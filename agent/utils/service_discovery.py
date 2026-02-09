"""Service discovery logic for various codebase types."""

import json
from pathlib import Path
from typing import List, Dict, Optional

from code_analysis_agent.schemas.service import Service


class ServiceDiscoverer:
    """Discovers services within a codebase."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).absolute()

    def discover_all(self) -> List[Service]:
        """
        Discover all services in the codebase.
        Supports Rust (Cargo.toml), Node.js (package.json), Python (pyproject.toml).
        """
        services = []

        # Discover Rust crates
        services.extend(self._discover_rust_services())

        # Discover Node.js packages
        services.extend(self._discover_nodejs_services())

        # Discover Python packages
        services.extend(self._discover_python_services())

        return services

    def _discover_rust_services(self) -> List[Service]:
        """Discover Rust crates by finding Cargo.toml files."""
        services = []

        # Find all Cargo.toml files
        cargo_files = list(self.repo_root.rglob("Cargo.toml"))

        for cargo_path in cargo_files:
            # Skip if in target/ directory
            if "target" in cargo_path.parts:
                continue

            try:
                # Read Cargo.toml as text (no TOML parser)
                cargo_content = cargo_path.read_text()

                # Extract package name
                name = self._extract_cargo_field(cargo_content, "name")
                if not name:
                    name = cargo_path.parent.name

                # Extract description
                description = self._extract_cargo_field(cargo_content, "description")
                if not description:
                    description = ""

                # Extract dependencies
                dependencies = self._extract_rust_dependencies(cargo_content)

                # Find key files
                key_files = self._find_rust_key_files(cargo_path.parent)

                service = Service(
                    name=name,
                    type="rust-crate",
                    root_path=cargo_path.parent,
                    manifest_path=cargo_path,
                    description=description,
                    dependencies=dependencies,
                    key_files=key_files,
                )
                services.append(service)

            except Exception as e:
                print(f"Error parsing {cargo_path}: {e}")

        return services

    def _extract_cargo_field(self, content: str, field_name: str) -> Optional[str]:
        """Extract a field value from Cargo.toml content."""
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith(f"{field_name} ="):
                # Extract value between quotes
                parts = line.split('"')
                if len(parts) >= 2:
                    return parts[1]
        return None

    def _extract_rust_dependencies(self, cargo_content: str) -> List[str]:
        """Extract internal dependencies from Cargo.toml."""
        deps = []
        lines = cargo_content.split("\n")

        in_dependencies_section = False
        for line in lines:
            line = line.strip()

            # Check if we're entering a dependencies section
            if line in ["[dependencies]", "[dev-dependencies]", "[build-dependencies]"]:
                in_dependencies_section = True
                continue

            # Check if we're leaving the section
            if line.startswith("[") and in_dependencies_section:
                in_dependencies_section = False
                continue

            # If in dependencies section and line contains "path ="
            if in_dependencies_section and "path =" in line:
                # Extract dependency name
                dep_name = line.split("=")[0].strip()
                if dep_name and not dep_name.startswith("#"):
                    deps.append(dep_name)

        return deps

    def _find_rust_key_files(self, service_root: Path) -> List[Path]:
        """Find key Rust source files."""
        key_files = []

        # Main entry points
        for entry in ["src/main.rs", "src/lib.rs"]:
            entry_path = service_root / entry
            if entry_path.exists():
                key_files.append(entry_path)

        # Find major module files in src/
        src_dir = service_root / "src"
        if src_dir.exists():
            # Add top-level .rs files (not in subdirectories)
            for rs_file in src_dir.glob("*.rs"):
                if rs_file.name not in ["main.rs", "lib.rs"]:
                    key_files.append(rs_file)

        return key_files[:20]  # Limit to prevent overwhelming

    def _discover_nodejs_services(self) -> List[Service]:
        """Discover Node.js packages by finding package.json files."""
        services = []

        # Find all package.json files
        package_files = list(self.repo_root.rglob("package.json"))

        for package_path in package_files:
            # Skip node_modules
            if "node_modules" in package_path.parts:
                continue

            try:
                package_data = json.loads(package_path.read_text())

                name = package_data.get("name", package_path.parent.name)
                description = package_data.get("description", "")

                # Extract file: dependencies (internal)
                dependencies = []
                for dep_name, dep_spec in package_data.get("dependencies", {}).items():
                    if isinstance(dep_spec, str) and dep_spec.startswith("file:"):
                        dependencies.append(dep_name)

                # Find key files
                key_files = self._find_nodejs_key_files(package_path.parent)

                service = Service(
                    name=name,
                    type="nodejs-package",
                    root_path=package_path.parent,
                    manifest_path=package_path,
                    description=description,
                    dependencies=dependencies,
                    key_files=key_files,
                )
                services.append(service)

            except Exception as e:
                print(f"Error parsing {package_path}: {e}")

        return services

    def _find_nodejs_key_files(self, service_root: Path) -> List[Path]:
        """Find key Node.js source files."""
        key_files = []

        # Main entry points
        for entry in ["index.js", "index.ts", "src/index.js", "src/index.ts"]:
            entry_path = service_root / entry
            if entry_path.exists():
                key_files.append(entry_path)

        # Find top-level source files
        for pattern in ["*.js", "*.ts"]:
            for file_path in service_root.glob(pattern):
                if file_path not in key_files:
                    key_files.append(file_path)

        return key_files[:20]

    def _discover_python_services(self) -> List[Service]:
        """Discover Python packages by finding pyproject.toml or setup.py."""
        services = []

        # Find pyproject.toml files
        pyproject_files = list(self.repo_root.rglob("pyproject.toml"))

        for pyproject_path in pyproject_files:
            try:
                content = pyproject_path.read_text()

                # Extract name (simple parsing)
                name = self._extract_toml_field(content, "name")
                if not name:
                    name = pyproject_path.parent.name

                description = self._extract_toml_field(content, "description")
                if not description:
                    description = ""

                # Find key files
                key_files = self._find_python_key_files(pyproject_path.parent)

                service = Service(
                    name=name,
                    type="python-package",
                    root_path=pyproject_path.parent,
                    manifest_path=pyproject_path,
                    description=description,
                    dependencies=[],  # Python internal deps harder to detect
                    key_files=key_files,
                )
                services.append(service)

            except Exception as e:
                print(f"Error parsing {pyproject_path}: {e}")

        return services

    def _extract_toml_field(self, content: str, field_name: str) -> Optional[str]:
        """Extract a field value from TOML content."""
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith(f"{field_name} ="):
                # Extract value between quotes
                parts = line.split('"')
                if len(parts) >= 2:
                    return parts[1]
        return None

    def _find_python_key_files(self, service_root: Path) -> List[Path]:
        """Find key Python source files."""
        key_files = []

        # Main entry points
        for entry in ["__init__.py", "main.py", "__main__.py"]:
            entry_path = service_root / entry
            if entry_path.exists():
                key_files.append(entry_path)

        # Find top-level .py files
        for py_file in service_root.glob("*.py"):
            if py_file not in key_files:
                key_files.append(py_file)

        return key_files[:20]
