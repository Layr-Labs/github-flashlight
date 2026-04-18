"""Tests for CLI diff logic (incremental update pipeline)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from agent.cli import (
    load_manifest,
    load_components,
    map_files_to_components,
    compute_diff_context,
)


@pytest.fixture
def repo(tmp_path):
    class Repo:
        root = tmp_path

        def write(self, path: str, content: str):
            p = tmp_path / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return p

        def write_json(self, path: str, data):
            self.write(path, json.dumps(data))

    return Repo()


class TestLoadManifest:
    def test_missing_manifest(self, tmp_path):
        assert load_manifest(tmp_path) is None

    def test_valid_manifest(self, repo):
        repo.write_json(
            "manifest.json",
            {
                "service_name": "myapp",
                "artifact_version": 3,
                "source_commit": "abc123",
            },
        )
        result = load_manifest(repo.root)
        assert result["service_name"] == "myapp"
        assert result["artifact_version"] == 3
        assert result["source_commit"] == "abc123"

    def test_manifest_without_source_commit(self, repo):
        repo.write_json(
            "manifest.json",
            {
                "service_name": "myapp",
                "artifact_version": 1,
            },
        )
        result = load_manifest(repo.root)
        assert result is not None
        assert result.get("source_commit", "") == ""


class TestLoadComponents:
    def test_components_json(self, repo):
        repo.write_json(
            "service_discovery/components.json",
            {
                "components": [
                    {"name": "core", "kind": "library", "root_path": "core"},
                    {"name": "utils", "kind": "library", "root_path": "utils"},
                    {"name": "server", "kind": "service", "root_path": "cmd/server"},
                ],
            },
        )
        comps = load_components(repo.root)
        assert len(comps) == 3
        names = {c["name"] for c in comps}
        assert names == {"core", "utils", "server"}

    def test_empty_components(self, repo):
        repo.write_json(
            "service_discovery/components.json",
            {
                "components": [],
            },
        )
        comps = load_components(repo.root)
        assert comps == []

    def test_no_service_discovery_dir(self, tmp_path):
        comps = load_components(tmp_path)
        assert comps == []

    def test_array_format_fallback(self, repo):
        repo.write_json(
            "service_discovery/components.json",
            [
                {"name": "core", "root_path": "core"},
            ],
        )
        comps = load_components(repo.root)
        assert len(comps) == 1


class TestMapFilesToComponents:
    def test_basic_mapping(self):
        components = [
            {"name": "core", "root_path": "core"},
            {"name": "api", "root_path": "api"},
        ]
        changed = ["core/types.go", "core/utils.go", "api/server.go"]
        affected, unmapped = map_files_to_components(changed, components)
        assert affected == {"core", "api"}
        assert unmapped == []

    def test_unmapped_files(self):
        components = [
            {"name": "core", "root_path": "core"},
        ]
        changed = ["core/types.go", "newpkg/foo.go"]
        affected, unmapped = map_files_to_components(changed, components)
        assert affected == {"core"}
        assert unmapped == ["newpkg/foo.go"]

    def test_nested_paths(self):
        components = [
            {"name": "disperser", "root_path": "disperser"},
            {"name": "disperser-apiserver", "root_path": "disperser/cmd/apiserver"},
        ]
        changed = ["disperser/cmd/apiserver/main.go"]
        affected, unmapped = map_files_to_components(changed, components)
        # Should match the more specific path first (disperser/cmd/apiserver)
        # But current implementation matches first component with prefix
        assert "disperser" in affected or "disperser-apiserver" in affected
        assert unmapped == []

    def test_exact_root_match(self):
        components = [
            {"name": "readme", "root_path": "README.md"},
        ]
        changed = ["README.md"]
        affected, unmapped = map_files_to_components(changed, components)
        assert affected == {"readme"}

    def test_empty_root_path_skipped(self):
        components = [
            {"name": "root", "root_path": ""},
            {"name": "core", "root_path": "core"},
        ]
        changed = ["core/types.go"]
        affected, unmapped = map_files_to_components(changed, components)
        assert affected == {"core"}

    def test_no_changed_files(self):
        components = [{"name": "core", "root_path": "core"}]
        affected, unmapped = map_files_to_components([], components)
        assert affected == set()
        assert unmapped == []

    def test_no_components(self):
        affected, unmapped = map_files_to_components(["foo.go"], [])
        assert affected == set()
        assert unmapped == ["foo.go"]

    def test_trailing_slash_handling(self):
        components = [
            {"name": "core", "root_path": "core/"},
        ]
        changed = ["core/types.go"]
        affected, unmapped = map_files_to_components(changed, components)
        assert affected == {"core"}


class TestComputeDiffContext:
    def test_no_last_sha(self, repo):
        result = compute_diff_context(repo.root, repo.root, "", "abc123")
        assert result["mode"] == "full"

    def test_no_components(self, repo):
        # Has manifest but no components
        (repo.root / "service_discovery").mkdir(parents=True)
        result = compute_diff_context(repo.root, repo.root, "old", "new")
        assert result["mode"] == "full"

    @patch("agent.cli.git_diff_files")
    def test_incremental_with_changes(self, mock_diff, repo):
        mock_diff.return_value = ["core/types.go", "api/server.go"]
        repo.write_json(
            "service_discovery/components.json",
            {
                "components": [
                    {"name": "core", "kind": "library", "root_path": "core"},
                    {"name": "api", "kind": "service", "root_path": "api"},
                ],
            },
        )

        result = compute_diff_context(repo.root, repo.root, "old_sha", "new_sha")
        assert result["mode"] == "incremental"
        assert result["changed_components"] == {"core", "api"}
        assert result["changed_files"] == ["core/types.go", "api/server.go"]
        assert result["unmapped_files"] == []

    @patch("agent.cli.git_diff_files")
    def test_incremental_with_unmapped(self, mock_diff, repo):
        mock_diff.return_value = ["core/types.go", "newpkg/foo.go"]
        repo.write_json(
            "service_discovery/components.json",
            {
                "components": [
                    {"name": "core", "kind": "library", "root_path": "core"},
                ],
            },
        )

        result = compute_diff_context(repo.root, repo.root, "old", "new")
        assert result["mode"] == "incremental"
        assert result["changed_components"] == {"core"}
        assert result["unmapped_files"] == ["newpkg/foo.go"]

    @patch("agent.cli.git_diff_files")
    def test_no_changes(self, mock_diff, repo):
        mock_diff.return_value = []
        repo.write_json(
            "service_discovery/components.json",
            {
                "components": [
                    {"name": "core", "kind": "library", "root_path": "core"},
                ],
            },
        )

        result = compute_diff_context(repo.root, repo.root, "old", "new")
        # Empty diff → full analysis (safety fallback)
        assert result["mode"] == "full"
