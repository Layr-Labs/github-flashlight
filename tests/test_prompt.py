"""Tests for prompt construction logic."""

import json
import pytest
from pathlib import Path

from agent.cli import build_analysis_prompt


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Set up a mock /tmp/{service_name}/ directory."""
    service_name = "testproject"
    work = tmp_path / service_name
    work.mkdir()

    # Monkeypatch the /tmp/ path used in build_analysis_prompt
    # The function uses Path(f"/tmp/{service_name}") — we need to
    # make the service_name match or patch the path.
    # Since we can't easily patch Path literals, we test via the
    # actual /tmp/ path or accept the prompt references /tmp/testproject
    return work, service_name


class TestFullAnalysis:
    def test_basic_prompt(self):
        prompt = build_analysis_prompt(
            Path("/repo/myapp"),
            "myapp",
            {"mode": "full"},
        )
        assert "Analyze the codebase at /repo/myapp" in prompt

    def test_includes_source_commit(self):
        prompt = build_analysis_prompt(
            Path("/repo/myapp"),
            "myapp",
            {"mode": "full"},
            head_sha="abc123",
        )
        assert "SOURCE_COMMIT: abc123" in prompt

    def test_no_source_commit_when_empty(self):
        prompt = build_analysis_prompt(
            Path("/repo/myapp"),
            "myapp",
            {"mode": "full"},
            head_sha="",
        )
        assert "SOURCE_COMMIT" not in prompt

    def test_discovery_complete_when_files_exist(self, tmp_path):
        """When components.json exists in /tmp/svcname/, prompt includes DISCOVERY_COMPLETE."""
        svc = "testdiscovery"
        work = Path(f"/tmp/{svc}")
        work.mkdir(parents=True, exist_ok=True)
        (work / "service_discovery").mkdir(exist_ok=True)
        (work / "service_discovery" / "components.json").write_text("{}")

        try:
            prompt = build_analysis_prompt(
                Path("/repo"),
                svc,
                {"mode": "full"},
            )
            assert "DISCOVERY_COMPLETE" in prompt
            assert "SKIP discovery phases" in prompt
        finally:
            # Clean up
            import shutil

            shutil.rmtree(work, ignore_errors=True)

    def test_discovery_complete_with_graph(self, tmp_path):
        svc = "testdiscoverygraph"
        work = Path(f"/tmp/{svc}")
        work.mkdir(parents=True, exist_ok=True)
        (work / "service_discovery").mkdir(exist_ok=True)
        (work / "service_discovery" / "components.json").write_text("{}")
        (work / "dependency_graphs").mkdir(exist_ok=True)
        (work / "dependency_graphs" / "graph.json").write_text("{}")

        try:
            prompt = build_analysis_prompt(
                Path("/repo"),
                svc,
                {"mode": "full"},
            )
            assert "graph.json" in prompt
        finally:
            import shutil

            shutil.rmtree(work, ignore_errors=True)

    def test_no_discovery_complete_without_files(self):
        prompt = build_analysis_prompt(
            Path("/repo"),
            "nonexistent_svc_12345",
            {"mode": "full"},
        )
        assert "DISCOVERY_COMPLETE" not in prompt


class TestIncrementalAnalysis:
    def test_changed_components_section(self, tmp_path):
        artifacts = tmp_path / "artifacts"
        (artifacts / "service_discovery").mkdir(parents=True)
        (artifacts / "service_discovery" / "components.json").write_text(
            json.dumps(
                {
                    "components": [
                        {"name": "core", "kind": "library", "root_path": "core"},
                        {"name": "api", "kind": "service", "root_path": "api"},
                    ],
                }
            )
        )

        diff_context = {
            "mode": "incremental",
            "changed_components": {"core", "api"},
            "changed_files": ["core/types.go", "api/server.go"],
            "unmapped_files": [],
        }

        prompt = build_analysis_prompt(
            Path("/repo"),
            "myapp",
            diff_context,
            artifacts_dir=artifacts,
        )
        assert "CHANGED_COMPONENTS:" in prompt
        assert "core" in prompt
        assert "api" in prompt

    def test_unmapped_files_section(self, tmp_path):
        artifacts = tmp_path / "artifacts"
        (artifacts / "service_discovery").mkdir(parents=True)
        (artifacts / "service_discovery" / "components.json").write_text(
            json.dumps({"components": []})
        )

        diff_context = {
            "mode": "incremental",
            "changed_components": set(),
            "changed_files": ["newpkg/foo.go"],
            "unmapped_files": ["newpkg/foo.go"],
        }

        prompt = build_analysis_prompt(
            Path("/repo"),
            "myapp",
            diff_context,
            artifacts_dir=artifacts,
        )
        assert "NEW_FILES_OUTSIDE_KNOWN_COMPONENTS:" in prompt
        assert "newpkg/foo.go" in prompt

    def test_existing_artifacts_reference(self, tmp_path):
        artifacts = tmp_path / "artifacts"
        (artifacts / "service_discovery").mkdir(parents=True)
        (artifacts / "service_discovery" / "components.json").write_text(
            json.dumps(
                {
                    "components": [
                        {"name": "core", "kind": "library", "root_path": "core"},
                    ],
                }
            )
        )

        diff_context = {
            "mode": "incremental",
            "changed_components": {"core"},
            "changed_files": ["core/types.go"],
            "unmapped_files": [],
        }

        prompt = build_analysis_prompt(
            Path("/repo"),
            "myapp",
            diff_context,
            artifacts_dir=artifacts,
        )
        assert "EXISTING_ARTIFACTS:" in prompt
        assert str(artifacts) in prompt

    def test_full_mode_no_changed_components(self):
        prompt = build_analysis_prompt(
            Path("/repo"),
            "myapp",
            {"mode": "full"},
        )
        assert "CHANGED_COMPONENTS" not in prompt
        assert "EXISTING_ARTIFACTS" not in prompt
