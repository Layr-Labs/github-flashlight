"""Tests for Python language discovery plugin."""

import pytest
from pathlib import Path

from agent.discovery.languages.python import PythonPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return PythonPlugin()


@pytest.fixture
def repo(tmp_path):
    class Repo:
        root = tmp_path

        def write(self, path: str, content: str):
            p = tmp_path / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return p

    return Repo()


class TestPyprojectToml:
    def test_basic_library(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "my-utils"
description = "Utility functions"

[build-system]
requires = ["setuptools"]
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "my-utils"
        assert comps[0].kind == ComponentKind.LIBRARY

    def test_cli_with_scripts(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "my-cli"
description = "CLI tool"

[project.scripts]
mycli = "my_cli:main"
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert comps[0].kind == ComponentKind.CLI

    def test_service_with_fastapi(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "my-api"
description = "API server"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn",
]

[project.scripts]
serve = "my_api:main"
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE

    def test_pipeline_with_airflow(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "etl-pipeline"
description = "Data pipeline"
dependencies = [
    "apache-airflow>=2.0",
]
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert comps[0].kind == ComponentKind.PIPELINE

    def test_frontend_with_streamlit(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "dashboard"
description = "Analytics dashboard"
dependencies = [
    "streamlit>=1.0",
]
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert comps[0].kind == ComponentKind.FRONTEND

    def test_extracts_dependencies(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "my-lib"
dependencies = [
    "requests>=2.28",
    "pydantic>=1.10",
    "click",
]
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        dep_names = {d.name for d in comps[0].external_dependencies}
        assert "requests" in dep_names
        assert "pydantic" in dep_names
        assert "click" in dep_names

    def test_extracts_name_and_description(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "awesome-lib"
description = "An awesome library"
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert comps[0].name == "awesome-lib"
        assert comps[0].description == "An awesome library"

    def test_subdirectory_manifest(self, plugin, repo):
        repo.write("libs/mylib/pyproject.toml", """
[project]
name = "mylib"
""")
        comps = plugin.parse_manifest(
            repo.root / "libs/mylib/pyproject.toml", repo.root
        )
        assert comps[0].root_path == "libs/mylib"


class TestSubpackageDiscovery:
    """Splits a monolithic Python package into sub-package components."""

    def _write_flat_layout(self, repo, project_name="myapp"):
        """Build a flat-layout project with 3 sub-packages: api, engine, cache."""
        repo.write("pyproject.toml", f"""
[project]
name = "{project_name}"
description = "An app"
""")
        # Top-level package files
        repo.write(f"{project_name}/__init__.py", "")
        repo.write(f"{project_name}/cli.py", "print('cli')")

        # Sub-package: api (imports engine + cache)
        repo.write(f"{project_name}/api/__init__.py", "")
        repo.write(
            f"{project_name}/api/routes.py",
            f"from {project_name}.engine import Engine\n"
            f"from ..cache import Cache\n",
        )

        # Sub-package: engine (imports cache)
        repo.write(f"{project_name}/engine/__init__.py", "")
        repo.write(
            f"{project_name}/engine/core.py",
            f"from {project_name}.cache import Cache\n",
        )

        # Sub-package: cache (no internal deps)
        repo.write(f"{project_name}/cache/__init__.py", "")
        repo.write(f"{project_name}/cache/lru.py", "class Cache: pass")

    def test_flat_layout_splits_into_subpackages(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)

        # Root + 3 sub-packages
        assert len(comps) == 4
        names = {c.name for c in comps}
        assert names == {"myapp", "api", "engine", "cache"}

    def test_subpackage_absolute_import_edges(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}

        # engine -> cache (absolute import: from myapp.cache)
        assert by_name["engine"].internal_dependencies == ["cache"]
        # cache has no internal deps
        assert by_name["cache"].internal_dependencies == []

    def test_subpackage_relative_import_edges(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}

        # api -> engine (absolute) and api -> cache (relative: from ..cache)
        assert set(by_name["api"].internal_dependencies) == {"engine", "cache"}

    def test_root_links_to_subpackages(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}

        # Root component's internal_dependencies include every sub-package
        assert set(by_name["myapp"].internal_dependencies) >= {"api", "engine", "cache"}

    def test_subpackage_root_paths(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}

        assert by_name["api"].root_path == "myapp/api"
        assert by_name["engine"].root_path == "myapp/engine"
        assert by_name["cache"].root_path == "myapp/cache"

    def test_subpackage_manifest_path_points_to_root_pyproject(self, plugin, repo):
        self._write_flat_layout(repo, "myapp")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)

        for c in comps:
            assert c.manifest_path == "pyproject.toml"

    def test_src_layout_splits_into_subpackages(self, plugin, repo):
        """src/<pkg>/<subpkg>/ layout is also supported."""
        repo.write("pyproject.toml", """
[project]
name = "srcapp"
""")
        repo.write("src/srcapp/__init__.py", "")
        repo.write("src/srcapp/api/__init__.py", "")
        repo.write("src/srcapp/api/routes.py", "x = 1")
        repo.write("src/srcapp/engine/__init__.py", "")
        repo.write("src/srcapp/engine/core.py", "y = 2")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        names = {c.name for c in comps}
        assert {"srcapp", "api", "engine"} <= names

        by_name = {c.name: c for c in comps}
        assert by_name["api"].root_path == "src/srcapp/api"

    def test_hyphenated_project_name_maps_to_underscored_dir(self, plugin, repo):
        """A project named 'my-app' lives in 'my_app/' on disk."""
        repo.write("pyproject.toml", """
[project]
name = "my-app"
""")
        repo.write("my_app/__init__.py", "")
        repo.write("my_app/alpha/__init__.py", "")
        repo.write("my_app/alpha/a.py", "x = 1")
        repo.write("my_app/beta/__init__.py", "")
        repo.write("my_app/beta/b.py", "y = 2")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        names = {c.name for c in comps}
        assert {"alpha", "beta"} <= names

    def test_skips_when_only_one_subpackage(self, plugin, repo):
        """Fewer than MIN_SUB_PACKAGES_TO_SPLIT sub-packages keeps single-component behavior."""
        repo.write("pyproject.toml", """
[project]
name = "tinyapp"
""")
        repo.write("tinyapp/__init__.py", "")
        repo.write("tinyapp/main.py", "print('hi')")
        repo.write("tinyapp/onlysub/__init__.py", "")
        repo.write("tinyapp/onlysub/thing.py", "x = 1")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "tinyapp"

    def test_skips_when_no_source_package(self, plugin, repo):
        """No source tree on disk => single root component, no sub-packages."""
        repo.write("pyproject.toml", """
[project]
name = "ghost"
""")
        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "ghost"

    def test_skips_tests_and_private_dirs(self, plugin, repo):
        """tests/, _private/, __pycache__/ etc. don't become components."""
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        # These three should become components
        repo.write("app/alpha/__init__.py", "")
        repo.write("app/alpha/a.py", "x = 1")
        repo.write("app/beta/__init__.py", "")
        repo.write("app/beta/b.py", "y = 2")
        # These should NOT
        repo.write("app/tests/__init__.py", "")
        repo.write("app/tests/test_alpha.py", "pass")
        repo.write("app/_internal/__init__.py", "")
        repo.write("app/_internal/helpers.py", "pass")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        sub_names = {c.name for c in comps if c.name != "app"}
        assert sub_names == {"alpha", "beta"}

    def test_skips_subpackage_with_too_few_files(self, plugin, repo):
        """A sub-package dir with only __init__.py is ignored."""
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        repo.write("app/real/__init__.py", "")
        repo.write("app/real/real.py", "x = 1")
        repo.write("app/another/__init__.py", "")
        repo.write("app/another/another.py", "y = 2")
        # Too-small dir: only __init__.py
        repo.write("app/stub/__init__.py", "")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        sub_names = {c.name for c in comps if c.name != "app"}
        assert sub_names == {"real", "another"}
        assert "stub" not in sub_names

    def test_subpackage_classification_service(self, plugin, repo):
        """A sub-package with FastAPI routes is classified SERVICE."""
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        repo.write("app/api/__init__.py", "")
        repo.write(
            "app/api/server.py",
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return 'ok'\n",
        )
        # Another plain library sub-package so we meet MIN_SUB_PACKAGES_TO_SPLIT
        repo.write("app/lib/__init__.py", "")
        repo.write("app/lib/stuff.py", "x = 1")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}
        assert by_name["api"].kind == ComponentKind.SERVICE
        assert by_name["lib"].kind == ComponentKind.LIBRARY

    def test_subpackage_classification_cli(self, plugin, repo):
        """A sub-package with argparse + main guard is classified CLI."""
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        repo.write("app/tool/__init__.py", "")
        repo.write(
            "app/tool/__main__.py",
            "import argparse\n"
            "def main():\n"
            "    parser = argparse.ArgumentParser()\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
        )
        repo.write("app/tool/helpers.py", "def h(): pass")
        repo.write("app/lib/__init__.py", "")
        repo.write("app/lib/stuff.py", "x = 1")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}
        assert by_name["tool"].kind == ComponentKind.CLI

    def test_external_deps_only_on_root(self, plugin, repo):
        """Module-level external deps are declared once on the root component."""
        repo.write("pyproject.toml", """
[project]
name = "app"
dependencies = [
    "requests>=2",
    "pydantic",
]
""")
        repo.write("app/__init__.py", "")
        repo.write("app/alpha/__init__.py", "")
        repo.write("app/alpha/a.py", "x = 1")
        repo.write("app/beta/__init__.py", "")
        repo.write("app/beta/b.py", "y = 2")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}
        root_deps = {d.name for d in by_name["app"].external_dependencies}
        assert "requests" in root_deps
        assert "pydantic" in root_deps
        # Sub-packages don't duplicate module-level deps
        assert by_name["alpha"].external_dependencies == []
        assert by_name["beta"].external_dependencies == []

    def test_classification_ignores_framework_names_in_comments(self, plugin, repo):
        """Substring matches in docstrings/comments must NOT trigger misclassification.

        Regression test: 'dashboard' should not match the 'dash' frontend
        framework marker; only real `import dash` statements should.
        """
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        repo.write("app/alpha/__init__.py", "")
        repo.write(
            "app/alpha/a.py",
            '"""A dashboard-adjacent utility module."""\n'
            "# This has nothing to do with the dash framework.\n"
            "def helper():\n"
            "    return 42\n",
        )
        repo.write("app/beta/__init__.py", "")
        repo.write("app/beta/b.py", "class Thing: pass")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}
        # Without the word-boundary fix, 'alpha' would be misclassified as FRONTEND
        assert by_name["alpha"].kind == ComponentKind.LIBRARY

    def test_subpackage_metadata_links_back_to_parent(self, plugin, repo):
        repo.write("pyproject.toml", """
[project]
name = "app"
""")
        repo.write("app/__init__.py", "")
        repo.write("app/alpha/__init__.py", "")
        repo.write("app/alpha/a.py", "x = 1")
        repo.write("app/beta/__init__.py", "")
        repo.write("app/beta/b.py", "y = 2")

        comps = plugin.parse_manifest(repo.root / "pyproject.toml", repo.root)
        by_name = {c.name: c for c in comps}
        assert by_name["alpha"].metadata.get("parent_package") == "app"
        assert by_name["beta"].metadata.get("parent_package") == "app"
