"""Go language discovery plugin."""

from pathlib import Path
from typing import List

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency


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
        components: List[Component] = []
        component_root = manifest_path.parent
        rel_root = str(component_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        text = manifest_path.read_text(encoding="utf-8", errors="replace")

        # Parse module name
        module_name = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("module "):
                module_name = line.split("module ", 1)[1].strip()
                break

        if not module_name:
            return components

        # Derive short name from module path
        short_name = module_name.rsplit("/", 1)[-1]

        # Parse dependencies
        internal_deps: List[str] = []
        external_deps: List[ExternalDependency] = []
        in_require = False

        for line in text.splitlines():
            line = line.strip()
            if line == "require (":
                in_require = True
                continue
            if line == ")" and in_require:
                in_require = False
                continue
            if in_require and line and not line.startswith("//"):
                parts = line.split()
                if len(parts) >= 2:
                    dep_path = parts[0]
                    dep_version = parts[1]
                    # Check if it's an internal dependency (same module prefix)
                    base_module = module_name.split("/")[0:3]  # e.g., github.com/org/repo
                    dep_base = dep_path.split("/")[0:3]
                    if base_module == dep_base and dep_path != module_name:
                        dep_short = dep_path.rsplit("/", 1)[-1]
                        internal_deps.append(dep_short)
                    else:
                        external_deps.append(ExternalDependency(
                            name=dep_path,
                            version=dep_version,
                        ))

        # Classify: check for main packages
        kind = self._classify(component_root)

        components.append(Component(
            name=short_name,
            kind=kind,
            type="go-module",
            root_path=rel_root or ".",
            manifest_path=str(manifest_path.relative_to(repo_root)),
            description="",
            internal_dependencies=internal_deps,
            external_dependencies=external_deps,
        ))

        # For monorepos: also discover cmd/ subdirectories as separate components
        cmd_dir = component_root / "cmd"
        if cmd_dir.is_dir():
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
                        internal_dependencies=[short_name],
                        external_dependencies=[],
                    ))

        return components

    def _classify(self, component_root: Path) -> ComponentKind:
        """Classify a Go module based on its structure."""
        # If there's a main.go at root, it's an executable
        if (component_root / "main.go").exists():
            return self._classify_by_content(component_root / "main.go")

        # If there's a cmd/ directory, the root module is a library
        # (the cmd/ entries are discovered separately)
        if (component_root / "cmd").is_dir():
            return ComponentKind.LIBRARY

        # Check for main package in any top-level .go file
        for go_file in component_root.glob("*.go"):
            if self._is_main_package(go_file):
                return self._classify_by_content(go_file)

        return ComponentKind.LIBRARY

    def _classify_cmd(self, cmd_dir: Path) -> ComponentKind:
        """Classify a cmd/ subdirectory."""
        main_go = cmd_dir / "main.go"
        if main_go.exists():
            return self._classify_by_content(main_go)
        return ComponentKind.SERVICE

    def _classify_by_content(self, main_file: Path) -> ComponentKind:
        """Inspect a main.go file to determine if it's a CLI or service."""
        try:
            content = main_file.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return ComponentKind.SERVICE

        # Heuristic: services typically start listeners
        service_indicators = [
            "listenandserve", "grpc.newserver", "net.listen",
            "http.server", "gin.default", "echo.new", "fiber.new",
            "grpcserver", "startserver",
        ]
        cli_indicators = [
            "cobra.command", "flag.parse", "pflag.", "cli.app",
            "kingpin.", "urfave/cli", "os.args",
        ]

        service_score = sum(1 for i in service_indicators if i in content)
        cli_score = sum(1 for i in cli_indicators if i in content)

        if service_score > cli_score:
            return ComponentKind.SERVICE
        if cli_score > 0:
            return ComponentKind.CLI
        return ComponentKind.SERVICE  # Default for executables

    def _has_main_go(self, directory: Path) -> bool:
        """Check if a directory contains a main.go file."""
        return (directory / "main.go").exists()

    def _is_main_package(self, go_file: Path) -> bool:
        """Check if a .go file declares package main."""
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
