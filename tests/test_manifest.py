"""Tests for artifact manifest schema."""

import json
import pytest
from pathlib import Path

from agent.schemas.manifest import (
    ArtifactManifest,
    ArtifactFile,
    MANIFEST_SCHEMA_VERSION,
)


class TestArtifactFile:
    def test_roundtrip(self):
        af = ArtifactFile(
            path="service_analyses/core.md",
            size_bytes=4096,
            sha256="abc123",
            category="analysis",
        )
        d = af.to_dict()
        af2 = ArtifactFile.from_dict(d)
        assert af2.path == af.path
        assert af2.size_bytes == af.size_bytes
        assert af2.sha256 == af.sha256
        assert af2.category == af.category

    def test_optional_category(self):
        af = ArtifactFile(path="foo.md", size_bytes=100, sha256="abc")
        d = af.to_dict()
        assert "category" not in d  # Empty category omitted

    def test_from_path(self, tmp_path):
        f = tmp_path / "sub" / "test.md"
        f.parent.mkdir()
        f.write_text("hello world")

        af = ArtifactFile.from_path(f, tmp_path, category="analysis")
        assert af.path == "sub/test.md"
        assert af.size_bytes == 11
        assert len(af.sha256) == 64  # SHA-256 hex digest
        assert af.category == "analysis"


class TestArtifactManifest:
    def test_roundtrip(self):
        m = ArtifactManifest(
            service_name="eigenda",
            artifact_version=3,
            generated_at="2026-04-08T00:00:00Z",
            model="claude-sonnet-4-20250514",
            source_repo="github.com/Layr-Labs/eigenda",
            source_commit="abc123",
            components_count=19,
            total_files=25,
            files=[
                ArtifactFile(path="core.md", size_bytes=100, sha256="aaa"),
            ],
            metadata={"custom": "value"},
        )
        d = m.to_dict()
        m2 = ArtifactManifest.from_dict(d)
        assert m2.service_name == "eigenda"
        assert m2.artifact_version == 3
        assert m2.source_commit == "abc123"
        assert m2.components_count == 19
        assert len(m2.files) == 1
        assert m2.files[0].path == "core.md"
        assert m2.metadata == {"custom": "value"}

    def test_json_roundtrip(self):
        m = ArtifactManifest.create_initial("myapp", source_commit="def456")
        json_str = m.to_json()
        m2 = ArtifactManifest.from_json(json_str)
        assert m2.service_name == "myapp"
        assert m2.artifact_version == 1
        assert m2.source_commit == "def456"

    def test_create_initial(self):
        m = ArtifactManifest.create_initial(
            "myapp",
            source_repo="github.com/org/myapp",
            source_commit="abc",
            model="claude-sonnet-4-20250514",
        )
        assert m.service_name == "myapp"
        assert m.artifact_version == 1
        assert m.source_repo == "github.com/org/myapp"
        assert m.source_commit == "abc"
        assert m.model == "claude-sonnet-4-20250514"
        assert m.generator == "github-flashlight"
        assert m.schema_version == MANIFEST_SCHEMA_VERSION
        assert m.generated_at  # Non-empty timestamp

    def test_create_next_version(self):
        v1 = ArtifactManifest.create_initial("myapp", source_commit="aaa")
        v2 = ArtifactManifest.create_next_version(v1, source_commit="bbb")

        assert v2.service_name == "myapp"
        assert v2.artifact_version == 2
        assert v2.source_commit == "bbb"
        assert v2.source_repo == v1.source_repo

    def test_create_next_version_increments(self):
        v1 = ArtifactManifest.create_initial("myapp")
        v2 = ArtifactManifest.create_next_version(v1)
        v3 = ArtifactManifest.create_next_version(v2)
        assert v1.artifact_version == 1
        assert v2.artifact_version == 2
        assert v3.artifact_version == 3

    def test_create_next_version_inherits_model(self):
        v1 = ArtifactManifest.create_initial("myapp", model="sonnet")
        v2 = ArtifactManifest.create_next_version(v1)
        assert v2.model == "sonnet"

    def test_create_next_version_override_model(self):
        v1 = ArtifactManifest.create_initial("myapp", model="sonnet")
        v2 = ArtifactManifest.create_next_version(v1, model="opus")
        assert v2.model == "opus"

    def test_create_next_version_inherits_commit_if_empty(self):
        v1 = ArtifactManifest.create_initial("myapp", source_commit="aaa")
        v2 = ArtifactManifest.create_next_version(v1)
        assert v2.source_commit == "aaa"

    def test_scan_directory(self, tmp_path):
        # Create mock artifact structure
        (tmp_path / "service_analyses").mkdir()
        (tmp_path / "service_analyses" / "core.md").write_text("# Core")
        (tmp_path / "service_analyses" / "api.md").write_text("# API")
        (tmp_path / "dependency_graphs").mkdir()
        (tmp_path / "dependency_graphs" / "library_graph.json").write_text("{}")
        (tmp_path / "architecture_docs").mkdir()
        (tmp_path / "architecture_docs" / "architecture.md").write_text("# Arch")
        # manifest.json should be skipped
        (tmp_path / "manifest.json").write_text("{}")
        # Non-artifact files should be skipped
        (tmp_path / "service_analyses" / "notes.txt").write_text("ignore me")

        m = ArtifactManifest.create_initial("test")
        m.scan_directory(tmp_path)

        assert m.total_files == 4
        paths = {f.path for f in m.files}
        assert "service_analyses/core.md" in paths
        assert "service_analyses/api.md" in paths
        assert "dependency_graphs/library_graph.json" in paths
        assert "architecture_docs/architecture.md" in paths
        assert "manifest.json" not in paths
        assert "service_analyses/notes.txt" not in paths

        # Check categories
        cats = {f.path: f.category for f in m.files}
        assert cats["service_analyses/core.md"] == "analysis"
        assert cats["dependency_graphs/library_graph.json"] == "graph"
        assert cats["architecture_docs/architecture.md"] == "architecture"

    def test_from_dict_defaults(self):
        """Minimal dict should deserialize with sensible defaults."""
        m = ArtifactManifest.from_dict(
            {
                "service_name": "test",
                "artifact_version": 1,
            }
        )
        assert m.generated_at == ""
        assert m.model == ""
        assert m.files == []
        assert m.metadata == {}
        assert m.schema_version == MANIFEST_SCHEMA_VERSION
