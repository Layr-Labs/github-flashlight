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
