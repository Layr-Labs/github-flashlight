"""Rust language discovery plugin."""

import re
from pathlib import Path
from typing import List

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency


class RustPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "Rust"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/Cargo.toml"]

    @property
    def exclude_patterns(self) -> List[str]:
        return ["**/target/**", "**/.git/**"]

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        component_root = manifest_path.parent
        rel_root = str(component_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        # Check for workspace — discover members instead
        if self._is_workspace(text):
            return self._discover_workspace(text, manifest_path, repo_root)

        name = self._extract_field(text, "name") or component_root.name
        description = self._extract_field(text, "description") or ""

        # Parse dependencies
        external_deps, internal_deps = self._parse_dependencies(text)

        # Classify
        kind = self._classify(text, component_root)

        return [Component(
            name=name,
            kind=kind,
            type="rust-crate",
            root_path=rel_root or ".",
            manifest_path=str(manifest_path.relative_to(repo_root)),
            description=description,
            internal_dependencies=internal_deps,
            external_dependencies=external_deps,
        )]

    def _is_workspace(self, text: str) -> bool:
        return bool(re.search(r'^\[workspace\]', text, re.MULTILINE))

    def _discover_workspace(
        self, text: str, manifest_path: Path, repo_root: Path
    ) -> List[Component]:
        """Discover crates from a Cargo workspace."""
        import glob as globmod

        components: List[Component] = []
        workspace_root = manifest_path.parent

        # Extract workspace members
        members_match = re.search(
            r'\[workspace\].*?members\s*=\s*\[(.*?)\]',
            text, re.DOTALL
        )
        if not members_match:
            return components

        members_block = members_match.group(1)
        for line in members_block.splitlines():
            member = line.strip().strip(',"\'')
            if not member or member.startswith("#"):
                continue
            # Expand globs
            pattern = str(workspace_root / member / "Cargo.toml")
            for cargo_path in sorted(globmod.glob(pattern)):
                cargo = Path(cargo_path)
                if self.should_exclude(cargo):
                    continue
                components.extend(self.parse_manifest(cargo, repo_root))

        return components

    def _extract_field(self, text: str, field: str) -> str:
        """Extract a field from [package] section."""
        # Simple approach: find field after [package]
        pkg_match = re.search(r'\[package\](.*?)(?:\[|\Z)', text, re.DOTALL)
        if not pkg_match:
            return ""
        pkg_section = pkg_match.group(1)
        field_match = re.search(
            rf'^\s*{field}\s*=\s*["\']([^"\']*)["\']',
            pkg_section, re.MULTILINE
        )
        return field_match.group(1) if field_match else ""

    _DEP_SECTION_RE = re.compile(
        r'^\[(?:target\.[^\]]+\.)?(dependencies|dev-dependencies|build-dependencies)\]'
        r'(.*?)(?=^\[|\Z)',
        re.MULTILINE | re.DOTALL,
    )

    def _parse_dependencies(self, text: str) -> tuple[List[ExternalDependency], List[str]]:
        """Parse all dependency tables (runtime, dev, build, target-specific).

        External deps are collected only from runtime [dependencies] sections —
        dev/build deps are test/build-time artifacts, not runtime edges.
        Internal path deps are collected from every table: a workspace member
        referenced by path is an internal edge regardless of which table
        declares it.
        """
        external: List[ExternalDependency] = []
        internal: set[str] = set()
        seen_external: set[str] = set()

        for match in self._DEP_SECTION_RE.finditer(text):
            kind = match.group(1)
            block = match.group(2)
            block_external, block_internal = self._parse_dep_block(block)
            internal.update(block_internal)
            if kind == "dependencies":
                for dep in block_external:
                    if dep.name in seen_external:
                        continue
                    seen_external.add(dep.name)
                    external.append(dep)

        return external, sorted(internal)

    def _parse_dep_block(
        self, block: str,
    ) -> tuple[List[ExternalDependency], List[str]]:
        external: List[ExternalDependency] = []
        internal: List[str] = []

        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue

            match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*(.*)', line)
            if not match:
                continue

            dep_name = match.group(1)
            dep_value = match.group(2).strip()

            if re.search(r'\bpath\s*=', dep_value):
                internal.append(dep_name)
                continue

            version = dep_value.strip('"\'')
            if version.startswith("{"):
                ver_match = re.search(r'version\s*=\s*["\']([^"\']+)', dep_value)
                version = ver_match.group(1) if ver_match else ""
            external.append(ExternalDependency(name=dep_name, version=version))

        return external, internal

    def _classify(self, text: str, component_root: Path) -> ComponentKind:
        """Classify a Rust crate."""
        has_bin = bool(re.search(r'^\[\[bin\]\]', text, re.MULTILINE))
        has_lib = bool(re.search(r'^\[lib\]', text, re.MULTILINE))
        has_main_rs = (component_root / "src" / "main.rs").exists()
        has_lib_rs = (component_root / "src" / "lib.rs").exists()

        if has_bin or has_main_rs:
            if has_lib or has_lib_rs:
                # Both lib and bin — classify based on name/content
                return self._classify_hybrid(text, component_root)
            return self._classify_executable(text, component_root)

        return ComponentKind.LIBRARY

    def _classify_executable(self, text: str, component_root: Path) -> ComponentKind:
        """Classify an executable crate as SERVICE or CLI."""
        text_lower = text.lower()
        name = self._extract_field(text, "name").lower()

        # Service indicators
        service_deps = [
            "actix-web", "axum", "warp", "rocket", "tonic",
            "hyper", "tower", "tide",
        ]
        if any(dep in text_lower for dep in service_deps):
            return ComponentKind.SERVICE

        # CLI indicators
        cli_deps = ["clap", "structopt", "argh", "gumdrop"]
        if any(dep in text_lower for dep in cli_deps):
            return ComponentKind.CLI

        # Name-based heuristic
        if any(kw in name for kw in ["server", "service", "daemon", "node", "api"]):
            return ComponentKind.SERVICE
        if any(kw in name for kw in ["cli", "tool", "cmd", "gen", "packer"]):
            return ComponentKind.CLI

        # Default: bare executables with no server framework are almost always
        # CLI tools (build scripts, codegen, packers). Audit corpus showed
        # SERVICE default produced far more false positives than CLI default.
        return ComponentKind.CLI

    def _classify_hybrid(self, text: str, component_root: Path) -> ComponentKind:
        """Classify a crate with both lib.rs and a [[bin]] / main.rs.

        A lib crate can ship a companion binary (tauri-cli ships a bin named
        cargo-tauri; workspace crates ship codegen binaries). The presence of
        a binary takes precedence when its manifest declaration is explicit —
        i.e. [[bin]] with a distinct name, or crate-type = ["cdylib"]/["bin"].
        Otherwise we treat the crate as primarily a library with a test
        harness binary.
        """
        bin_blocks = re.findall(
            r'^\[\[bin\]\](.*?)(?=^\[|\Z)',
            text, re.MULTILINE | re.DOTALL,
        )
        pkg_name = self._extract_field(text, "name")

        for block in bin_blocks:
            bin_name_match = re.search(
                r'^\s*name\s*=\s*["\']([^"\']+)', block, re.MULTILINE,
            )
            if not bin_name_match:
                continue
            bin_name = bin_name_match.group(1)
            if bin_name != pkg_name:
                # An explicitly-named binary distinct from the crate name
                # signals this is an executable with a library internal.
                return self._classify_executable(text, component_root)

        return ComponentKind.LIBRARY
