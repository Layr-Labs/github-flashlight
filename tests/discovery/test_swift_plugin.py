"""Tests for Swift language discovery plugin."""

import pytest
from pathlib import Path

from agent.discovery.languages.swift import SwiftPlugin
from agent.schemas.core import ComponentKind


@pytest.fixture
def plugin():
    return SwiftPlugin()


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


class TestSingleTarget:
    def test_library_package(self, plugin, repo):
        repo.write("Package.swift", """
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MyUtils",
    targets: [
        .target(name: "MyUtils"),
    ]
)
""")
        repo.write("Sources/MyUtils/Utils.swift", "public func hello() {}\n")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        assert len(comps) == 1
        assert comps[0].name == "MyUtils"
        assert comps[0].kind == ComponentKind.LIBRARY

    def test_executable_target(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "MyCLI",
    targets: [
        .executableTarget(name: "MyCLI"),
    ]
)
""")
        repo.write("Sources/MyCLI/main.swift", 'print("hello")\n')

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        cli = next(c for c in comps if c.name == "MyCLI")
        assert cli.kind == ComponentKind.CLI

    def test_server_target(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "MyServer",
    targets: [
        .executableTarget(name: "MyServer"),
    ]
)
""")
        repo.write("Sources/MyServer/main.swift", """
import Vapor
let app = try Application()
try app.run()
""")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        server = next(c for c in comps if c.name == "MyServer")
        assert server.kind == ComponentKind.SERVICE


class TestMultiTarget:
    def test_library_and_executable(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "MyProject",
    targets: [
        .target(name: "MyLib"),
        .executableTarget(
            name: "MyCLI",
            dependencies: ["MyLib"]
        ),
    ]
)
""")
        repo.write("Sources/MyLib/Lib.swift", "public struct Config {}\n")
        repo.write("Sources/MyCLI/main.swift", 'print("hello")\n')

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        names = {c.name for c in comps}
        assert "MyLib" in names
        assert "MyCLI" in names

        cli = next(c for c in comps if c.name == "MyCLI")
        assert "MyLib" in cli.internal_dependencies

    def test_test_targets_excluded(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "MyLib",
    targets: [
        .target(name: "MyLib"),
        .testTarget(name: "MyLibTests", dependencies: ["MyLib"]),
    ]
)
""")
        repo.write("Sources/MyLib/Lib.swift", "")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        names = {c.name for c in comps}
        assert "MyLib" in names
        assert "MyLibTests" not in names

    def test_root_component_created_for_multi_target(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "Workspace",
    targets: [
        .target(name: "Core"),
        .target(name: "Networking", dependencies: ["Core"]),
    ]
)
""")
        repo.write("Sources/Core/Core.swift", "")
        repo.write("Sources/Networking/Net.swift", "")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        root = next((c for c in comps if c.name == "Workspace"), None)
        assert root is not None
        assert "Core" in root.internal_dependencies
        assert "Networking" in root.internal_dependencies


class TestDependencies:
    def test_external_url_deps(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription

let package = Package(
    name: "MyApp",
    dependencies: [
        .package(url: "https://github.com/vapor/vapor.git", from: "4.0.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", exact: "1.2.3"),
    ],
    targets: [
        .target(name: "MyApp"),
    ]
)
""")
        repo.write("Sources/MyApp/App.swift", "")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        dep_names = set()
        for c in comps:
            for d in c.external_dependencies:
                dep_names.add(d.name)
        assert "vapor" in dep_names
        assert "swift-argument-parser" in dep_names

    def test_package_name_extraction(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription
let package = Package(
    name: "CoolProject",
    targets: [.target(name: "CoolProject")]
)
""")
        repo.write("Sources/CoolProject/main.swift", "")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        assert any(c.name == "CoolProject" for c in comps)


class TestClassification:
    def test_swiftui_app(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription
let package = Package(
    name: "MyApp",
    targets: [.executableTarget(name: "MyApp")]
)
""")
        repo.write("Sources/MyApp/App.swift", """
import SwiftUI

@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
""")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        app = next(c for c in comps if c.name == "MyApp")
        assert app.kind == ComponentKind.FRONTEND

    def test_argument_parser_cli(self, plugin, repo):
        repo.write("Package.swift", """
import PackageDescription
let package = Package(
    name: "MyTool",
    targets: [.executableTarget(name: "MyTool")]
)
""")
        repo.write("Sources/MyTool/main.swift", """
import ArgumentParser

struct MyTool: ParsableCommand {
    func run() { print("running") }
}
""")

        comps = plugin.parse_manifest(repo.root / "Package.swift", repo.root)
        tool = next(c for c in comps if c.name == "MyTool")
        assert tool.kind == ComponentKind.CLI
