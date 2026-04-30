"""Tests for Rust language discovery plugin."""

import pytest
from pathlib import Path

from agent.discovery.languages.rust import RustPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return RustPlugin()


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


class TestSingleCrate:
    def test_library_crate(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-utils"
version = "0.1.0"

[lib]

[dependencies]
serde = "1.0"
""")
        repo.write("src/lib.rs", "pub fn hello() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "my-utils"
        assert comps[0].kind == ComponentKind.LIBRARY

    def test_binary_crate_service(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-server"
version = "0.1.0"

[[bin]]
name = "my-server"
path = "src/main.rs"

[dependencies]
axum = "0.7"
tokio = "1.0"
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert comps[0].kind == ComponentKind.SERVICE

    def test_cli_crate(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-tool"
version = "0.1.0"

[dependencies]
clap = "4.0"
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert comps[0].kind == ComponentKind.CLI

    def test_extracts_external_deps(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-lib"

[dependencies]
serde = "1.0"
tokio = { version = "1.35", features = ["full"] }
""")
        repo.write("src/lib.rs", "")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        dep_names = {d.name for d in comps[0].external_dependencies}
        assert "serde" in dep_names
        assert "tokio" in dep_names

    def test_internal_path_deps(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-app"

[dependencies]
my-lib = { path = "../my-lib" }
serde = "1.0"
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert "my-lib" in comps[0].internal_dependencies
        ext_names = {d.name for d in comps[0].external_dependencies}
        assert "my-lib" not in ext_names


class TestWorkspace:
    def test_workspace_discovers_members(self, plugin, repo):
        repo.write("Cargo.toml", """
[workspace]
members = [
    "crates/core",
    "crates/cli",
]
""")
        repo.write("crates/core/Cargo.toml", """
[package]
name = "my-core"
[lib]
[dependencies]
serde = "1.0"
""")
        repo.write("crates/core/src/lib.rs", "")
        repo.write("crates/cli/Cargo.toml", """
[package]
name = "my-cli"
[dependencies]
my-core = { path = "../core" }
clap = "4.0"
""")
        repo.write("crates/cli/src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        names = {c.name for c in comps}
        assert "my-core" in names
        assert "my-cli" in names

        cli = next(c for c in comps if c.name == "my-cli")
        assert "my-core" in cli.internal_dependencies

    def test_hybrid_lib_and_bin(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-crate"
[lib]
[[bin]]
name = "my-crate"
""")
        repo.write("src/lib.rs", "")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert comps[0].kind == ComponentKind.LIBRARY  # same-name bin → library


class TestHybridAndExecutableClassification:
    """Corpus findings: [[bin]] with distinct name indicates executable,
    bare executables default to CLI not SERVICE."""

    def test_hybrid_with_distinct_bin_name_is_executable(self, plugin, repo):
        # tauri-cli pattern: lib + bin named cargo-tauri
        repo.write("Cargo.toml", """
[package]
name = "tauri-cli"
[lib]
[[bin]]
name = "cargo-tauri"
path = "src/main.rs"

[dependencies]
clap = "4.0"
""")
        repo.write("src/lib.rs", "")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert comps[0].kind == ComponentKind.CLI

    def test_bare_executable_defaults_to_cli(self, plugin, repo):
        # Bare build-time binary with no framework hints — should be CLI
        repo.write("Cargo.toml", """
[package]
name = "my-packer"
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert comps[0].kind == ComponentKind.CLI


class TestNonDefaultDependencyTables:
    """Corpus findings: path-based deps in [dev-dependencies],
    [build-dependencies], and [target.*.dependencies] must produce
    internal edges."""

    def test_dev_dependency_path_is_internal(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-app"

[dev-dependencies]
mock-service = { path = "../mock-service" }
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert "mock-service" in comps[0].internal_dependencies

    def test_build_dependency_path_is_internal(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-app"

[build-dependencies]
hbb_common = { path = "libs/hbb_common" }
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert "hbb_common" in comps[0].internal_dependencies

    def test_target_specific_dependency_path_is_internal(self, plugin, repo):
        repo.write("Cargo.toml", """
[package]
name = "my-app"

[target.'cfg(target_os = "linux")'.dependencies]
linux-shim = { path = "../linux-shim" }
""")
        repo.write("src/main.rs", "fn main() {}\n")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        assert "linux-shim" in comps[0].internal_dependencies

    def test_dev_dep_external_not_in_runtime_externals(self, plugin, repo):
        # dev/build deps are test-time; they shouldn't leak into runtime externals
        repo.write("Cargo.toml", """
[package]
name = "my-lib"

[dependencies]
serde = "1.0"

[dev-dependencies]
criterion = "0.5"
""")
        repo.write("src/lib.rs", "")

        comps = plugin.parse_manifest(repo.root / "Cargo.toml", repo.root)
        ext_names = {d.name for d in comps[0].external_dependencies}
        assert "serde" in ext_names
        assert "criterion" not in ext_names
