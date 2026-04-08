"""Solidity language discovery plugin.

Supports Foundry (foundry.toml) and Hardhat (hardhat.config.ts/js) projects.
Discovers contracts, interfaces, and libraries from .sol source files,
traces import edges, and classifies components.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency

logger = logging.getLogger(__name__)

# Solidity declaration kinds
SOL_CONTRACT = "contract"
SOL_ABSTRACT = "abstract contract"
SOL_INTERFACE = "interface"
SOL_LIBRARY = "library"


class SolidityPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "Solidity"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/foundry.toml", "**/hardhat.config.ts", "**/hardhat.config.js"]

    @property
    def exclude_patterns(self) -> List[str]:
        return [
            "**/node_modules/**", "**/.git/**", "**/out/**",
            "**/cache/**", "**/artifacts/**", "**/typechain/**",
            "**/typechain-types/**",
            # Foundry lib/ contains vendored dependencies (git submodules).
            # These have their own foundry.toml files but should not be
            # discovered as source components.
            "**/lib/forge-std/**",
            "**/lib/openzeppelin-*/**",
            "**/lib/eigenlayer-*/**",
            "**/lib/ds-test/**",
            "**/lib/zeus-*/**",
        ]

    def should_exclude(self, path: Path) -> bool:
        """Exclude vendored Foundry lib/ dependencies."""
        path_str = str(path)

        # Generic: any foundry.toml inside a lib/ directory is vendored
        parts = path.parts
        for i, part in enumerate(parts):
            if part == "lib" and i > 0:
                # Check if a parent is a Foundry project (has foundry.toml)
                parent = Path(*parts[:i])
                if (parent / "foundry.toml").exists():
                    return True

        return super().should_exclude(path)

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        project_root = manifest_path.parent
        rel_root = str(project_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        if manifest_path.name == "foundry.toml":
            return self._parse_foundry(manifest_path, project_root, repo_root)
        else:
            return self._parse_hardhat(manifest_path, project_root, repo_root)

    # ------------------------------------------------------------------
    # Foundry
    # ------------------------------------------------------------------

    def _parse_foundry(
        self, manifest_path: Path, project_root: Path, repo_root: Path,
    ) -> List[Component]:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        manifest_rel = str(manifest_path.relative_to(repo_root))

        # Parse foundry.toml for source/lib/test paths
        src_dir = self._parse_foundry_field(text, "src", "src")
        lib_dir = self._parse_foundry_field(text, "libs", "lib")
        test_dir = self._parse_foundry_field(text, "test", "test")
        script_dir = self._parse_foundry_field(text, "script", "script")

        src_path = project_root / src_dir
        lib_path = project_root / lib_dir
        test_path = project_root / test_dir
        script_path = project_root / script_dir

        if not src_path.is_dir():
            logger.warning("Foundry src dir not found: %s", src_path)
            return []

        # Add lib/, test/, script/ to exclude list for this project
        # These are dependencies and test code, not source components
        self._project_excludes = {
            str(lib_path), str(test_path), str(script_path),
        }

        # Parse remappings for import resolution
        remappings = self._parse_remappings(text, project_root)

        # Discover external dependencies from lib/ (git submodules)
        external_deps = self._discover_lib_deps(lib_path)

        # Discover source components by top-level directory in src/
        packages = self._discover_sol_packages(src_path)

        if not packages:
            # Flat structure: treat the whole src/ as one component
            return [self._build_flat_component(
                project_root, repo_root, manifest_rel, src_path,
                external_deps, remappings,
            )]

        # Multi-package: build components per directory
        return self._build_package_components(
            packages, project_root, repo_root, manifest_rel,
            src_path, external_deps, remappings,
        )

    def _parse_foundry_field(self, text: str, field: str, default: str) -> str:
        """Extract a string field from foundry.toml."""
        # Handle both: src = "src" and libs = ["lib"]
        match = re.search(
            rf'^\s*{field}\s*=\s*["\']([^"\']+)["\']',
            text, re.MULTILINE,
        )
        if match:
            return match.group(1)
        # Array form: libs = ["lib"]
        match = re.search(
            rf'^\s*{field}\s*=\s*\[\s*["\']([^"\']+)["\']',
            text, re.MULTILINE,
        )
        if match:
            return match.group(1)
        return default

    def _parse_remappings(
        self, text: str, project_root: Path,
    ) -> Dict[str, str]:
        """Parse import remappings from foundry.toml."""
        remappings: Dict[str, str] = {}
        remap_match = re.search(
            r'remappings\s*=\s*\[(.*?)\]', text, re.DOTALL,
        )
        if remap_match:
            block = remap_match.group(1)
            for line in block.splitlines():
                line = line.strip().strip(',"\'')
                if "=" in line:
                    prefix, target = line.split("=", 1)
                    remappings[prefix.strip()] = target.strip()
        return remappings

    def _discover_lib_deps(self, lib_path: Path) -> List[ExternalDependency]:
        """Discover external dependencies from Foundry lib/ directory."""
        deps: List[ExternalDependency] = []
        if not lib_path.is_dir():
            return deps

        for entry in sorted(lib_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            deps.append(ExternalDependency(
                name=entry.name,
                category="solidity-library",
            ))

        return deps

    # ------------------------------------------------------------------
    # Package discovery
    # ------------------------------------------------------------------

    def _discover_sol_packages(self, src_path: Path) -> Dict[str, Path]:
        """Find top-level directories in src/ that contain .sol files."""
        packages: Dict[str, Path] = {}

        for entry in sorted(src_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            sol_files = list(entry.rglob("*.sol"))
            if sol_files:
                packages[entry.name] = entry

        return packages

    def _build_flat_component(
        self,
        project_root: Path,
        repo_root: Path,
        manifest_rel: str,
        src_path: Path,
        external_deps: List[ExternalDependency],
        remappings: Dict[str, str],
    ) -> Component:
        """Build a single component for a flat src/ directory."""
        sol_files = list(src_path.rglob("*.sol"))
        declarations = self._scan_declarations(sol_files)
        kind = self._classify_declarations(declarations)
        rel_root = str(project_root.relative_to(repo_root))

        return Component(
            name=project_root.name + "-contracts",
            kind=kind,
            type="solidity-contract",
            root_path=rel_root or ".",
            manifest_path=manifest_rel,
            description="",
            internal_dependencies=[],
            external_dependencies=external_deps,
            metadata={
                "declarations": self._summarize_declarations(declarations),
                "solidity_version": self._detect_solidity_version(sol_files),
            },
        )

    def _build_package_components(
        self,
        packages: Dict[str, Path],
        project_root: Path,
        repo_root: Path,
        manifest_rel: str,
        src_path: Path,
        external_deps: List[ExternalDependency],
        remappings: Dict[str, str],
    ) -> List[Component]:
        """Build components for each subdirectory in src/."""
        components: List[Component] = []

        # Scan imports for each package
        package_imports: Dict[str, Set[str]] = {}
        for pkg_name, pkg_dir in packages.items():
            package_imports[pkg_name] = self._scan_sol_imports(
                pkg_dir, src_path, remappings,
            )

        for pkg_name, pkg_dir in packages.items():
            sol_files = list(pkg_dir.rglob("*.sol"))
            declarations = self._scan_declarations(sol_files)
            kind = self._classify_declarations(declarations)

            # Resolve internal deps from imports
            internal_deps = self._resolve_import_deps(
                package_imports[pkg_name], packages, src_path,
            )
            internal_deps.discard(pkg_name)  # Remove self-dependency

            rel_path = str(pkg_dir.relative_to(repo_root))

            components.append(Component(
                name=pkg_name,
                kind=kind,
                type="solidity-contract",
                root_path=rel_path,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=sorted(internal_deps),
                external_dependencies=[],  # Project-level deps apply to all
                metadata={
                    "declarations": self._summarize_declarations(declarations),
                },
            ))

        # Add a root component representing the project with external deps
        project_rel = str(project_root.relative_to(repo_root))
        sol_version = self._detect_solidity_version(
            list(src_path.rglob("*.sol"))[:10]
        )
        components.append(Component(
            name=project_root.name + "-contracts",
            kind=ComponentKind.CONTRACT,
            type="solidity-contract",
            root_path=project_rel or ".",
            manifest_path=manifest_rel,
            description=f"Foundry project (Solidity {sol_version})",
            internal_dependencies=[pkg for pkg in packages],
            external_dependencies=external_deps,
            metadata={"solidity_version": sol_version},
        ))

        return components

    # ------------------------------------------------------------------
    # Solidity source scanning
    # ------------------------------------------------------------------

    def _scan_declarations(
        self, sol_files: List[Path],
    ) -> List[Tuple[str, str, str]]:
        """Scan .sol files for contract/interface/library declarations.

        Returns list of (kind, name, file_path) tuples.
        """
        declarations: List[Tuple[str, str, str]] = []

        for sol_file in sol_files:
            try:
                content = sol_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Match: contract Foo, abstract contract Foo, interface IFoo, library Bar
            for match in re.finditer(
                r'^(abstract\s+contract|contract|interface|library)\s+'
                r'([A-Za-z_][A-Za-z0-9_]*)',
                content, re.MULTILINE,
            ):
                kind = match.group(1).strip()
                name = match.group(2)
                declarations.append((kind, name, str(sol_file)))

        return declarations

    def _summarize_declarations(
        self, declarations: List[Tuple[str, str, str]],
    ) -> Dict[str, int]:
        """Summarize declaration counts by kind."""
        summary: Dict[str, int] = {}
        for kind, _, _ in declarations:
            summary[kind] = summary.get(kind, 0) + 1
        return summary

    def _scan_sol_imports(
        self,
        pkg_dir: Path,
        src_root: Path,
        remappings: Dict[str, str],
    ) -> Set[str]:
        """Scan .sol files for import paths."""
        imports: Set[str] = set()

        for sol_file in pkg_dir.rglob("*.sol"):
            try:
                content = sol_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Match: import "path.sol" and import {Foo} from "path.sol"
            for match in re.finditer(r'import\s+(?:\{[^}]*\}\s+from\s+)?["\']([^"\']+)["\']', content):
                imp = match.group(1)
                # Apply remappings
                for prefix, target in remappings.items():
                    if imp.startswith(prefix):
                        imp = target + imp[len(prefix):]
                        break
                imports.add(imp)

        return imports

    def _resolve_import_deps(
        self,
        imports: Set[str],
        packages: Dict[str, Path],
        src_root: Path,
    ) -> Set[str]:
        """Map import paths to package names.

        Imports like "src/core/Foo.sol" or "./core/Foo.sol" map to the 'core' package.
        Imports starting with "lib/" are external (handled separately).
        """
        deps: Set[str] = set()
        src_prefix = "src/"

        for imp in imports:
            # Skip external lib imports
            if imp.startswith("lib/") or imp.startswith("node_modules/"):
                continue

            # Normalize: strip src/ prefix, handle relative paths
            if imp.startswith(src_prefix):
                rel = imp[len(src_prefix):]
            elif imp.startswith("./") or imp.startswith("../"):
                continue  # Relative within same package
            else:
                rel = imp

            # Top-level directory is the package
            top_dir = rel.split("/")[0]
            if top_dir in packages:
                deps.add(top_dir)

        return deps

    def _classify_declarations(
        self, declarations: List[Tuple[str, str, str]],
    ) -> ComponentKind:
        """Classify based on what Solidity declarations are present."""
        has_contract = any(
            k in (SOL_CONTRACT, SOL_ABSTRACT)
            for k, _, _ in declarations
        )
        has_interface_only = all(
            k == SOL_INTERFACE for k, _, _ in declarations
        ) and declarations
        has_library_only = all(
            k == SOL_LIBRARY for k, _, _ in declarations
        ) and declarations

        if has_library_only:
            return ComponentKind.LIBRARY
        if has_interface_only:
            return ComponentKind.CONTRACT  # Interfaces are contract specs
        if has_contract:
            return ComponentKind.CONTRACT
        return ComponentKind.CONTRACT

    def _detect_solidity_version(self, sol_files: List[Path]) -> str:
        """Detect Solidity version from pragma statements."""
        for sol_file in sol_files[:10]:
            try:
                content = sol_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r'pragma\s+solidity\s+([^;]+);', content)
            if match:
                return match.group(1).strip()
        return "unknown"

    # ------------------------------------------------------------------
    # Hardhat
    # ------------------------------------------------------------------

    def _parse_hardhat(
        self, manifest_path: Path, project_root: Path, repo_root: Path,
    ) -> List[Component]:
        """Parse a Hardhat project.

        Hardhat uses contracts/ as the default source directory and
        node_modules/ for dependencies.
        """
        manifest_rel = str(manifest_path.relative_to(repo_root))
        contracts_dir = project_root / "contracts"

        if not contracts_dir.is_dir():
            # Try src/ as alternative
            contracts_dir = project_root / "src"
            if not contracts_dir.is_dir():
                return []

        # External deps from package.json
        external_deps: List[ExternalDependency] = []
        pkg_json = project_root / "package.json"
        if pkg_json.exists():
            import json
            try:
                data = json.loads(pkg_json.read_text())
                for dep_name in data.get("dependencies", {}):
                    if any(kw in dep_name.lower() for kw in [
                        "openzeppelin", "hardhat", "solidity",
                        "ethers", "chai", "waffle",
                    ]):
                        external_deps.append(ExternalDependency(
                            name=dep_name,
                            version=data["dependencies"][dep_name],
                            category="solidity-tooling",
                        ))
            except Exception:
                pass

        # Discover packages within contracts/
        packages = self._discover_sol_packages(contracts_dir)

        if not packages:
            sol_files = list(contracts_dir.rglob("*.sol"))
            if not sol_files:
                return []
            declarations = self._scan_declarations(sol_files)
            rel_root = str(project_root.relative_to(repo_root))
            return [Component(
                name=project_root.name + "-contracts",
                kind=ComponentKind.CONTRACT,
                type="solidity-contract",
                root_path=rel_root or ".",
                manifest_path=manifest_rel,
                description="Hardhat project",
                internal_dependencies=[],
                external_dependencies=external_deps,
                metadata={
                    "declarations": self._summarize_declarations(declarations),
                    "framework": "hardhat",
                },
            )]

        # Multi-package
        components: List[Component] = []
        for pkg_name, pkg_dir in packages.items():
            sol_files = list(pkg_dir.rglob("*.sol"))
            declarations = self._scan_declarations(sol_files)
            kind = self._classify_declarations(declarations)
            rel_path = str(pkg_dir.relative_to(repo_root))

            components.append(Component(
                name=pkg_name,
                kind=kind,
                type="solidity-contract",
                root_path=rel_path,
                manifest_path=manifest_rel,
                description="",
                internal_dependencies=[],
                external_dependencies=[],
                metadata={
                    "declarations": self._summarize_declarations(declarations),
                    "framework": "hardhat",
                },
            ))

        return components
