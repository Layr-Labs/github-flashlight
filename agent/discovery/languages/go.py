"""Go language discovery plugin.

Handles two patterns:
1. Multi-module repos: each go.mod is a separate component.
2. Single-module monorepos (e.g., eigenda): one go.mod at root, but
   top-level directories are logically separate packages. The plugin
   scans imports to discover these internal packages and traces their
   dependency edges.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency

logger = logging.getLogger(__name__)

# Directories to skip when scanning for Go packages
SKIP_DIRS = {
    "vendor", "testdata", "test", "tests", "docs", "scripts",
    "resources", "node_modules", ".git", "contracts", "rust",
    "venv", ".venv", "inabox", "tools", "subgraphs",
}

# Minimum number of .go files for a directory to be considered a package
MIN_GO_FILES = 1


class GoPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "Go"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/go.mod"]

    @property
    def exclude_patterns(self) -> List[str]:
        return ["**/vendor/**", "**/testdata/**", "**/.git/**"]

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        component_root = manifest_path.parent
        rel_root = str(component_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        text = manifest_path.read_text(encoding="utf-8", errors="replace")

        # Parse module path
        module_path = self._parse_module_path(text)
        if not module_path:
            return []

        # Parse go.mod dependencies (direct vs indirect)
        direct_deps, indirect_deps = self._parse_go_mod_deps(text, module_path)

        # Check if this is a single-module monorepo (go.mod at repo root with
        # multiple top-level Go package directories)
        if component_root == repo_root:
            packages = self._discover_packages(component_root, module_path)
            if len(packages) > 1:
                return self._build_package_components(
                    packages, component_root, repo_root,
                    module_path, manifest_path, direct_deps,
                )

        # Standard case: single component per go.mod
        short_name = module_path.rsplit("/", 1)[-1]
        kind = self._classify(component_root)

        components = [Component(
            name=short_name,
            kind=kind,
            type="go-module",
            root_path=rel_root or ".",
            manifest_path=str(manifest_path.relative_to(repo_root)),
            description="",
            internal_dependencies=[],
            external_dependencies=direct_deps,
        )]

        # Discover cmd/ subdirectories
        self._discover_cmd_components(
            component_root, repo_root, manifest_path,
            short_name, components,
        )

        return components

    # ------------------------------------------------------------------
    # Package-level discovery for single-module monorepos
    # ------------------------------------------------------------------

    def _discover_packages(
        self, repo_root: Path, module_path: str,
    ) -> Dict[str, Path]:
        """Find top-level directories that contain Go source files.

        Returns a dict of {package_name: directory_path}. A top-level `cmd/`
        dir is treated as a container, not a package — its children are
        handled by _build_package_components via the cmd/ recursion path.
        """
        packages: Dict[str, Path] = {}

        for entry in sorted(repo_root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue
            if entry.name == "cmd" and self._cmd_is_binary_container(entry):
                continue

            # Count .go files anywhere in this directory tree
            go_files = list(entry.rglob("*.go"))
            if len(go_files) >= MIN_GO_FILES:
                packages[entry.name] = entry

        return packages

    def _cmd_is_binary_container(self, cmd_dir: Path) -> bool:
        """True if `cmd/` holds one-or-more `cmd/<name>/main.go` binaries
        rather than a `cmd` Go package (cmd/*.go at the top level)."""
        has_top_level_go = any(f.is_file() for f in cmd_dir.glob("*.go"))
        if has_top_level_go:
            return False
        has_child_main = any(
            sub.is_dir() and (sub / "main.go").exists() for sub in cmd_dir.iterdir()
        )
        return has_child_main

    def _build_package_components(
        self,
        packages: Dict[str, Path],
        component_root: Path,
        repo_root: Path,
        module_path: str,
        manifest_path: Path,
        module_deps: List[ExternalDependency],
    ) -> List[Component]:
        """Build components for each discovered Go package.

        Traces imports across all .go files to determine internal dependency
        edges between packages.
        """
        components: List[Component] = []
        manifest_rel = str(manifest_path.relative_to(repo_root))

        # Scan all imports for each package
        package_imports: Dict[str, Set[str]] = {}
        for pkg_name, pkg_dir in packages.items():
            package_imports[pkg_name] = self._scan_imports(pkg_dir, module_path)

        # Scan all cmd/ directories recursively within each package AND
        # at the repo root. Handles: cmd/foo, pkg/cmd/foo, pkg/sub/cmd/bar.
        cmd_components: List[Tuple[str, str, Path, ComponentKind]] = []

        root_cmd = component_root / "cmd"
        if root_cmd.is_dir():
            for cmd_entry in sorted(root_cmd.iterdir()):
                if cmd_entry.is_dir() and self._has_main_go(cmd_entry):
                    cmd_name = cmd_entry.name
                    if cmd_name in package_imports:
                        continue
                    cmd_imports = self._scan_imports(cmd_entry, module_path)
                    package_imports[cmd_name] = cmd_imports
                    kind = self._classify_cmd(cmd_entry)
                    cmd_components.append((cmd_name, "", cmd_entry, kind))

        for pkg_name, pkg_dir in packages.items():
            for cmd_dir in sorted(pkg_dir.rglob("cmd")):
                if not cmd_dir.is_dir():
                    continue
                for cmd_entry in sorted(cmd_dir.iterdir()):
                    if cmd_entry.is_dir() and self._has_main_go(cmd_entry):
                        # Name: prefer parent-cmdname if different, else just cmdname
                        cmd_entry_name = cmd_entry.name
                        # Use a descriptive name: pkg-cmdname or just cmdname
                        if cmd_entry_name == pkg_name or cmd_entry_name == "main":
                            cmd_name = pkg_name
                        else:
                            cmd_name = f"{pkg_name}-{cmd_entry_name}"
                        # Deduplicate
                        if cmd_name in package_imports:
                            continue
                        cmd_imports = self._scan_imports(cmd_entry, module_path)
                        package_imports[cmd_name] = cmd_imports
                        kind = self._classify_cmd(cmd_entry)
                        cmd_components.append((cmd_name, pkg_name, cmd_entry, kind))

        # Build library components
        for pkg_name, pkg_dir in packages.items():
            internal_deps = self._resolve_import_deps(
                package_imports[pkg_name], packages, module_path,
            )
            # Remove self-dependency
            internal_deps.discard(pkg_name)
            rel_path = str(pkg_dir.relative_to(repo_root))

            components.append(Component(
                name=pkg_name,
                kind=ComponentKind.LIBRARY,
                type="go-module",
                root_path=rel_path,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=sorted(internal_deps),
                external_dependencies=[],  # Module-level deps apply to all
            ))

        # Build application components from cmd/ directories
        for cmd_name, parent_pkg, cmd_dir, kind in cmd_components:
            internal_deps = self._resolve_import_deps(
                package_imports[cmd_name], packages, module_path,
            )
            # Root-level cmd binaries have no parent package
            if parent_pkg and parent_pkg not in internal_deps:
                internal_deps.add(parent_pkg)

            rel_path = str(cmd_dir.relative_to(repo_root))

            components.append(Component(
                name=cmd_name,
                kind=kind,
                type="go-module",
                root_path=rel_path,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=sorted(internal_deps),
                external_dependencies=[],
            ))

        return components

    def _scan_imports(self, directory: Path, module_path: str) -> Set[str]:
        """Scan all .go files in a directory (recursively) for import paths."""
        imports: Set[str] = set()

        for go_file in directory.rglob("*.go"):
            try:
                content = go_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Extract import blocks
            # Match: import "path" or import ( "path1" \n "path2" )
            for match in re.finditer(
                r'import\s*\(\s*(.*?)\s*\)|import\s+"([^"]+)"',
                content, re.DOTALL,
            ):
                if match.group(1):
                    # Multi-line import block
                    block = match.group(1)
                    for line in block.splitlines():
                        line = line.strip()
                        # Handle: "path" or alias "path"
                        imp_match = re.search(r'"([^"]+)"', line)
                        if imp_match:
                            imp = imp_match.group(1)
                            if imp.startswith(module_path + "/"):
                                imports.add(imp)
                elif match.group(2):
                    # Single import
                    imp = match.group(2)
                    if imp.startswith(module_path + "/"):
                        imports.add(imp)

        return imports

    def _resolve_import_deps(
        self,
        imports: Set[str],
        packages: Dict[str, Path],
        module_path: str,
    ) -> Set[str]:
        """Map import paths to package component names.

        e.g., 'github.com/Layr-Labs/eigenda/common/aws' → 'common'
        """
        deps: Set[str] = set()
        prefix = module_path + "/"

        for imp in imports:
            if not imp.startswith(prefix):
                continue
            # Get the relative path after module prefix
            rel = imp[len(prefix):]
            # The top-level directory is the package name
            top_dir = rel.split("/")[0]
            if top_dir in packages:
                deps.add(top_dir)

        return deps

    # ------------------------------------------------------------------
    # go.mod parsing
    # ------------------------------------------------------------------

    def _parse_module_path(self, text: str) -> str:
        """Extract module path from go.mod content."""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("module "):
                return line.split("module ", 1)[1].strip()
        return ""

    def _parse_go_mod_deps(
        self, text: str, module_path: str,
    ) -> Tuple[List[ExternalDependency], List[ExternalDependency]]:
        """Parse go.mod require blocks into direct and indirect deps."""
        direct: List[ExternalDependency] = []
        indirect: List[ExternalDependency] = []
        in_require = False

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if stripped == ")" and in_require:
                in_require = False
                continue
            if in_require and stripped and not stripped.startswith("//"):
                is_indirect = "// indirect" in stripped
                parts = stripped.split()
                if len(parts) >= 2:
                    dep_path = parts[0]
                    dep_version = parts[1]

                    # Skip internal sub-modules
                    base = "/".join(module_path.split("/")[:3])
                    if dep_path.startswith(base):
                        continue

                    dep = ExternalDependency(name=dep_path, version=dep_version)
                    if is_indirect:
                        indirect.append(dep)
                    else:
                        direct.append(dep)

        return direct, indirect

    # ------------------------------------------------------------------
    # cmd/ discovery
    # ------------------------------------------------------------------

    def _discover_cmd_components(
        self,
        component_root: Path,
        repo_root: Path,
        manifest_path: Path,
        parent_name: str,
        components: List[Component],
    ) -> None:
        """Discover cmd/ subdirectories as application components."""
        cmd_dir = component_root / "cmd"
        if not cmd_dir.is_dir():
            return

        for cmd_entry in sorted(cmd_dir.iterdir()):
            if cmd_entry.is_dir() and self._has_main_go(cmd_entry):
                cmd_name = cmd_entry.name
                cmd_rel = str(cmd_entry.relative_to(repo_root))
                components.append(Component(
                    name=cmd_name,
                    kind=self._classify_cmd(cmd_entry),
                    type="go-module",
                    root_path=cmd_rel,
                    manifest_path=str(manifest_path.relative_to(repo_root)),
                    description="",
                    internal_dependencies=[parent_name],
                    external_dependencies=[],
                ))

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(self, component_root: Path) -> ComponentKind:
        if (component_root / "main.go").exists():
            return self._classify_by_content(component_root / "main.go")
        if (component_root / "cmd").is_dir():
            return ComponentKind.LIBRARY
        for go_file in component_root.glob("*.go"):
            if self._is_main_package(go_file):
                return self._classify_by_content(go_file)
        return ComponentKind.LIBRARY

    def _classify_cmd(self, cmd_dir: Path) -> ComponentKind:
        main_go = cmd_dir / "main.go"
        if main_go.exists():
            return self._classify_by_content(main_go)
        return ComponentKind.SERVICE

    def _classify_by_content(self, main_file: Path) -> ComponentKind:
        """Classify an executable Go file.

        Strategy: scan the main.go and also nearby files for indicators.
        urfave/cli is used by both services and CLIs (for flag parsing),
        so we look at the broader context — does the cmd dir or its
        parent contain server/listener setup?
        """
        try:
            # Read main.go + all .go files in the same directory
            content_parts = []
            for f in main_file.parent.rglob("*.go"):
                try:
                    content_parts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
            content = "\n".join(content_parts).lower()
        except OSError:
            return ComponentKind.SERVICE

        # Strong service indicators (these are definitive)
        service_indicators = [
            "listenandserve", "grpc.newserver", "net.listen",
            "http.server", "gin.default", "echo.new", "fiber.new",
            "grpcserver", "startserver", "serve(", "runserver",
            "listener", ".start(", "httpserver", "grpcserver",
        ]

        # Strong CLI indicators (not shared with services)
        cli_only_indicators = [
            "cobra.command", "pflag.",
            "kingpin.", "os.args",
        ]

        # Weak indicators (shared between services and CLIs)
        # urfave/cli and flag.parse are used by both
        service_score = sum(1 for i in service_indicators if i in content)
        cli_score = sum(1 for i in cli_only_indicators if i in content)

        # Name-based boost: many Go services use urfave/cli for flags
        # but are still long-running processes, not CLI tools
        name = main_file.parent.name.lower()
        service_names = [
            "server", "apiserver", "daemon", "node", "relay", "proxy",
            "batcher", "encoder", "controller", "worker", "agent",
            "indexer", "ejector", "retriever", "dataapi", "blobapi",
        ]
        if any(kw in name for kw in service_names):
            service_score += 2
        if any(kw in name for kw in ["cli", "tool", "util"]):
            cli_score += 2

        if service_score > cli_score:
            return ComponentKind.SERVICE
        if cli_score > 0:
            return ComponentKind.CLI
        return ComponentKind.SERVICE  # Default for executables

    def _has_main_go(self, directory: Path) -> bool:
        return (directory / "main.go").exists()

    def _is_main_package(self, go_file: Path) -> bool:
        try:
            for line in go_file.open(encoding="utf-8", errors="replace"):
                line = line.strip()
                if line.startswith("package "):
                    return line.split()[1] == "main"
                if line and not line.startswith("//") and not line.startswith("/*"):
                    break
        except OSError:
            pass
        return False
