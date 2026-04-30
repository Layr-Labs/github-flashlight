"""Tests for TypeScript/JavaScript language discovery plugin."""

import json
import pytest
from pathlib import Path

from agent.discovery.languages.typescript import TypeScriptPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return TypeScriptPlugin()


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


class TestBasicPackage:
    def test_library(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-utils",
            "version": "1.0.0",
            "main": "dist/index.js",
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "my-utils"
        assert comps[0].kind == ComponentKind.LIBRARY

    def test_cli_with_bin(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-cli",
            "bin": {"mycli": "dist/cli.js"},
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.CLI

    def test_frontend_with_react(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-app",
            "dependencies": {"react": "^18.0", "react-dom": "^18.0"},
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.FRONTEND

    def test_frontend_with_next(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-site",
            "dependencies": {"next": "^14.0", "react": "^18.0"},
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.FRONTEND

    def test_service_with_express(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "api-server",
            "main": "src/index.js",
            "scripts": {"start": "node src/index.js"},
            "dependencies": {"express": "^4.18"},
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE

    def test_typescript_detected(self, plugin, repo):
        repo.write_json("package.json", {"name": "ts-lib"})
        repo.write("tsconfig.json", "{}")

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].type == "typescript-package"

    def test_javascript_without_tsconfig(self, plugin, repo):
        repo.write_json("package.json", {"name": "js-lib"})

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].type == "javascript-package"


class TestWorkspaces:
    def test_workspace_discovers_members(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "monorepo",
            "private": True,
            "workspaces": ["packages/*"],
        })
        repo.write_json("packages/core/package.json", {
            "name": "@org/core",
            "version": "1.0.0",
        })
        repo.write_json("packages/cli/package.json", {
            "name": "@org/cli",
            "bin": {"mycli": "dist/index.js"},
        })

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        names = {c.name for c in comps}
        assert "@org/core" in names
        assert "@org/cli" in names
        # Root workspace package should NOT be included
        assert "monorepo" not in names

    def test_workspace_internal_deps(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "monorepo",
            "private": True,
            "workspaces": ["packages/*"],
        })
        repo.write_json("packages/core/package.json", {
            "name": "@org/core",
        })
        repo.write_json("packages/app/package.json", {
            "name": "@org/app",
            "dependencies": {"@org/core": "workspace:*"},
        })

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        app = next(c for c in comps if c.name == "@org/app")
        assert "@org/core" in app.internal_dependencies


class TestDependencyExtraction:
    def test_external_deps(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-app",
            "dependencies": {
                "express": "^4.18",
                "lodash": "^4.17",
            },
            "devDependencies": {
                "jest": "^29.0",
            },
        })
        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        dep_names = {d.name for d in comps[0].external_dependencies}
        assert "express" in dep_names
        assert "lodash" in dep_names
        # devDependencies should not be in external_dependencies
        assert "jest" not in dep_names


class TestCloudflareWorker:
    """Corpus finding: packages with wrangler.toml are deployed services."""

    def test_wrangler_toml_sets_service_kind(self, plugin, repo):
        repo.write_json("package.json", {
            "name": "my-worker",
            "scripts": {"deploy": "wrangler deploy", "dev": "wrangler dev"},
        })
        repo.write("wrangler.toml", 'name = "my-worker"\nmain = "src/index.ts"\n')
        repo.write("src/index.ts", "export default {}")

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE

    def test_wrangler_jsonc_also_detected(self, plugin, repo):
        repo.write_json("package.json", {"name": "my-worker"})
        repo.write("wrangler.jsonc", '{"name": "my-worker"}')

        comps = plugin.parse_manifest(repo.root / "package.json", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE
