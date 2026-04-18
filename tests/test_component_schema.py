"""Tests for Component schema and ComponentKind."""

import pytest

from agent.schemas.core import (
    Component,
    ComponentKind,
    LanguageType,
    ExternalDependency,
    CodeCitation,
    component_from_dict,
)


class TestComponentKind:
    def test_all_values(self):
        assert ComponentKind.LIBRARY.value == "library"
        assert ComponentKind.SERVICE.value == "service"
        assert ComponentKind.CLI.value == "cli"
        assert ComponentKind.CONTRACT.value == "contract"
        assert ComponentKind.INFRA.value == "infra"
        assert ComponentKind.PIPELINE.value == "pipeline"
        assert ComponentKind.FRONTEND.value == "frontend"
        assert ComponentKind.UNKNOWN.value == "unknown"

    def test_from_str_valid(self):
        assert ComponentKind.from_str("library") == ComponentKind.LIBRARY
        assert ComponentKind.from_str("service") == ComponentKind.SERVICE
        assert ComponentKind.from_str("cli") == ComponentKind.CLI

    def test_from_str_case_insensitive(self):
        assert ComponentKind.from_str("LIBRARY") == ComponentKind.LIBRARY
        assert ComponentKind.from_str("Service") == ComponentKind.SERVICE

    def test_from_str_unknown_fallback(self):
        assert ComponentKind.from_str("garbage") == ComponentKind.UNKNOWN
        assert ComponentKind.from_str("") == ComponentKind.UNKNOWN
        assert ComponentKind.from_str("application") == ComponentKind.UNKNOWN


class TestComponent:
    def test_roundtrip(self):
        c = Component(
            name="core",
            kind=ComponentKind.LIBRARY,
            type="go-module",
            root_path="core",
            manifest_path="go.mod",
            description="Core types",
            internal_dependencies=["common"],
            external_dependencies=[
                ExternalDependency(name="serde", version="1.0"),
            ],
            key_files=["core/types.go"],
            metadata={"custom": True},
        )
        d = c.to_dict()
        c2 = Component.from_dict(d)

        assert c2.name == "core"
        assert c2.kind == ComponentKind.LIBRARY
        assert c2.type == "go-module"
        assert c2.root_path == "core"
        assert c2.internal_dependencies == ["common"]
        assert len(c2.external_dependencies) == 1
        assert c2.external_dependencies[0].name == "serde"
        assert c2.key_files == ["core/types.go"]
        assert c2.metadata == {"custom": True}

    def test_to_dict_includes_kind(self):
        c = Component(name="a", kind=ComponentKind.SERVICE, type="t", root_path=".")
        d = c.to_dict()
        assert d["kind"] == "service"

    def test_to_dict_no_classification(self):
        """to_dict should not include legacy 'classification' field."""
        lib = Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path=".")
        assert "classification" not in lib.to_dict()

        svc = Component(name="b", kind=ComponentKind.SERVICE, type="t", root_path=".")
        assert "classification" not in svc.to_dict()

    def test_from_dict_with_kind(self):
        d = {"name": "a", "kind": "cli", "type": "t", "root_path": "."}
        c = Component.from_dict(d)
        assert c.kind == ComponentKind.CLI

    def test_from_dict_no_kind(self):
        d = {"name": "a", "type": "t", "root_path": "."}
        c = Component.from_dict(d)
        assert c.kind == ComponentKind.UNKNOWN

    def test_is_library(self):
        lib = Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path=".")
        svc = Component(name="b", kind=ComponentKind.SERVICE, type="t", root_path=".")
        assert lib.is_library is True
        assert svc.is_library is False

    def test_is_executable(self):
        lib = Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path=".")
        svc = Component(name="b", kind=ComponentKind.SERVICE, type="t", root_path=".")
        cli = Component(name="c", kind=ComponentKind.CLI, type="t", root_path=".")
        fe = Component(name="d", kind=ComponentKind.FRONTEND, type="t", root_path=".")
        contract = Component(
            name="e", kind=ComponentKind.CONTRACT, type="t", root_path="."
        )

        assert lib.is_executable is False
        assert svc.is_executable is True
        assert cli.is_executable is True
        assert fe.is_executable is True
        assert contract.is_executable is False

    def test_optional_fields_omitted(self):
        c = Component(name="a", kind=ComponentKind.LIBRARY, type="t", root_path=".")
        d = c.to_dict()
        assert "manifest_path" not in d  # Empty string omitted
        assert "metadata" not in d  # Empty dict omitted
        assert "citations" not in d  # Empty list omitted


class TestComponentFromDict:
    def test_factory_function(self):
        d = {"name": "a", "kind": "cli", "type": "t", "root_path": "."}
        c = component_from_dict(d)
        assert isinstance(c, Component)
        assert c.kind == ComponentKind.CLI


class TestExternalDependency:
    def test_from_string(self):
        d = ExternalDependency.from_dict("serde")
        assert d.name == "serde"
        assert d.version == ""

    def test_from_dict_full(self):
        d = ExternalDependency.from_dict(
            {
                "name": "tokio",
                "version": "1.35",
                "category": "async-runtime",
                "purpose": "Async runtime",
            }
        )
        assert d.name == "tokio"
        assert d.version == "1.35"
        assert d.category == "async-runtime"

    def test_roundtrip(self):
        d = ExternalDependency(name="serde", version="1.0", category="serialization")
        d2 = ExternalDependency.from_dict(d.to_dict())
        assert d2.name == d.name
        assert d2.version == d.version
        assert d2.category == d.category


class TestCodeCitation:
    def test_roundtrip(self):
        c = CodeCitation(
            file_path="src/main.rs",
            start_line=10,
            end_line=20,
            claim="Handles auth",
            section="Architecture",
        )
        c2 = CodeCitation.from_dict(c.to_dict())
        assert c2.file_path == c.file_path
        assert c2.start_line == c.start_line
        assert c2.end_line == c.end_line
        assert c2.claim == c.claim
        assert c2.section == c.section

    def test_markdown_single_line(self):
        c = CodeCitation(file_path="foo.go", start_line=5, end_line=5, claim="")
        assert c.to_markdown() == "`foo.go:5`"

    def test_markdown_range(self):
        c = CodeCitation(file_path="foo.go", start_line=5, end_line=15, claim="")
        assert c.to_markdown() == "`foo.go:5-15`"
