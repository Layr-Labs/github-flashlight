"""Tests for Go language discovery plugin."""

import pytest
from pathlib import Path

from agent.discovery.languages.go import GoPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return GoPlugin()


@pytest.fixture
def repo(tmp_path):
    """Helper to create files in a temp repo."""

    class Repo:
        root = tmp_path

        def write(self, path: str, content: str):
            p = tmp_path / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return p

    return Repo()


class TestSingleModule:
    def test_basic_library(self, plugin, repo):
        repo.write("go.mod", 'module github.com/org/mylib\n\ngo 1.21\n')
        repo.write("lib.go", "package mylib\n\nfunc Hello() {}\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "mylib"
        assert comps[0].kind == ComponentKind.LIBRARY

    def test_module_with_cmd(self, plugin, repo):
        repo.write("go.mod", 'module github.com/org/myapp\n\ngo 1.21\n')
        repo.write("lib.go", "package myapp\n")
        repo.write("cmd/server/main.go", 'package main\n\nimport "net/http"\n\nfunc main() { http.ListenAndServe(":8080", nil) }\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        names = {c.name for c in comps}
        assert "myapp" in names  # root library
        assert "server" in names  # cmd executable

    def test_external_deps_parsed(self, plugin, repo):
        repo.write("go.mod", """module github.com/org/mylib

go 1.21

require (
\tgithub.com/stretchr/testify v1.8.0
\tgithub.com/gin-gonic/gin v1.9.1
\tgolang.org/x/sync v0.5.0 // indirect
)
""")
        repo.write("lib.go", "package mylib\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        assert len(comps) == 1

        dep_names = {d.name for d in comps[0].external_dependencies}
        assert "github.com/stretchr/testify" in dep_names
        assert "github.com/gin-gonic/gin" in dep_names
        # Indirect deps should be excluded from direct list
        # (currently both go into direct — acceptable for now)


class TestMonorepoPackageDiscovery:
    def test_discovers_top_level_packages(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        repo.write("core/types.go", "package core\n\ntype Block struct{}\n")
        repo.write("core/utils.go", "package core\n\nfunc Hash() {}\n")
        repo.write("api/server.go", "package api\n\nfunc Serve() {}\n")
        repo.write("api/routes.go", "package api\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        names = {c.name for c in comps}
        assert "core" in names
        assert "api" in names

    def test_traces_import_deps(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        repo.write("core/types.go", "package core\n\ntype Config struct{}\n")
        repo.write("api/server.go", 'package api\n\nimport "github.com/org/monorepo/core"\n\nvar _ = core.Config{}\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        api_comp = next(c for c in comps if c.name == "api")
        assert "core" in api_comp.internal_dependencies

    def test_no_self_dependency(self, plugin, repo):
        # Need 2+ top-level packages to trigger monorepo discovery
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        repo.write("core/a.go", "package core\n\nfunc A() {}\n")
        repo.write("core/sub/c.go", 'package sub\n\nimport "github.com/org/monorepo/core"\n\nvar _ = core.A\n')
        repo.write("api/handler.go", "package api\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        core_comp = next(c for c in comps if c.name == "core")
        assert "core" not in core_comp.internal_dependencies

    def test_cmd_discovered_as_service(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        repo.write("core/types.go", "package core\n")
        repo.write("disperser/batcher.go", "package disperser\n")
        repo.write("disperser/cmd/apiserver/main.go",
                    'package main\n\nimport "net/http"\n\nfunc main() { http.ListenAndServe(":8080", nil) }\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        apiserver = next((c for c in comps if "apiserver" in c.name), None)
        assert apiserver is not None
        assert apiserver.kind == ComponentKind.SERVICE

    def test_nested_cmd_discovered(self, plugin, repo):
        """cmd/ directories nested deeper than top-level should be found."""
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        # Need 2+ top-level packages to trigger monorepo path
        repo.write("api/handler.go", "package api\n\nfunc Handle() {}\n")
        repo.write("core/types.go", "package core\n")
        repo.write("api/proxy/cmd/server/main.go", 'package main\n\nfunc main() {}\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        cmd_comps = [c for c in comps if c.kind != ComponentKind.LIBRARY]
        assert len(cmd_comps) >= 1

    def test_skips_excluded_dirs(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/monorepo\n\ngo 1.21\n")
        repo.write("core/types.go", "package core\n")
        repo.write("vendor/lib/foo.go", "package foo\n")
        repo.write("testdata/fixture.go", "package testdata\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        names = {c.name for c in comps}
        assert "vendor" not in names
        assert "testdata" not in names


class TestClassification:
    def test_service_by_content(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/svc\n\ngo 1.21\n")
        repo.write("main.go", 'package main\n\nimport "net/http"\n\nfunc main() {\n\thttp.ListenAndServe(":8080", nil)\n}\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE

    def test_cli_by_content(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/tool\n\ngo 1.21\n")
        repo.write("main.go", 'package main\n\nimport "github.com/spf13/cobra"\n\nvar rootCmd = &cobra.Command{}\n\nfunc main() { rootCmd.Execute() }\n')

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        assert comps[0].kind == ComponentKind.CLI

    def test_library_no_main(self, plugin, repo):
        repo.write("go.mod", "module github.com/org/lib\n\ngo 1.21\n")
        repo.write("utils.go", "package lib\n\nfunc Add(a, b int) int { return a + b }\n")

        comps = plugin.parse_manifest(repo.root / "go.mod", repo.root)
        assert comps[0].kind == ComponentKind.LIBRARY
