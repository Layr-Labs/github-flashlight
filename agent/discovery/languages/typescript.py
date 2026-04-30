"""TypeScript/JavaScript language discovery plugin."""

import json
from pathlib import Path
from typing import List

from .base import LanguagePlugin
from agent.schemas.core import Component, ComponentKind, ExternalDependency


class TypeScriptPlugin(LanguagePlugin):

    @property
    def name(self) -> str:
        return "TypeScript"

    @property
    def manifest_patterns(self) -> List[str]:
        return ["**/package.json"]

    @property
    def exclude_patterns(self) -> List[str]:
        return [
            "**/node_modules/**", "**/.git/**", "**/dist/**",
            "**/build/**", "**/.next/**", "**/.nuxt/**",
        ]

    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        component_root = manifest_path.parent
        rel_root = str(component_root.relative_to(repo_root))
        if rel_root == ".":
            rel_root = ""

        name = data.get("name", component_root.name)
        description = data.get("description", "")

        # Skip private workspace root packages that are just orchestrators
        if data.get("private") and data.get("workspaces") and not data.get("main"):
            # This is a workspace root — discover workspace members instead
            return self._discover_workspaces(data, manifest_path, repo_root)

        # Parse dependencies
        external_deps: List[ExternalDependency] = []
        internal_deps: List[str] = []

        for dep_section in ("dependencies", "peerDependencies"):
            for dep_name, dep_version in data.get(dep_section, {}).items():
                if isinstance(dep_version, str) and (
                    dep_version.startswith("file:")
                    or dep_version.startswith("workspace:")
                    or dep_version.startswith("link:")
                ):
                    # Internal/workspace dependency
                    internal_deps.append(dep_name)
                else:
                    external_deps.append(ExternalDependency(
                        name=dep_name,
                        version=str(dep_version) if dep_version else "",
                    ))

        kind = self._classify(data, component_root)

        return [Component(
            name=name,
            kind=kind,
            type="typescript-package" if self._has_typescript(component_root) else "javascript-package",
            root_path=rel_root or ".",
            manifest_path=str(manifest_path.relative_to(repo_root)),
            description=description,
            internal_dependencies=internal_deps,
            external_dependencies=external_deps,
        )]

    def _discover_workspaces(
        self, data: dict, manifest_path: Path, repo_root: Path
    ) -> List[Component]:
        """Discover components from workspace globs."""
        import glob as globmod

        components: List[Component] = []
        workspace_root = manifest_path.parent

        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])

        for pattern in workspaces:
            glob_pattern = str(workspace_root / pattern / "package.json")
            for ws_manifest in sorted(globmod.glob(glob_pattern)):
                ws_path = Path(ws_manifest)
                if self.should_exclude(ws_path):
                    continue
                components.extend(self.parse_manifest(ws_path, repo_root))

        return components

    def _classify(self, data: dict, component_root: Path) -> ComponentKind:
        """Classify a Node.js/TypeScript package."""
        all_deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        scripts = data.get("scripts", {})

        # Cloudflare Workers (wrangler.toml) are deployed services
        if (component_root / "wrangler.toml").exists() or (
            component_root / "wrangler.jsonc"
        ).exists():
            return ComponentKind.SERVICE

        # Has bin → CLI
        if data.get("bin"):
            return ComponentKind.CLI

        # Frontend frameworks
        frontend_deps = [
            "react", "vue", "svelte", "angular", "@angular/core",
            "next", "nuxt", "gatsby", "remix", "@remix-run/react",
            "solid-js", "preact", "lit",
        ]
        if any(dep in all_deps for dep in frontend_deps):
            return ComponentKind.FRONTEND

        # Server frameworks
        server_deps = [
            "express", "fastify", "koa", "hapi", "@hapi/hapi",
            "nestjs", "@nestjs/core", "hono",
        ]
        if any(dep in all_deps for dep in server_deps):
            # Could be frontend with a dev server — check for main/start
            if "start" in scripts or data.get("main"):
                return ComponentKind.SERVICE

        # Check for main entrypoint → service
        if data.get("main") and ("start" in scripts or "serve" in scripts):
            return ComponentKind.SERVICE

        return ComponentKind.LIBRARY

    def _has_typescript(self, component_root: Path) -> bool:
        """Check if the package uses TypeScript."""
        if (component_root / "tsconfig.json").exists():
            return True
        return any(component_root.glob("**/*.ts"))
