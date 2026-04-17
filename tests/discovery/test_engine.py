"""Tests for the discovery engine and validator."""

import json
import pytest
from pathlib import Path

from agent.discovery.engine import discover_components, _detect_repo_shape
from agent.discovery.validator import (
    validate_discovery,
    validate_graph,
    validate_analysis,
)
from agent.schemas.core import Component, ComponentKind


@pytest.fixture
def repo(tmp_path):
    class Repo:
        root = tmp_path

        def write(self, path: str, content: str):
            p = tmp_path / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return p

        def write_json(self, path: str, data: dict):
            self.write(path, json.dumps(data))

    return Repo()


class TestDiscoverComponents:
    def test_empty_repo(self, repo):
        comps = discover_components(repo.root)
        assert comps == []

    def test_single_go_module(self, repo):
        repo.write("go.mod", "module github.com/org/mylib\n\ngo 1.21\n")
        repo.write("lib.go", "package mylib\n\nfunc Hello() {}\n")

        comps = discover_components(repo.root)
        assert len(comps) == 1
        assert comps[0].type == "go-module"

    def test_polyglot_repo(self, repo):
        repo.write("go.mod", "module github.com/org/backend\n\ngo 1.21\n")
        repo.write("server.go", "package main\n\nfunc main() {}\n")
        repo.write(
            "web/package.json",
            json.dumps(
                {
                    "name": "frontend",
                    "dependencies": {"react": "^18"},
                }
            ),
        )

        comps = discover_components(repo.root)
        types = {c.type for c in comps}
        assert "go-module" in types
        # TS plugin should find the frontend
        assert any("package" in t for t in types)

    def test_deduplication_by_root_path(self, repo):
        """Same root_path from different plugins should be deduplicated."""
        repo.write("go.mod", "module github.com/org/lib\n\ngo 1.21\n")
        repo.write("lib.go", "package lib\n")
        # The Go plugin will find root "." — no other plugin should
        # add another component at root

        comps = discover_components(repo.root)
        roots = [c.root_path for c in comps]
        # No duplicate root paths
        assert len(roots) == len(set(roots))

    def test_writes_output_files(self, repo):
        repo.write("go.mod", "module github.com/org/lib\n\ngo 1.21\n")
        repo.write("lib.go", "package lib\n")

        output_dir = repo.root / "output"
        discover_components(repo.root, output_dir=output_dir)

        assert (output_dir / "components.json").exists()

        with open(output_dir / "components.json") as f:
            data = json.load(f)
        assert "components" in data
        assert "metadata" in data
        assert isinstance(data["components"], list)

    def test_output_metadata(self, repo):
        repo.write("pyproject.toml", '[project]\nname = "mylib"\n')

        output_dir = repo.root / "output"
        discover_components(repo.root, output_dir=output_dir)

        with open(output_dir / "components.json") as f:
            data = json.load(f)
        meta = data["metadata"]
        assert meta["total_components"] == 1
        assert "python-package" in meta["by_language"]


class TestRepoShapeDetection:
    def test_empty(self):
        assert _detect_repo_shape([]) == "empty"

    def test_single_package(self):
        comp = Component(
            name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="."
        )
        assert _detect_repo_shape([comp]) == "single-package"

    def test_monorepo(self):
        comps = [
            Component(
                name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="a"
            ),
            Component(
                name="b", kind=ComponentKind.SERVICE, type="go-module", root_path="b"
            ),
        ]
        assert _detect_repo_shape(comps) == "monorepo"

    def test_polyglot(self):
        comps = [
            Component(
                name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="a"
            ),
            Component(
                name="b",
                kind=ComponentKind.FRONTEND,
                type="typescript-package",
                root_path="web",
            ),
        ]
        assert _detect_repo_shape(comps) == "polyglot-monorepo"


class TestValidateDiscovery:
    def test_valid(self, repo):
        comps = [
            Component(
                name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="."
            ),
        ]
        errors = validate_discovery(comps, repo.root)
        assert errors == []

    def test_duplicate_names(self, repo):
        comps = [
            Component(
                name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="a"
            ),
            Component(
                name="a", kind=ComponentKind.LIBRARY, type="go-module", root_path="b"
            ),
        ]
        (repo.root / "a").mkdir()
        (repo.root / "b").mkdir()
        errors = validate_discovery(comps, repo.root)
        assert any("Duplicate" in e for e in errors)

    def test_missing_root_path(self, repo):
        comps = [
            Component(
                name="a",
                kind=ComponentKind.LIBRARY,
                type="go-module",
                root_path="nonexistent",
            ),
        ]
        errors = validate_discovery(comps, repo.root)
        assert any("does not exist" in e for e in errors)

    def test_self_dependency(self, repo):
        comps = [
            Component(
                name="a",
                kind=ComponentKind.LIBRARY,
                type="go-module",
                root_path=".",
                internal_dependencies=["a"],
            ),
        ]
        errors = validate_discovery(comps, repo.root)
        assert any("depends on itself" in e for e in errors)

    def test_unresolved_dependency(self, repo):
        comps = [
            Component(
                name="a",
                kind=ComponentKind.LIBRARY,
                type="go-module",
                root_path=".",
                internal_dependencies=["nonexistent"],
            ),
        ]
        errors = validate_discovery(comps, repo.root)
        assert any("unresolved" in e for e in errors)


class TestValidateGraph:
    def test_valid_depth_order(self):
        comps = [
            Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path="a"),
            Component(
                name="b",
                kind=ComponentKind.LIBRARY,
                type="t",
                root_path="b",
                internal_dependencies=["a"],
            ),
        ]
        depth_order = [["a"], ["b"]]
        errors = validate_graph(comps, depth_order)
        assert errors == []

    def test_topological_violation(self):
        comps = [
            Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path="a"),
            Component(
                name="b",
                kind=ComponentKind.LIBRARY,
                type="t",
                root_path="b",
                internal_dependencies=["a"],
            ),
        ]
        # b depends on a, but both at depth 0 → violation
        depth_order = [["a", "b"]]
        errors = validate_graph(comps, depth_order)
        assert any("Topological violation" in e for e in errors)
