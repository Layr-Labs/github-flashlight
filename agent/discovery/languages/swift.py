"""Swift language discovery plugin.

Supports Swift Package Manager (Package.swift) projects.
Discovers targets (libraries, executables, tests) and their dependencies.
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency


class SwiftPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "Swift"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/Package.swift"]

    @property
    def exclude_patterns(self) -> List[str]:
        return [
            "**/.build/**", "**/.git/**", "**/Pods/**",
            "**/Carthage/**", "**/DerivedData/**",
        ]

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        project_root = manifest_path.parent
        rel_root = str(project_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        manifest_rel = str(manifest_path.relative_to(repo_root))

        # Parse package name
        package_name = self._parse_package_name(text) or project_root.name

        # Parse external dependencies (.package directives)
        external_deps = self._parse_dependencies(text)

        # Parse targets
        targets = self._parse_targets(text)

        if not targets:
            # Single-target package: classify from directory structure
            kind = self._classify_from_structure(project_root)
            return [Component(
                name=package_name,
                kind=kind,
                type="swift-package",
                root_path=rel_root or ".",
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=[],
                external_dependencies=external_deps,
            )]

        # Single non-test target: attach external deps directly
        non_test = [t for t in targets if t["type"] != "testTarget"]
        if len(non_test) == 1:
            t = non_test[0]
            kind = self._classify_target(t["type"], t["name"], project_root)
            tgt_path = t.get("path")
            if tgt_path:
                target_root = str((project_root / tgt_path).relative_to(repo_root))
            else:
                sources_dir = project_root / "Sources" / t["name"]
                target_root = str(sources_dir.relative_to(repo_root)) if sources_dir.is_dir() else (rel_root or ".")
            return [Component(
                name=t["name"],
                kind=kind,
                type="swift-package",
                root_path=target_root,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=[],
                external_dependencies=external_deps,
            )]

        # Multi-target package: one component per target
        components: List[Component] = []
        target_names = {t["name"] for t in targets}

        for target in targets:
            tgt_name = target["name"]
            tgt_type = target["type"]
            tgt_deps = target.get("dependencies", [])

            # Separate internal vs. external deps
            internal_deps = [d for d in tgt_deps if d in target_names]

            # Classify
            kind = self._classify_target(tgt_type, tgt_name, project_root)

            # Determine target root path
            tgt_path = target.get("path")
            if tgt_path:
                target_root = str((project_root / tgt_path).relative_to(repo_root))
            else:
                # Default SPM layout: Sources/{target_name}/
                sources_dir = project_root / "Sources" / tgt_name
                if sources_dir.is_dir():
                    target_root = str(sources_dir.relative_to(repo_root))
                else:
                    target_root = rel_root or "."

            # Skip test targets
            if tgt_type == "testTarget":
                continue

            components.append(Component(
                name=tgt_name,
                kind=kind,
                type="swift-package",
                root_path=target_root,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=sorted(internal_deps),
                external_dependencies=[],  # Package-level deps apply to all
            ))

        # Add a root component if there are multiple targets, to hold external deps
        if len(components) > 1:
            components.append(Component(
                name=package_name,
                kind=ComponentKind.LIBRARY,
                type="swift-package",
                root_path=rel_root or ".",
                manifest_path=manifest_rel,
                description="Swift package root",
                internal_dependencies=[c.name for c in components],
                external_dependencies=external_deps,
            ))

        return components

    # ------------------------------------------------------------------
    # Package.swift parsing
    # ------------------------------------------------------------------

    def _parse_package_name(self, text: str) -> str:
        """Extract package name from Package(name: "...")."""
        match = re.search(r'Package\s*\(\s*name\s*:\s*"([^"]+)"', text)
        return match.group(1) if match else ""

    def _parse_dependencies(self, text: str) -> List[ExternalDependency]:
        """Extract external package dependencies."""
        deps: List[ExternalDependency] = []

        # Match .package(url: "...", ...) or .package(name: "...", url: "...", ...)
        for match in re.finditer(
            r'\.package\s*\([^)]*url\s*:\s*"([^"]+)"[^)]*\)',
            text,
        ):
            url = match.group(1)
            # Extract name from URL: https://github.com/org/repo.git -> repo
            name = url.rstrip("/").rstrip(".git").rsplit("/", 1)[-1]

            # Try to find version
            block = match.group(0)
            version = ""
            ver_match = re.search(r'from\s*:\s*"([^"]+)"', block)
            if ver_match:
                version = ">=" + ver_match.group(1)
            else:
                ver_match = re.search(r'exact\s*:\s*"([^"]+)"', block)
                if ver_match:
                    version = ver_match.group(1)
                else:
                    ver_match = re.search(r'"(\d+\.\d+\.\d+)"', block)
                    if ver_match:
                        version = ver_match.group(1)

            deps.append(ExternalDependency(name=name, version=version))

        return deps

    def _parse_targets(self, text: str) -> List[Dict]:
        """Extract target definitions from Package.swift.

        Returns list of dicts with keys: name, type, dependencies, path.
        """
        targets: List[Dict] = []

        # Match target types: .target, .executableTarget, .testTarget,
        # .binaryTarget, .systemLibrary
        target_pattern = re.compile(
            r'\.(target|executableTarget|testTarget|binaryTarget|systemLibrary)'
            r'\s*\(\s*'
            r'name\s*:\s*"([^"]+)"'
            r'([^)]*)\)',
            re.DOTALL,
        )

        for match in target_pattern.finditer(text):
            tgt_type = match.group(1)
            tgt_name = match.group(2)
            tgt_body = match.group(3)

            # Parse dependencies within target
            deps = []
            # .product(name: "Foo", package: "Bar") or just "Foo" or .target(name: "Foo")
            for dep_match in re.finditer(
                r'\.(?:product|target)\s*\(\s*name\s*:\s*"([^"]+)"[^)]*\)|'
                r'"([A-Za-z_][A-Za-z0-9_]*)"',
                tgt_body,
            ):
                dep_name = dep_match.group(1) or dep_match.group(2)
                if dep_name and dep_name != tgt_name:
                    deps.append(dep_name)

            # Parse custom path
            path = None
            path_match = re.search(r'path\s*:\s*"([^"]+)"', tgt_body)
            if path_match:
                path = path_match.group(1)

            targets.append({
                "name": tgt_name,
                "type": tgt_type,
                "dependencies": deps,
                "path": path,
            })

        return targets

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_target(
        self, target_type: str, name: str, project_root: Path,
    ) -> ComponentKind:
        """Classify a Swift target."""
        if target_type == "executableTarget":
            return self._classify_executable(name, project_root)
        if target_type == "binaryTarget":
            return ComponentKind.LIBRARY
        if target_type == "systemLibrary":
            return ComponentKind.LIBRARY
        if target_type == "testTarget":
            return ComponentKind.LIBRARY  # shouldn't reach here (filtered out)

        # Regular .target — check if it has @main or main.swift
        sources_dir = project_root / "Sources" / name
        if sources_dir.is_dir():
            if (sources_dir / "main.swift").exists():
                return self._classify_executable(name, project_root)
            # Check for @main attribute
            for swift_file in sources_dir.rglob("*.swift"):
                try:
                    content = swift_file.read_text(encoding="utf-8", errors="replace")
                    if re.search(r'@main\b', content):
                        return self._classify_executable(name, project_root)
                except OSError:
                    pass

        return ComponentKind.LIBRARY

    def _classify_executable(self, name: str, project_root: Path) -> ComponentKind:
        """Classify an executable target as service, CLI, or frontend."""
        name_lower = name.lower()

        # Service indicators
        if any(kw in name_lower for kw in [
            "server", "service", "daemon", "api", "backend", "proxy",
        ]):
            return ComponentKind.SERVICE

        # Check source for server patterns
        sources_dir = project_root / "Sources" / name
        if sources_dir.is_dir():
            for swift_file in list(sources_dir.rglob("*.swift"))[:10]:
                try:
                    content = swift_file.read_text(encoding="utf-8", errors="replace").lower()
                except OSError:
                    continue

                server_indicators = [
                    "vapor", "hummingbird", "swiftnio", "grpc",
                    "httpserver", "app.run()", "server.start",
                    "niotsbootstrap", "serverbootstrap",
                ]
                if any(ind in content for ind in server_indicators):
                    return ComponentKind.SERVICE

                # iOS/macOS app indicators
                app_indicators = [
                    "uiapplication", "nsapplication", "swiftui",
                    "@main struct", "windowgroup", "scene",
                ]
                if any(ind in content for ind in app_indicators):
                    return ComponentKind.FRONTEND

        # CLI indicators
        if any(kw in name_lower for kw in ["cli", "tool", "cmd", "command"]):
            return ComponentKind.CLI

        # Check for ArgumentParser (swift-argument-parser)
        if sources_dir.is_dir():
            for swift_file in list(sources_dir.rglob("*.swift"))[:10]:
                try:
                    content = swift_file.read_text(encoding="utf-8", errors="replace")
                    if "ParsableCommand" in content or "ArgumentParser" in content:
                        return ComponentKind.CLI
                except OSError:
                    pass

        return ComponentKind.CLI  # Default for executables

    def _classify_from_structure(self, project_root: Path) -> ComponentKind:
        """Classify a single-target Swift package from directory structure."""
        sources = project_root / "Sources"
        if not sources.is_dir():
            return ComponentKind.LIBRARY

        # Check for main.swift or @main
        for swift_file in sources.rglob("*.swift"):
            if swift_file.name == "main.swift":
                return self._classify_executable(project_root.name, project_root)
            try:
                content = swift_file.read_text(encoding="utf-8", errors="replace")
                if re.search(r'@main\b', content):
                    return self._classify_executable(project_root.name, project_root)
            except OSError:
                pass

        return ComponentKind.LIBRARY
