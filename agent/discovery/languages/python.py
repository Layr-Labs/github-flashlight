"""Python language discovery plugin."""

import re
from pathlib import Path
from typing import List

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency


class PythonPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "Python"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/pyproject.toml", "**/setup.py"]

    @property
    def exclude_patterns(self) -> List[str]:
        return [
            "**/venv/**", "**/.venv/**", "**/env/**",
            "**/__pycache__/**", "**/.git/**", "**/node_modules/**",
            "**/.tox/**", "**/.eggs/**",
        ]

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        if manifest_path.name == "pyproject.toml":
            return self._parse_pyproject(manifest_path, repo_root)
        return []  # setup.py parsing is complex; skip for now

    def _parse_pyproject(self, path: Path, repo_root: Path) -> List[Component]:
        text = path.read_text(encoding="utf-8", errors="replace")
        component_root = path.parent
        rel_root = str(component_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        name = self._extract_field(text, "name") or component_root.name
        description = self._extract_field(text, "description") or ""

        # Parse dependencies
        external_deps = self._extract_dependencies(text)
        internal_deps = self._find_internal_deps(text, repo_root, component_root)

        # Classify
        kind = self._classify(text, component_root)

        return [Component(
            name=name,
            kind=kind,
            type="python-package",
            root_path=rel_root or ".",
            manifest_path=str(path.relative_to(repo_root)),
            description=description,
            internal_dependencies=internal_deps,
            external_dependencies=external_deps,
        )]

    def _extract_field(self, text: str, field: str) -> str:
        """Extract a simple string field from pyproject.toml."""
        # Match: name = "value" or name = 'value'
        pattern = rf'^\s*{field}\s*=\s*["\']([^"\']+)["\']'
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1) if match else ""

    def _extract_dependencies(self, text: str) -> List[ExternalDependency]:
        """Extract dependencies from [project.dependencies] or [tool.poetry.dependencies]."""
        deps: List[ExternalDependency] = []

        # Find [project] dependencies array
        dep_match = re.search(
            r'\[project\].*?dependencies\s*=\s*\[(.*?)\]',
            text, re.DOTALL
        )
        if dep_match:
            dep_block = dep_match.group(1)
            for line in dep_block.splitlines():
                line = line.strip().strip(',"\'')
                if not line or line.startswith("#"):
                    continue
                # Parse "package>=1.0" or "package" or "package[extra]>=1.0"
                match = re.match(r'^([a-zA-Z0-9_-]+)(?:\[.*?\])?\s*(.*)$', line)
                if match:
                    pkg_name = match.group(1)
                    version = match.group(2).strip().strip(',"\'')
                    deps.append(ExternalDependency(name=pkg_name, version=version))

        # Fallback: try [tool.poetry.dependencies]
        if not deps:
            poetry_match = re.search(
                r'\[tool\.poetry\.dependencies\](.*?)(?:\[|\Z)',
                text, re.DOTALL
            )
            if poetry_match:
                for line in poetry_match.group(1).splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#") and not line.startswith("python"):
                        parts = line.split("=", 1)
                        pkg_name = parts[0].strip()
                        version = parts[1].strip().strip('"\'{}')
                        deps.append(ExternalDependency(name=pkg_name, version=version))

        return deps

    def _find_internal_deps(
        self, text: str, repo_root: Path, component_root: Path
    ) -> List[str]:
        """Find internal (workspace) dependencies."""
        internal: List[str] = []

        # Look for path dependencies in pyproject.toml
        # e.g., my-lib = {path = "../my-lib"}
        for match in re.finditer(r'(\w[\w-]*)\s*=\s*\{[^}]*path\s*=\s*["\']([^"\']+)', text):
            dep_name = match.group(1)
            internal.append(dep_name)

        return internal

    def _classify(self, text: str, component_root: Path) -> ComponentKind:
        """Classify a Python package."""
        text_lower = text.lower()

        # Has CLI scripts?
        has_scripts = bool(re.search(r'\[project\.scripts\]', text))
        has_gui_scripts = bool(re.search(r'\[project\.gui-scripts\]', text))
        has_entry_points = bool(re.search(r'\[project\.entry-points\]', text))

        # Has __main__.py?
        has_main = any(
            (component_root / pkg / "__main__.py").exists()
            for pkg in component_root.iterdir()
            if pkg.is_dir() and not pkg.name.startswith(".")
        )

        # Check for web framework markers
        web_frameworks = [
            "fastapi", "flask", "django", "starlette", "sanic",
            "aiohttp", "tornado", "uvicorn", "gunicorn",
        ]
        is_web = any(fw in text_lower for fw in web_frameworks)

        # Check for pipeline markers
        pipeline_markers = ["airflow", "dagster", "prefect", "dbt", "luigi"]
        is_pipeline = any(m in text_lower for m in pipeline_markers)

        # Check for frontend markers
        frontend_markers = ["streamlit", "gradio", "panel", "dash"]
        is_frontend = any(m in text_lower for m in frontend_markers)

        if is_pipeline:
            return ComponentKind.PIPELINE
        if is_frontend:
            return ComponentKind.FRONTEND
        if is_web and (has_scripts or has_main):
            return ComponentKind.SERVICE
        if has_scripts or has_main:
            return ComponentKind.CLI
        if has_gui_scripts:
            return ComponentKind.FRONTEND
        return ComponentKind.LIBRARY
