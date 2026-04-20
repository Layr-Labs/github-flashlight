"""Python language discovery plugin.

Handles two patterns:
1. Multi-manifest repos: each pyproject.toml is a separate component.
2. Single-package monoliths (common in Python): one pyproject.toml at
   the repo root with a source tree containing multiple top-level
   sub-packages (e.g., omlx/engine, omlx/api, omlx/cache). The plugin
   scans imports via AST to discover these sub-packages and traces
   their internal dependency edges, mirroring the Go plugin's approach
   for single-module monorepos.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency

logger = logging.getLogger(__name__)

# Directory names inside a source package that should NOT be treated as
# sub-package components (they aren't logical subsystems).
SUB_PACKAGE_SKIP_DIRS = {
    "tests", "test", "_tests", "_test", "testing",
    "__pycache__", "migrations", "fixtures",
}

# A candidate sub-package must have at least this many .py files (inclusive
# of __init__.py) to be emitted as its own component. Filters out namespace
# shims that just re-export other packages.
MIN_SUB_PACKAGE_PY_FILES = 2

# Minimum number of sub-packages required before we bother splitting the
# project. Below this, a single root component is more informative.
MIN_SUB_PACKAGES_TO_SPLIT = 2


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

        # Classify root component from the manifest
        kind = self._classify(text, component_root)

        # Attempt to split into sub-packages. For monolithic Python packages
        # with a substantial internal module tree, this yields one Component
        # per top-level sub-package plus a root Component.
        subpackage_components = self._discover_subpackages(
            component_root=component_root,
            repo_root=repo_root,
            project_name=name,
            manifest_path=path,
        )

        root_component = Component(
            name=name,
            kind=kind,
            type="python-package",
            root_path=rel_root or ".",
            manifest_path=str(path.relative_to(repo_root)),
            description=description,
            internal_dependencies=sorted(
                set(internal_deps) | {c.name for c in subpackage_components}
            ),
            external_dependencies=external_deps,
        )

        return [root_component] + subpackage_components

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
        """Find internal (workspace) dependencies declared in the manifest."""
        internal: List[str] = []

        # Look for path dependencies in pyproject.toml
        # e.g., my-lib = {path = "../my-lib"}
        for match in re.finditer(r'(\w[\w-]*)\s*=\s*\{[^}]*path\s*=\s*["\']([^"\']+)', text):
            dep_name = match.group(1)
            internal.append(dep_name)

        return internal

    def _classify(self, text: str, component_root: Path) -> ComponentKind:
        """Classify a Python package from manifest-level signals."""
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

    # ------------------------------------------------------------------
    # Sub-package discovery (for monolithic Python packages)
    # ------------------------------------------------------------------

    def _discover_subpackages(
        self,
        component_root: Path,
        repo_root: Path,
        project_name: str,
        manifest_path: Path,
    ) -> List[Component]:
        """Emit Components for top-level sub-packages inside the main source tree.

        For a flat-layout project like:
            pyproject.toml  (name = "omlx")
            omlx/
              __init__.py
              cli.py
              engine/
                __init__.py
                core.py
              api/
                __init__.py
                routes.py

        This yields Components for ``engine`` and ``api``. Import edges between
        them are traced via AST (both absolute and relative imports).

        Returns an empty list if the project doesn't meet the monolithic-
        package pattern (no source tree, <2 sub-packages, etc.).
        """
        src_root = self._find_source_package(component_root, project_name)
        if src_root is None:
            return []

        # Collect candidate sub-package directories
        candidates: List[Path] = []
        for entry in sorted(src_root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in SUB_PACKAGE_SKIP_DIRS:
                continue
            if entry.name.startswith(".") or entry.name.startswith("_"):
                # Skip dunder and private dirs (e.g., __pycache__, _internal)
                continue
            if not (entry / "__init__.py").exists():
                continue
            py_files = [p for p in entry.rglob("*.py") if "__pycache__" not in p.parts]
            if len(py_files) < MIN_SUB_PACKAGE_PY_FILES:
                continue
            candidates.append(entry)

        if len(candidates) < MIN_SUB_PACKAGES_TO_SPLIT:
            return []

        src_pkg_name = src_root.name  # e.g., "omlx"
        candidate_names = {c.name for c in candidates}
        manifest_rel = str(manifest_path.relative_to(repo_root))

        # Resolve cross-package imports for each candidate
        components: List[Component] = []
        for sub_dir in candidates:
            resolved_imports = self._scan_python_imports(sub_dir, src_root)

            # Keep imports that point at a sibling sub-package
            internal: Set[str] = set()
            for imp in resolved_imports:
                parts = imp.split(".")
                if (
                    len(parts) >= 2
                    and parts[0] == src_pkg_name
                    and parts[1] in candidate_names
                    and parts[1] != sub_dir.name
                ):
                    internal.add(parts[1])

            kind = self._classify_subpackage(sub_dir)

            components.append(Component(
                name=sub_dir.name,
                kind=kind,
                type="python-package",
                root_path=str(sub_dir.relative_to(repo_root)),
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=sorted(internal),
                # Module-level external deps are declared once on the root
                # component; intentionally left empty here to avoid duplication.
                external_dependencies=[],
                metadata={"parent_package": project_name},
            ))

        return components

    def _find_source_package(
        self, component_root: Path, project_name: str
    ) -> Optional[Path]:
        """Locate the source package directory for a project.

        Tries (in order):
          1. ``<component_root>/src/<project_name>/``           (src-layout, PEP 518)
          2. ``<component_root>/<project_name>/``               (flat-layout)
          3. ``<component_root>/src/<project_name_underscored>/``
          4. ``<component_root>/<project_name_underscored>/``

        Returns the first directory that exists and contains ``__init__.py``.
        """
        name_underscored = project_name.replace("-", "_")
        candidates = [
            component_root / "src" / project_name,
            component_root / project_name,
            component_root / "src" / name_underscored,
            component_root / name_underscored,
        ]
        for c in candidates:
            if c.is_dir() and (c / "__init__.py").exists():
                return c
        return None

    def _scan_python_imports(
        self, sub_dir: Path, src_root: Path
    ) -> Set[str]:
        """AST-parse every .py file in ``sub_dir`` and return resolved import paths.

        Both absolute (``from foo.bar import X``) and relative
        (``from ..bar import X``) imports are returned in absolute dotted form
        relative to ``src_root.parent`` (e.g., ``omlx.engine.core``).
        """
        src_package_parent = src_root.parent  # dir that contains the top-level package
        imports: Set[str] = set()

        for py_file in sub_dir.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, OSError):
                continue

            # Compute dotted module path for this file (needed for relative resolution)
            try:
                rel = py_file.relative_to(src_package_parent)
            except ValueError:
                continue
            module_parts = list(rel.with_suffix("").parts)
            # If file is <pkg>/foo/__init__.py, its module is <pkg>.foo
            if module_parts and module_parts[-1] == "__init__":
                module_parts = module_parts[:-1]

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name:
                            imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    level = node.level or 0
                    if level == 0:
                        # Absolute import: `from foo.bar import X`
                        if node.module:
                            imports.add(node.module)
                    else:
                        # Relative import: `from ..bar import X`
                        # Resolve against the importing module's parent package
                        base = module_parts[: max(0, len(module_parts) - level)]
                        if node.module:
                            resolved = base + node.module.split(".")
                        else:
                            resolved = base
                        if resolved:
                            imports.add(".".join(resolved))

        return imports

    def _classify_subpackage(self, sub_dir: Path) -> ComponentKind:
        """Classify a sub-package by scanning a bounded sample of its source.

        Framework detection uses word-boundary regex matching on ``import``
        statements specifically, to avoid false positives from substrings in
        comments or docstrings (e.g., "dash" matching "dashboard").
        """
        web_frameworks = ("fastapi", "flask", "django", "starlette", "sanic", "aiohttp", "tornado")
        cli_frameworks = ("argparse", "click", "typer", "docopt", "fire")
        pipeline_markers = ("airflow", "dagster", "prefect", "luigi", "dbt")
        frontend_markers = ("streamlit", "gradio", "panel", "dash")

        # Read up to 20 files, capped at 4 KB each — enough to catch framework
        # imports and route decorators without scanning massive test fixtures.
        sampled = ""
        for py_file in list(sub_dir.rglob("*.py"))[:20]:
            if "__pycache__" in py_file.parts:
                continue
            try:
                sampled += py_file.read_text(encoding="utf-8", errors="replace")[:4000]
                sampled += "\n"
            except OSError:
                continue

        if not sampled:
            return ComponentKind.LIBRARY

        def has_import_of(markers: Tuple[str, ...]) -> bool:
            # Match `import <marker>` or `from <marker>[...] import ...`
            # Requires word boundary after the marker so `dash` doesn't match `dashboard`.
            pattern = (
                r"(?m)^\s*(?:from|import)\s+("
                + "|".join(re.escape(m) for m in markers)
                + r")\b"
            )
            return bool(re.search(pattern, sampled))

        is_pipeline = has_import_of(pipeline_markers)
        is_frontend = has_import_of(frontend_markers)
        is_service = has_import_of(web_frameworks) and bool(
            re.search(
                r"(app\s*=\s*(FastAPI|Flask|Starlette|Sanic)|@(?:app|router|bp)\.(?:get|post|put|delete|patch|route))",
                sampled,
            )
        )
        is_cli = has_import_of(cli_frameworks) and bool(
            re.search(
                r"(argparse\.ArgumentParser|@click\.(?:command|group)|@app\.command|typer\.Typer|if\s+__name__\s*==\s*[\"']__main__[\"'])",
                sampled,
            )
        )

        if is_pipeline:
            return ComponentKind.PIPELINE
        if is_frontend:
            return ComponentKind.FRONTEND
        if is_service:
            return ComponentKind.SERVICE
        if is_cli:
            return ComponentKind.CLI
        return ComponentKind.LIBRARY
