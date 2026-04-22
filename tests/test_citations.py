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
    strip_extracted_sections,
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


# ---------------------------------------------------------------------------
# component_root fallback resolution
#
# LLMs frequently emit citation paths that aren't repo-root-relative. The
# validator/extractor recover these using the component's root_path as a
# prefix candidate, with two strategies (suffix-overlap dedup, plain
# prepend). These tests pin each recovery path.
# ---------------------------------------------------------------------------


class TestComponentRootFallback:
    def _make_repo(self, tmp_path, relpath):
        full = tmp_path / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("content\n")
        return full

    def test_repo_root_relative_path_accepted_as_is(self, tmp_path):
        """If the LLM emits the canonical repo-root path, no rewrite happens."""
        self._make_repo(tmp_path, "omlx/models/base.py")
        raw = {
            "file_path": "omlx/models/base.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "base model",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert errors == []
        assert citation.file_path == "omlx/models/base.py"

    def test_plain_prepend_for_bare_filename(self, tmp_path):
        """Bare filename + component_root -> prepended full path."""
        self._make_repo(tmp_path, "omlx/models/base.py")
        raw = {
            "file_path": "base.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "base model",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert errors == []
        assert citation.file_path == "omlx/models/base.py"

    def test_suffix_overlap_dedup(self, tmp_path):
        """Path that repeats the component's directory name (a common LLM
        mistake) is merged via overlap dedup, not naive concat."""
        self._make_repo(tmp_path, "omlx/models/base.py")
        raw = {
            "file_path": "models/base.py",  # repeats last segment of component_root
            "start_line": 1,
            "end_line": 5,
            "claim": "base model",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert errors == []
        # NOT "omlx/models/models/base.py" — the dedup must win.
        assert citation.file_path == "omlx/models/base.py"

    def test_multi_segment_overlap(self, tmp_path):
        """A longer overlap should dedup correctly too."""
        self._make_repo(tmp_path, "pkg/auth/token/jwt.rs")
        raw = {
            "file_path": "auth/token/jwt.rs",
            "start_line": 1,
            "end_line": 5,
            "claim": "jwt",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="pkg/auth/token"
        )
        assert errors == []
        assert citation.file_path == "pkg/auth/token/jwt.rs"

    def test_leading_dot_slash_stripped(self, tmp_path):
        self._make_repo(tmp_path, "omlx/models/base.py")
        raw = {
            "file_path": "./base.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "base",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert errors == []
        assert citation.file_path == "omlx/models/base.py"

    def test_absolute_project_prefix_still_stripped(self, tmp_path):
        """The existing /tmp/*/project/ strip continues to work alongside
        the new component-root fallback."""
        self._make_repo(tmp_path, "omlx/models/base.py")
        raw = {
            "file_path": "/tmp/omlx/project/omlx/models/base.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "base",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert errors == []
        assert citation.file_path == "omlx/models/base.py"

    def test_unresolvable_path_still_errors(self, tmp_path):
        """If neither the bare path nor component-rooted variants exist,
        we keep the original error."""
        raw = {
            "file_path": "ghost/file.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "ghost",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=tmp_path, component_root="omlx/models"
        )
        assert citation is None
        assert any("does not exist" in e for e in errors)

    def test_component_root_unused_when_no_repo_root(self):
        """component_root only activates when repo_root is provided (i.e.
        when we're actually doing existence checks)."""
        raw = {
            "file_path": "models/base.py",
            "start_line": 1,
            "end_line": 5,
            "claim": "base",
        }
        citation, errors = validate_citation_dict(
            raw, repo_root=None, component_root="omlx/models"
        )
        assert errors == []
        # Path is passed through unchanged when we can't verify.
        assert citation.file_path == "models/base.py"

    def test_index_uses_component_roots_map(self, tmp_path):
        """build_citations_index threads component_roots through to the
        validator."""
        # Layout: repo with the component's real file
        (tmp_path / "omlx/models").mkdir(parents=True)
        (tmp_path / "omlx/models/base.py").write_text("x\n")

        # Analysis emits a component-relative path (the common failure mode)
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()
        (analyses_dir / "models.md").write_text(
            dedent(
                """
                # models

                ## Citations
                ```json
                [
                  {
                    "file_path": "base.py",
                    "start_line": 1,
                    "end_line": 5,
                    "claim": "entry",
                    "section": "Key Components"
                  }
                ]
                ```
                """
            )
        )

        index = build_citations_index(
            analyses_dir=analyses_dir,
            repo_root=tmp_path,
            component_roots={"models": "omlx/models"},
        )
        assert index["metadata"]["total_citations"] == 1
        assert index["all_citations"][0]["file_path"] == "omlx/models/base.py"

    def test_index_without_component_roots_still_works(self, tmp_path):
        """Backwards compatibility: callers that don't pass component_roots
        get the pre-existing behavior (path accepted as-is or rejected)."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src/main.rs").write_text("fn main() {}\n")

        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()
        (analyses_dir / "lib.md").write_text(
            dedent(
                """
                # lib

                ## Citations
                ```json
                [
                  {
                    "file_path": "src/main.rs",
                    "start_line": 1,
                    "end_line": 1,
                    "claim": "entry",
                    "section": "Key Components"
                  }
                ]
                ```
                """
            )
        )

        index = build_citations_index(
            analyses_dir=analyses_dir,
            repo_root=tmp_path,
            # no component_roots
        )
        assert index["metadata"]["total_citations"] == 1


# ---------------------------------------------------------------------------
# strip_extracted_sections — ensures the duplicated JSON blocks are removed
# from the human-facing Markdown after being lifted into sidecar files.
# ---------------------------------------------------------------------------


class TestStripExtractedSections:
    def test_strips_citations_section(self):
        md = SAMPLE_MD_WITH_CITATIONS
        cleaned = strip_extracted_sections(md)
        assert "## Citations" not in cleaned
        assert "```json" not in cleaned
        # Prose sections around the block are preserved.
        assert "## Architecture" in cleaned
        assert "## Analysis Summary" in cleaned

    def test_strips_analysis_data_section(self):
        md = dedent(
            """\
            # lib

            ## Architecture
            Prose.

            ## Analysis Data
            ```json
            {"summary": "x", "tech_stack": ["python"]}
            ```

            ## Citations
            ```json
            [{"file_path": "a.py", "start_line": 1, "end_line": 2, "claim": "c"}]
            ```
            """
        )
        cleaned = strip_extracted_sections(md)
        assert "## Analysis Data" not in cleaned
        assert "## Citations" not in cleaned
        assert "```json" not in cleaned
        assert "## Architecture" in cleaned

    def test_does_not_strip_analysis_summary(self):
        """Regex must not match ``## Analysis Summary`` (a common human section)."""
        md = SAMPLE_MD_WITH_CITATIONS
        cleaned = strip_extracted_sections(md)
        assert "## Analysis Summary" in cleaned

    def test_idempotent(self):
        md = SAMPLE_MD_WITH_CITATIONS
        once = strip_extracted_sections(md)
        twice = strip_extracted_sections(once)
        assert once == twice

    def test_no_change_when_no_sections(self):
        md = SAMPLE_MD_NO_CITATIONS
        cleaned = strip_extracted_sections(md)
        # Content survives; we only normalise trailing whitespace.
        assert cleaned.rstrip() == md.rstrip()

    def test_trailing_newline_normalised(self):
        cleaned = strip_extracted_sections(SAMPLE_MD_WITH_CITATIONS)
        assert cleaned.endswith("\n")
        assert not cleaned.endswith("\n\n\n")

    def test_build_index_strips_md_after_extraction(self, tmp_path):
        """End-to-end: running the pipeline removes the duplicated blocks
        from the Markdown while preserving the sidecar JSON."""
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()
        md_path = analyses_dir / "my-library.md"
        md_path.write_text(SAMPLE_MD_WITH_CITATIONS)

        build_citations_index(
            analyses_dir=analyses_dir,
            source_repo="https://github.com/org/repo",
            source_commit="abc",
        )

        # Sidecar was written
        sidecar = analyses_dir / "my-library.citations.json"
        assert sidecar.exists()

        # MD no longer contains the extracted sections
        cleaned_md = md_path.read_text()
        assert "## Citations" not in cleaned_md
        assert "```json" not in cleaned_md
        # Non-extracted prose is preserved
        assert "## Architecture" in cleaned_md

    def test_build_index_leaves_md_untouched_on_extraction_failure(self, tmp_path):
        """If extraction fails (e.g. invalid JSON), the MD must be left as-is
        so the malformed block is still visible for debugging."""
        analyses_dir = tmp_path / "service_analyses"
        analyses_dir.mkdir()
        md_path = analyses_dir / "bad.md"
        md_path.write_text(SAMPLE_MD_INVALID_JSON)
        original = md_path.read_text()

        build_citations_index(analyses_dir=analyses_dir)

        # MD unchanged
        assert md_path.read_text() == original
        # No sidecar written
        assert not (analyses_dir / "bad.citations.json").exists()
