"""Tests for citation tracking: CodeCitation source URLs and citation extractor."""

import json
import pytest
from pathlib import Path
from textwrap import dedent

from agent.schemas.core import CodeCitation
from agent.utils.citation_extractor import (
    extract_citations_from_markdown,
    validate_citation_dict,
    extract_component_citations,
    build_citations_index,
    ExtractionResult,
)


# ---------------------------------------------------------------------------
# CodeCitation.source_url tests
# ---------------------------------------------------------------------------


class TestCodeCitationSourceUrl:
    def test_github_single_line(self):
        c = CodeCitation(
            file_path="src/main.rs", start_line=42, end_line=42, claim="entry"
        )
        url = c.source_url("https://github.com/org/repo", "abc123")
        assert url == "https://github.com/org/repo/blob/abc123/src/main.rs#L42"

    def test_github_line_range(self):
        c = CodeCitation(
            file_path="src/auth.rs", start_line=10, end_line=25, claim="auth"
        )
        url = c.source_url("https://github.com/org/repo", "abc123")
        assert url == "https://github.com/org/repo/blob/abc123/src/auth.rs#L10-L25"

    def test_github_no_commit_uses_head(self):
        c = CodeCitation(file_path="lib.rs", start_line=1, end_line=5, claim="")
        url = c.source_url("https://github.com/org/repo")
        assert url == "https://github.com/org/repo/blob/HEAD/lib.rs#L1-L5"

    def test_gitlab_url(self):
        c = CodeCitation(file_path="src/main.py", start_line=10, end_line=20, claim="")
        url = c.source_url("https://gitlab.com/org/repo", "def456")
        assert url == "https://gitlab.com/org/repo/blob/def456/src/main.py#L10-20"

    def test_bitbucket_url(self):
        c = CodeCitation(file_path="index.ts", start_line=1, end_line=10, claim="")
        url = c.source_url("https://bitbucket.org/org/repo", "abc")
        assert url == "https://bitbucket.org/org/repo/src/abc/index.ts#lines-1:10"

    def test_empty_base_url_returns_empty(self):
        c = CodeCitation(file_path="foo.go", start_line=1, end_line=1, claim="")
        assert c.source_url("") == ""
        assert c.source_url() == ""

    def test_trailing_slash_stripped(self):
        c = CodeCitation(file_path="main.go", start_line=5, end_line=5, claim="")
        url = c.source_url("https://github.com/org/repo/", "abc")
        assert url == "https://github.com/org/repo/blob/abc/main.go#L5"


class TestCodeCitationMarkdownLink:
    def test_with_url(self):
        c = CodeCitation(file_path="src/main.rs", start_line=10, end_line=20, claim="")
        result = c.to_markdown_link("https://github.com/org/repo", "abc123")
        assert (
            result
            == "[`src/main.rs:10-20`](https://github.com/org/repo/blob/abc123/src/main.rs#L10-L20)"
        )

    def test_without_url(self):
        c = CodeCitation(file_path="src/main.rs", start_line=10, end_line=20, claim="")
        result = c.to_markdown_link()
        assert result == "`src/main.rs:10-20`"


# ---------------------------------------------------------------------------
# Citation extractor tests
# ---------------------------------------------------------------------------


SAMPLE_MD_WITH_CITATIONS = dedent("""\
    # my-library Analysis

    ## Architecture

    This library provides utilities.

    ## Key Components

    - **Config** (`src/config.rs`): Configuration loader.

    ## Citations

    ```json
    [
      {
        "file_path": "src/config.rs",
        "start_line": 1,
        "end_line": 15,
        "claim": "Config struct loads TOML files",
        "section": "Key Components",
        "snippet": "pub struct Config { ... }"
      },
      {
        "file_path": "src/lib.rs",
        "start_line": 5,
        "end_line": 5,
        "claim": "Library re-exports config module",
        "section": "Architecture"
      }
    ]
    ```

    ## Analysis Summary

    Good library.
""")

SAMPLE_MD_NO_CITATIONS = dedent("""\
    # my-app Analysis

    ## Architecture

    This is an app.

    ## Files Analyzed

    - `src/main.rs` - entry point

    ## Analysis Summary

    Good app.
""")

SAMPLE_MD_INVALID_JSON = dedent("""\
    # bad Analysis

    ## Citations

    ```json
    [{ "file_path": "broken, not valid json
    ```

    ## Analysis Summary

    Oops.
""")

SAMPLE_MD_EMPTY_CITATIONS = dedent("""\
    # empty Analysis

    ## Citations

    ```json
    []
    ```

    ## Analysis Summary
""")

SAMPLE_MD_WITH_COMMENTS = dedent("""\
    # my-lib Analysis

    ## Citations

    <!-- These are the citations -->

    ```json
    [
      {
        "file_path": "src/main.rs",
        "start_line": 1,
        "end_line": 10,
        "claim": "Entry point",
        "section": "Architecture"
      }
    ]
    ```
""")


class TestExtractCitationsFromMarkdown:
    def test_extracts_valid_citations(self):
        dicts, errors = extract_citations_from_markdown(SAMPLE_MD_WITH_CITATIONS)
        assert len(dicts) == 2
        assert errors == []
        assert dicts[0]["file_path"] == "src/config.rs"
        assert dicts[1]["file_path"] == "src/lib.rs"

    def test_no_citations_section(self):
        dicts, errors = extract_citations_from_markdown(SAMPLE_MD_NO_CITATIONS)
        assert dicts == []
        assert len(errors) == 1
        assert "No ## Citations section" in errors[0]

    def test_invalid_json(self):
        dicts, errors = extract_citations_from_markdown(SAMPLE_MD_INVALID_JSON)
        assert dicts == []
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_empty_array(self):
        dicts, errors = extract_citations_from_markdown(SAMPLE_MD_EMPTY_CITATIONS)
        assert dicts == []
        assert errors == []

    def test_with_html_comments(self):
        dicts, errors = extract_citations_from_markdown(SAMPLE_MD_WITH_COMMENTS)
        assert len(dicts) == 1
        assert errors == []
        assert dicts[0]["claim"] == "Entry point"


class TestValidateCitationDict:
    def test_valid_citation(self):
        raw = {
            "file_path": "src/main.rs",
            "start_line": 10,
            "end_line": 20,
            "claim": "Handles auth",
            "section": "Architecture",
            "snippet": "fn auth() {}",
        }
        citation, errors = validate_citation_dict(raw)
        assert errors == []
        assert citation is not None
        assert citation.file_path == "src/main.rs"
        assert citation.start_line == 10
        assert citation.end_line == 20
        assert citation.claim == "Handles auth"

    def test_missing_file_path(self):
        raw = {"start_line": 1, "end_line": 1, "claim": "test"}
        citation, errors = validate_citation_dict(raw)
        assert citation is None
        assert any("file_path" in e for e in errors)

    def test_missing_claim(self):
        raw = {"file_path": "x.rs", "start_line": 1, "end_line": 1}
        citation, errors = validate_citation_dict(raw)
        assert citation is None
        assert any("claim" in e for e in errors)

    def test_invalid_line_numbers(self):
        raw = {"file_path": "x.rs", "start_line": 0, "end_line": -1, "claim": "test"}
        citation, errors = validate_citation_dict(raw)
        assert citation is None
        assert len(errors) >= 2

    def test_end_before_start(self):
        raw = {"file_path": "x.rs", "start_line": 20, "end_line": 10, "claim": "test"}
        citation, errors = validate_citation_dict(raw)
        assert citation is None
        assert any("end_line" in e for e in errors)

    def test_strips_tmp_prefix(self):
        raw = {
            "file_path": "/tmp/my-service/project/src/main.rs",
            "start_line": 1,
            "end_line": 5,
            "claim": "entry point",
        }
        citation, errors = validate_citation_dict(raw)
        assert errors == []
        assert citation.file_path == "src/main.rs"

    def test_file_existence_check(self, tmp_path):
        # Create a real file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.rs").write_text("fn main() {}\n")

        raw = {
            "file_path": "src/main.rs",
            "start_line": 1,
            "end_line": 1,
            "claim": "entry",
        }
        citation, errors = validate_citation_dict(raw, repo_root=tmp_path)
        assert errors == []
        assert citation is not None

    def test_file_not_found_check(self, tmp_path):
        raw = {
            "file_path": "src/nonexistent.rs",
            "start_line": 1,
            "end_line": 1,
            "claim": "test",
        }
        citation, errors = validate_citation_dict(raw, repo_root=tmp_path)
        assert any("does not exist" in e for e in errors)


class TestExtractComponentCitations:
    def test_extracts_from_file(self, tmp_path):
        md_path = tmp_path / "my-library.md"
        md_path.write_text(SAMPLE_MD_WITH_CITATIONS)

        result = extract_component_citations(md_path, "my-library")
        assert result.component_name == "my-library"
        assert result.valid_count == 2
        assert result.raw_count == 2
        assert result.errors == []

    def test_missing_file(self, tmp_path):
        md_path = tmp_path / "nonexistent.md"
        result = extract_component_citations(md_path, "missing")
        assert result.valid_count == 0
        assert len(result.errors) == 1

    def test_no_citations_section(self, tmp_path):
        md_path = tmp_path / "no-citations.md"
        md_path.write_text(SAMPLE_MD_NO_CITATIONS)

        result = extract_component_citations(md_path, "no-citations")
        assert result.valid_count == 0
        assert len(result.errors) == 1


class TestBuildCitationsIndex:
    def test_full_pipeline(self, tmp_path):
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()

        # Write two analysis files
        (analyses_dir / "my-library.md").write_text(SAMPLE_MD_WITH_CITATIONS)
        (analyses_dir / "my-app.md").write_text(SAMPLE_MD_NO_CITATIONS)

        index = build_citations_index(
            analyses_dir=analyses_dir,
            source_repo="https://github.com/org/repo",
            source_commit="abc123",
        )

        # Check metadata
        meta = index["metadata"]
        assert meta["total_citations"] == 2
        assert meta["components_with_citations"] == 1
        assert meta["components_without_citations"] == 1
        assert meta["components_analyzed"] == 2
        assert meta["source_repo"] == "https://github.com/org/repo"
        assert meta["source_commit"] == "abc123"

        # Check by_component
        assert "my-library" in index["by_component"]
        assert len(index["by_component"]["my-library"]) == 2
        assert "my-app" not in index["by_component"]

        # Check all_citations flat list
        assert len(index["all_citations"]) == 2
        for c in index["all_citations"]:
            assert "component" in c
            assert "source_url" in c
            assert "github.com" in c["source_url"]

        # Check per-component JSON file was written
        lib_citations_path = analyses_dir / "my-library.citations.json"
        assert lib_citations_path.exists()
        lib_data = json.loads(lib_citations_path.read_text())
        assert lib_data["component"] == "my-library"
        assert lib_data["citation_count"] == 2
        assert lib_data["source_repo"] == "https://github.com/org/repo"

        # Check aggregated index file
        all_path = analyses_dir / "all_citations.json"
        assert all_path.exists()
        all_data = json.loads(all_path.read_text())
        assert all_data["metadata"]["total_citations"] == 2

    def test_empty_directory(self, tmp_path):
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()

        index = build_citations_index(analyses_dir=analyses_dir)
        assert index["metadata"]["total_citations"] == 0
        assert index["metadata"]["components_analyzed"] == 0

    def test_source_url_enrichment(self, tmp_path):
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()
        (analyses_dir / "lib.md").write_text(SAMPLE_MD_WITH_CITATIONS)

        index = build_citations_index(
            analyses_dir=analyses_dir,
            source_repo="https://github.com/myorg/myrepo",
            source_commit="deadbeef",
        )

        citation = index["all_citations"][0]
        assert citation["source_url"] == (
            "https://github.com/myorg/myrepo/blob/deadbeef/src/config.rs#L1-L15"
        )
