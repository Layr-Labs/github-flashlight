"""Tests for analyze_current_depth's parallel execution and error handling.

The action runs one ThreadPoolExecutor per depth level, bounded by
FLASHLIGHT_MAX_PARALLEL. These tests exercise that behavior without
touching any real LLM by monkeypatching _run_component_analyzer.
"""

import os
import threading
import time
from unittest.mock import MagicMock

import pytest
from burr.core import State

import agent.burr_app as burr_app
from agent.burr_app import (
    _build_upstream_context,
    _get_max_parallel,
    _run_component_analyzer,
    analyze_current_depth,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _component(name, *, deps=None, kind="library"):
    """Build a minimal component dict matching the structure analyze_current_depth expects."""
    return {
        "name": name,
        "kind": kind,
        "type": "python-package",
        "root_path": f"path/{name}",
        "description": "",
        "internal_dependencies": deps or [],
    }


def _state(components, depth_order, current_depth=0, prior_analyses=None):
    """Construct the Burr State slice analyze_current_depth needs."""
    return State(
        {
            "components": {c["name"]: c for c in components},
            "depth_order": depth_order,
            "current_depth": current_depth,
            "component_analyses": prior_analyses or {},
            "service_name": "test-svc",
        }
    )


@pytest.fixture(autouse=True)
def _reset_max_parallel(monkeypatch):
    """Ensure FLASHLIGHT_MAX_PARALLEL never leaks between tests."""
    monkeypatch.delenv("FLASHLIGHT_MAX_PARALLEL", raising=False)
    yield


# ---------------------------------------------------------------------------
# _get_max_parallel: env-var parsing
# ---------------------------------------------------------------------------


class TestGetMaxParallel:
    def test_default_is_four(self):
        assert _get_max_parallel() == 4

    def test_valid_integer(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "8")
        assert _get_max_parallel() == 8

    def test_one_opts_out_of_parallelism(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "1")
        assert _get_max_parallel() == 1

    def test_negative_clamped_to_one(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "-5")
        assert _get_max_parallel() == 1

    def test_zero_clamped_to_one(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "0")
        assert _get_max_parallel() == 1

    def test_garbage_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "not-a-number")
        assert _get_max_parallel() == 4

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "")
        assert _get_max_parallel() == 4


# ---------------------------------------------------------------------------
# _build_upstream_context: dependency summary assembly
# ---------------------------------------------------------------------------


class TestBuildUpstreamContext:
    def test_no_deps_returns_empty(self):
        assert _build_upstream_context([], {"other": "analysis"}) == ""

    def test_missing_analyses_silently_skipped(self):
        out = _build_upstream_context(
            ["dep_a", "dep_b"], {"dep_b": "## Summary\nDep B summary\n"}
        )
        assert "dep_a" not in out
        assert "dep_b" in out
        assert "Dep B summary" in out

    def test_extracts_summary_section(self):
        analysis = "## Summary\nI do a thing.\nAnd another.\n\n## Other\nIgnored"
        out = _build_upstream_context(["dep"], {"dep": analysis})
        assert "### dep" in out
        assert "I do a thing." in out
        assert "Ignored" not in out

    def test_preserves_dep_order(self):
        analyses = {
            "b": "## Summary\nB summary\n",
            "a": "## Summary\nA summary\n",
        }
        # Caller-supplied dependency order is preserved.
        out = _build_upstream_context(["b", "a"], analyses)
        assert out.index("### b") < out.index("### a")


# ---------------------------------------------------------------------------
# analyze_current_depth: core behavior
# ---------------------------------------------------------------------------


class TestAnalyzeCurrentDepth:
    def test_single_component(self, monkeypatch):
        calls = []

        def fake_runner(**kwargs):
            calls.append(kwargs["component"]["name"])
            return f"## Summary\n{kwargs['component']['name']} done\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("solo")],
            depth_order=[["solo"]],
        )
        out = analyze_current_depth(state, MagicMock())

        assert calls == ["solo"]
        assert out.get("component_analyses") == {"solo": "## Summary\nsolo done\n"}
        assert out.get("current_depth") == 1

    def test_multiple_components_all_analyzed(self, monkeypatch):
        runs = []

        def fake_runner(**kwargs):
            runs.append(kwargs["component"]["name"])
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("a"), _component("b"), _component("c")],
            depth_order=[["a", "b", "c"]],
        )
        out = analyze_current_depth(state, MagicMock())

        assert sorted(runs) == ["a", "b", "c"]
        assert set(out.get("component_analyses").keys()) == {"a", "b", "c"}

    def test_results_merged_in_deterministic_order(self, monkeypatch):
        """Even if futures finish in reverse order, the merge order matches
        depth_order so downstream synthesis is reproducible."""
        finish_delays = {"a": 0.06, "b": 0.03, "c": 0.01}

        def fake_runner(**kwargs):
            name = kwargs["component"]["name"]
            time.sleep(finish_delays[name])
            return f"## Summary\n{name}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("a"), _component("b"), _component("c")],
            depth_order=[["a", "b", "c"]],
        )
        out = analyze_current_depth(state, MagicMock())

        # c finishes first, b second, a last — but the dict key order is
        # the depth_order order (a, b, c).
        assert list(out.get("component_analyses").keys()) == ["a", "b", "c"]

    def test_components_actually_run_in_parallel(self, monkeypatch):
        """Wall time for N 100ms tasks with MAX_PARALLEL=N should be ~100ms,
        not N*100ms. Tolerance is generous so flakes are unlikely."""
        per_task = 0.10
        n = 4

        def fake_runner(**kwargs):
            time.sleep(per_task)
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", str(n))

        state = _state(
            components=[_component(f"c{i}") for i in range(n)],
            depth_order=[[f"c{i}" for i in range(n)]],
        )
        t0 = time.perf_counter()
        analyze_current_depth(state, MagicMock())
        elapsed = time.perf_counter() - t0

        sequential_lower_bound = per_task * n  # 0.40s
        # If parallel, we should be well below sequential_lower_bound.
        # Allow a fat safety margin (75% of sequential) for CI noise.
        assert elapsed < sequential_lower_bound * 0.75, (
            f"Expected parallel run much faster than {sequential_lower_bound}s, "
            f"got {elapsed:.3f}s"
        )

    def test_max_parallel_one_forces_serial(self, monkeypatch):
        """MAX_PARALLEL=1 should serialize: per-task sleep seen N times
        end-to-end, not once."""
        per_task = 0.10
        n = 3

        def fake_runner(**kwargs):
            time.sleep(per_task)
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "1")

        state = _state(
            components=[_component(f"c{i}") for i in range(n)],
            depth_order=[[f"c{i}" for i in range(n)]],
        )
        t0 = time.perf_counter()
        analyze_current_depth(state, MagicMock())
        elapsed = time.perf_counter() - t0

        # Should take at least (n-1)*per_task — if parallel, would be ~per_task.
        assert elapsed >= per_task * (n - 1), (
            f"Expected serial run ≥ {per_task * (n - 1)}s, got {elapsed:.3f}s"
        )

    def test_max_parallel_respects_pool_cap(self, monkeypatch):
        """With MAX_PARALLEL=2 and 4 tasks @ 100ms each, wall time should be
        ~200ms (2 waves of 2), not 100ms (all four at once) or 400ms (serial)."""
        per_task = 0.10
        n = 4
        active = {"count": 0, "peak": 0}
        lock = threading.Lock()

        def fake_runner(**kwargs):
            with lock:
                active["count"] += 1
                active["peak"] = max(active["peak"], active["count"])
            time.sleep(per_task)
            with lock:
                active["count"] -= 1
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)
        monkeypatch.setenv("FLASHLIGHT_MAX_PARALLEL", "2")

        state = _state(
            components=[_component(f"c{i}") for i in range(n)],
            depth_order=[[f"c{i}" for i in range(n)]],
        )
        analyze_current_depth(state, MagicMock())

        # Peak concurrency should equal the cap, not exceed it.
        assert active["peak"] == 2, f"expected peak=2, got {active['peak']}"

    def test_worker_exception_captured_as_error_string(self, monkeypatch):
        """A crashing subagent shouldn't kill the whole depth — its result
        becomes an Error-prefixed string and peers still run."""

        def fake_runner(**kwargs):
            if kwargs["component"]["name"] == "bad":
                raise RuntimeError("boom")
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("good"), _component("bad"), _component("also_good")],
            depth_order=[["good", "bad", "also_good"]],
        )
        out = analyze_current_depth(state, MagicMock())
        analyses = out.get("component_analyses")

        assert analyses["good"].startswith("## Summary")
        assert analyses["also_good"].startswith("## Summary")
        assert analyses["bad"].startswith("Error:")
        assert "boom" in analyses["bad"]
        # Depth still advances.
        assert out.get("current_depth") == 1

    def test_missing_component_is_warned_and_skipped(self, monkeypatch, caplog):
        """A name in depth_order that isn't in the components inventory should
        log a warning but not stop the run."""
        calls = []

        def fake_runner(**kwargs):
            calls.append(kwargs["component"]["name"])
            return "## Summary\nok\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("real")],
            depth_order=[["real", "ghost"]],
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="agent.burr_app"):
            out = analyze_current_depth(state, MagicMock())

        assert calls == ["real"]
        assert "ghost" not in out.get("component_analyses")
        assert any("ghost" in rec.message for rec in caplog.records)

    def test_upstream_context_built_from_prior_analyses(self, monkeypatch):
        """A depth>0 component should receive the summaries of its deps."""
        captured_context = {}

        def fake_runner(**kwargs):
            captured_context[kwargs["component"]["name"]] = kwargs["upstream_context"]
            return f"## Summary\n{kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        prior = {
            "dep_a": "## Summary\nDep A does stuff\n",
            "dep_b": "## Summary\nDep B does other stuff\n",
        }
        state = _state(
            components=[
                _component("consumer", deps=["dep_a", "dep_b"]),
            ],
            depth_order=[["consumer"]],
            prior_analyses=prior,
        )
        analyze_current_depth(state, MagicMock())

        ctx = captured_context["consumer"]
        assert "### dep_a" in ctx
        assert "Dep A does stuff" in ctx
        assert "### dep_b" in ctx
        assert "Dep B does other stuff" in ctx

    def test_depth_already_exhausted_noop(self, monkeypatch):
        """If current_depth >= len(depth_order), no work is attempted."""
        monkeypatch.setattr(
            burr_app,
            "_run_component_analyzer",
            lambda **kw: pytest.fail("should not be called"),
        )

        state = _state(
            components=[_component("a")],
            depth_order=[["a"]],
            current_depth=5,
        )
        out = analyze_current_depth(state, MagicMock())
        assert out.get("component_analyses") == {}

    def test_empty_depth_still_advances(self, monkeypatch):
        """An empty depth bucket is legal (e.g. diff-driven runs) — advance
        without running anything."""
        monkeypatch.setattr(
            burr_app,
            "_run_component_analyzer",
            lambda **kw: pytest.fail("should not be called"),
        )

        state = _state(components=[], depth_order=[[]])
        out = analyze_current_depth(state, MagicMock())
        assert out.get("current_depth") == 1
        assert out.get("component_analyses") == {}

    def test_prior_analyses_preserved(self, monkeypatch):
        """analyses accumulated across earlier depths aren't clobbered."""

        def fake_runner(**kwargs):
            return f"## Summary\nnew: {kwargs['component']['name']}\n"

        monkeypatch.setattr(burr_app, "_run_component_analyzer", fake_runner)

        state = _state(
            components=[_component("new")],
            depth_order=[["new"]],
            prior_analyses={"old": "## Summary\nold result\n"},
        )
        out = analyze_current_depth(state, MagicMock())

        analyses = out.get("component_analyses")
        assert analyses["old"] == "## Summary\nold result\n"
        assert analyses["new"].startswith("## Summary\nnew: new")


# ---------------------------------------------------------------------------
# _run_component_analyzer: orchestrator-writes-file behavior
#
# LLMs drop the write_file tool call ~75% of the time, especially on
# smaller models. The orchestrator persists the final_response to disk
# itself to guarantee every completed subagent produces a .md file.
# ---------------------------------------------------------------------------


class TestOrchestratorWritesAnalysis:
    def test_writes_final_response_to_expected_path(self, tmp_path, monkeypatch):
        """The runner's return value should land in service_analyses/{name}.md."""
        # Redirect /tmp/{service_name}/ at a tmp_path so the test is hermetic.
        service_name = "hermetic-svc"
        svc_root = tmp_path / service_name
        svc_root.mkdir()

        monkeypatch.setattr(
            burr_app,
            "_run_subagent_as_app",
            lambda **kwargs: "# Mock Analysis\n\nSubstantive content.",
        )

        # Patch the Path construction inside _run_component_analyzer
        import pathlib

        real_path = pathlib.Path

        def patched_path(arg):
            if isinstance(arg, str) and arg.startswith(f"/tmp/{service_name}/"):
                return real_path(str(tmp_path) + arg[len("/tmp"):])
            return real_path(arg)

        # Easier: patch the /tmp prefix by wrapping the out_path logic.
        # We do that by monkey-patching Path inside burr_app; simpler is to
        # run with the real /tmp and clean up.
        out_file = pathlib.Path(f"/tmp/{service_name}/service_analyses/comp.md")
        if out_file.exists():
            out_file.unlink()
        try:
            result = _run_component_analyzer(
                component={
                    "name": "comp",
                    "kind": "library",
                    "type": "python-package",
                    "root_path": "path/comp",
                },
                service_name=service_name,
                upstream_context="",
                tracer=None,
            )
            assert result.startswith("# Mock Analysis")
            assert out_file.exists(), "expected orchestrator to persist analysis"
            assert out_file.read_text() == "# Mock Analysis\n\nSubstantive content."
        finally:
            # Clean up the /tmp side-effect.
            if out_file.exists():
                out_file.unlink()
            try:
                out_file.parent.rmdir()
                out_file.parent.parent.rmdir()
            except OSError:
                pass  # directory not empty or already gone — that's fine

    def test_does_not_write_when_subagent_errored(self, monkeypatch):
        """Error-prefixed results shouldn't land on disk — they'd pollute
        the analyses directory with garbage."""
        service_name = "error-svc"
        monkeypatch.setattr(
            burr_app,
            "_run_subagent_as_app",
            lambda **kwargs: "Error: LLM call failed after 4 attempts: timeout",
        )

        import pathlib

        out_file = pathlib.Path(
            f"/tmp/{service_name}/service_analyses/broken.md"
        )
        if out_file.exists():
            out_file.unlink()
        try:
            result = _run_component_analyzer(
                component={
                    "name": "broken",
                    "kind": "library",
                    "type": "python-package",
                    "root_path": "path/broken",
                },
                service_name=service_name,
                upstream_context="",
                tracer=None,
            )
            assert result.startswith("Error:")
            assert not out_file.exists(), (
                f"error response should not be persisted, but {out_file} exists"
            )
        finally:
            if out_file.exists():
                out_file.unlink()
            try:
                out_file.parent.rmdir()
                out_file.parent.parent.rmdir()
            except OSError:
                pass

    def test_write_failure_doesnt_kill_analyzer(self, monkeypatch, caplog):
        """If disk write fails (permission error, whatever), the analysis
        is still returned to the caller — just logged as an error."""
        monkeypatch.setattr(
            burr_app,
            "_run_subagent_as_app",
            lambda **kwargs: "# Good analysis",
        )

        # Force the write step to raise by patching Path.write_text.
        import pathlib

        real_write = pathlib.Path.write_text

        def failing_write(self, *args, **kwargs):
            if "service_analyses" in str(self):
                raise OSError("disk full")
            return real_write(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "write_text", failing_write)

        import logging

        with caplog.at_level(logging.ERROR, logger="agent.burr_app"):
            result = _run_component_analyzer(
                component={
                    "name": "comp",
                    "kind": "library",
                    "type": "python-package",
                    "root_path": "path/comp",
                },
                service_name="write-fail-svc",
                upstream_context="",
                tracer=None,
            )

        assert result == "# Good analysis"
        assert any("Failed to persist analysis" in r.message for r in caplog.records)
