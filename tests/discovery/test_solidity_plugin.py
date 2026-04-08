"""Tests for Solidity language discovery plugin."""

import pytest
from pathlib import Path

from agent.discovery.languages.solidity import SolidityPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return SolidityPlugin()


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


class TestFoundryProject:
    def test_basic_foundry(self, plugin, repo):
        repo.write("foundry.toml", """
[profile.default]
src = "src"
test = "test"
libs = ["lib"]
""")
        repo.write("src/MyContract.sol", """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MyContract {
    uint256 public value;
}
""")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        # Flat src/ → single component
        assert len(comps) == 1
        assert comps[0].kind == ComponentKind.CONTRACT
        assert "contract" in comps[0].metadata.get("declarations", {})

    def test_multi_package_src(self, plugin, repo):
        repo.write("foundry.toml", """
[profile.default]
src = "src"
libs = ["lib"]
""")
        repo.write("src/core/Token.sol", """
pragma solidity ^0.8.20;
contract Token {}
interface IToken {}
""")
        repo.write("src/periphery/Router.sol", """
pragma solidity ^0.8.20;
import "src/core/Token.sol";
contract Router {}
""")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        names = {c.name for c in comps}
        assert "core" in names
        assert "periphery" in names

        # Root project component
        root = next((c for c in comps if "contracts" in c.name.lower() or c.root_path == "."), None)
        assert root is not None

    def test_import_tracing(self, plugin, repo):
        repo.write("foundry.toml", '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n')
        repo.write("src/core/Base.sol", "pragma solidity ^0.8.20;\ncontract Base {}\n")
        repo.write("src/extensions/Extended.sol", """
pragma solidity ^0.8.20;
import "src/core/Base.sol";
contract Extended {}
""")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        ext = next((c for c in comps if c.name == "extensions"), None)
        assert ext is not None
        assert "core" in ext.internal_dependencies

    def test_external_deps_from_lib(self, plugin, repo):
        repo.write("foundry.toml", '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n')
        repo.write("src/MyContract.sol", "pragma solidity ^0.8.20;\ncontract MyContract {}\n")
        (repo.root / "lib" / "forge-std").mkdir(parents=True)
        (repo.root / "lib" / "openzeppelin-contracts").mkdir(parents=True)

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        dep_names = set()
        for c in comps:
            for d in c.external_dependencies:
                dep_names.add(d.name)
        assert "forge-std" in dep_names
        assert "openzeppelin-contracts" in dep_names

    def test_solidity_version_detection(self, plugin, repo):
        repo.write("foundry.toml", '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n')
        repo.write("src/Contract.sol", "pragma solidity ^0.8.20;\ncontract C {}\n")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        assert any(
            c.metadata.get("solidity_version") == "^0.8.20"
            for c in comps
        )


class TestDeclarationClassification:
    def test_library_only(self, plugin, repo):
        repo.write("foundry.toml", '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n')
        repo.write("src/Math.sol", """
pragma solidity ^0.8.20;
library MathLib { function add(uint a, uint b) internal pure returns (uint) { return a + b; } }
library StringLib {}
""")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        lib_comp = next(c for c in comps if c.metadata.get("declarations"))
        assert lib_comp.kind == ComponentKind.LIBRARY

    def test_interface_only(self, plugin, repo):
        repo.write("foundry.toml", '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n')
        repo.write("src/IToken.sol", """
pragma solidity ^0.8.20;
interface IToken { function transfer(address, uint) external; }
interface IERC20 {}
""")

        comps = plugin.parse_manifest(repo.root / "foundry.toml", repo.root)
        iface_comp = next(c for c in comps if c.metadata.get("declarations"))
        assert iface_comp.kind == ComponentKind.CONTRACT
