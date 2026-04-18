"""Tests for knowledge graph with N-level depth and cycle handling."""

import pytest
from agent.schemas.core import Component, ComponentKind
from agent.schemas.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphBuilder,
    Edge,
    EdgeType,
    ExternalService,
    ExternalServiceCategory,
)


def make_component(
    name: str, kind: ComponentKind = ComponentKind.LIBRARY, deps: list[str] = None
) -> Component:
    """Helper to create a test component."""
    return Component(
        name=name,
        kind=kind,
        type="test-type",
        root_path=f"packages/{name}",
        internal_dependencies=deps or [],
    )


class TestDepthOrder:
    def test_empty_graph(self):
        g = KnowledgeGraph()
        assert g.get_depth_order() == []

    def test_single_node(self):
        g = KnowledgeGraph()
        g.add_component(make_component("a"))
        levels = g.get_depth_order()
        assert levels == [["a"]]

    def test_no_edges(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c"]:
            g.add_component(make_component(n))
        levels = g.get_depth_order()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_linear_chain(self):
        g = KnowledgeGraph()
        g.add_component(make_component("a"))
        g.add_component(make_component("b"))
        g.add_component(make_component("c"))
        g.add_dependency("b", "a")  # b depends on a
        g.add_dependency("c", "b")  # c depends on b

        levels = g.get_depth_order()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_diamond_dependency(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c", "d"]:
            g.add_component(make_component(n))
        g.add_dependency("b", "a")
        g.add_dependency("c", "a")
        g.add_dependency("d", "b")
        g.add_dependency("d", "c")

        levels = g.get_depth_order()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_wide_base(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c", "d", "e"]:
            g.add_component(make_component(n))
        g.add_dependency("e", "a")
        g.add_dependency("e", "b")
        g.add_dependency("e", "c")
        g.add_dependency("e", "d")

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b", "c", "d"}
        assert levels[1] == ["e"]


class TestCycleHandling:
    def test_simple_cycle(self):
        g = KnowledgeGraph()
        g.add_component(make_component("a"))
        g.add_component(make_component("b"))
        g.add_dependency("a", "b")
        g.add_dependency("b", "a")

        levels = g.get_depth_order()
        # a and b form a cycle -> same depth level
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b"}

    def test_cycle_with_dependent(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c"]:
            g.add_component(make_component(n))
        g.add_dependency("a", "b")
        g.add_dependency("b", "a")  # a <-> b cycle
        g.add_dependency("c", "a")  # c depends on the cycle

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b"}
        assert levels[1] == ["c"]

    def test_cycle_with_base(self):
        g = KnowledgeGraph()
        for n in ["base", "a", "b"]:
            g.add_component(make_component(n))
        g.add_dependency("a", "base")
        g.add_dependency("b", "base")
        g.add_dependency("a", "b")
        g.add_dependency("b", "a")  # a <-> b cycle, both depend on base

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert levels[0] == ["base"]
        assert set(levels[1]) == {"a", "b"}

    def test_three_node_cycle(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c"]:
            g.add_component(make_component(n))
        g.add_dependency("a", "b")
        g.add_dependency("b", "c")
        g.add_dependency("c", "a")

        levels = g.get_depth_order()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_multiple_sccs(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c", "d"]:
            g.add_component(make_component(n))
        g.add_dependency("a", "b")
        g.add_dependency("b", "a")  # scc1: {a, b}
        g.add_dependency("c", "d")
        g.add_dependency("d", "c")  # scc2: {c, d}
        g.add_dependency("c", "a")  # scc2 depends on scc1

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b"}
        assert set(levels[1]) == {"c", "d"}


class TestGraphBuilder:
    def test_builder_creates_edges_from_internal_deps(self):
        components = [
            make_component("a"),
            make_component("b", deps=["a"]),
            make_component("c", deps=["a", "b"]),
        ]
        builder = KnowledgeGraphBuilder(components)
        graph = builder.build()

        assert len(graph.components) == 3
        assert len(graph.edges) == 3  # b->a, c->a, c->b

        deps_b = graph.get_dependencies("b")
        assert deps_b == ["a"]

        deps_c = graph.get_dependencies("c")
        assert set(deps_c) == {"a", "b"}

    def test_builder_analysis_order(self):
        components = [
            make_component("a"),
            make_component("b", deps=["a"]),
            make_component("c", deps=["b"]),
        ]
        builder = KnowledgeGraphBuilder(components)
        builder.build()

        order = builder.get_analysis_order()
        assert len(order) == 3
        assert order[0] == ["a"]
        assert order[1] == ["b"]
        assert order[2] == ["c"]


class TestMixedComponentKinds:
    def test_all_kinds_in_one_graph(self):
        components = [
            make_component("utils-lib", ComponentKind.LIBRARY),
            make_component("api-service", ComponentKind.SERVICE, deps=["utils-lib"]),
            make_component("cli-tool", ComponentKind.CLI, deps=["utils-lib"]),
            make_component("token-contract", ComponentKind.CONTRACT),
            make_component(
                "frontend-app", ComponentKind.FRONTEND, deps=["api-service"]
            ),
        ]
        builder = KnowledgeGraphBuilder(components)
        graph = builder.build()

        assert len(graph.components) == 5

        # Check depth ordering works across kinds
        order = builder.get_analysis_order()
        # utils-lib and token-contract have no deps -> depth 0
        # api-service and cli-tool depend on utils-lib -> depth 1
        # frontend-app depends on api-service -> depth 2
        assert len(order) == 3
        assert set(order[0]) == {"utils-lib", "token-contract"}
        assert set(order[1]) == {"api-service", "cli-tool"}
        assert order[2] == ["frontend-app"]

    def test_components_by_kind(self):
        components = [
            make_component("lib1", ComponentKind.LIBRARY),
            make_component("lib2", ComponentKind.LIBRARY),
            make_component("svc1", ComponentKind.SERVICE),
            make_component("cli1", ComponentKind.CLI),
        ]
        builder = KnowledgeGraphBuilder(components)
        graph = builder.build()

        libs = graph.components_by_kind(ComponentKind.LIBRARY)
        assert len(libs) == 2
        assert {c.name for c in libs} == {"lib1", "lib2"}

        svcs = graph.components_by_kind(ComponentKind.SERVICE)
        assert len(svcs) == 1
        assert svcs[0].name == "svc1"


class TestEdgeTypes:
    def test_different_edge_types(self):
        g = KnowledgeGraph()
        g.add_component(make_component("a", ComponentKind.SERVICE))
        g.add_component(make_component("b", ComponentKind.SERVICE))
        g.add_external_service(
            ExternalService(
                id="postgres",
                name="PostgreSQL",
                category=ExternalServiceCategory.DATABASE,
            )
        )

        g.add_dependency("b", "a")
        g.add_call(
            "a",
            "b",
            protocol=g.__class__.__module__.split(".")[0]
            and __import__(
                "agent.schemas.knowledge_graph", fromlist=["CommunicationProtocol"]
            ).CommunicationProtocol.HTTP,
        )
        g.add_integration("a", "postgres", description="Primary data store")

        deps = g.get_edges_from("b", EdgeType.DEPENDS_ON)
        assert len(deps) == 1
        assert deps[0].target == "a"

        integrations = g.get_edges_from("a", EdgeType.INTEGRATES_WITH)
        assert len(integrations) == 1
        assert integrations[0].target == "postgres"

    def test_get_dependents(self):
        g = KnowledgeGraph()
        for n in ["a", "b", "c"]:
            g.add_component(make_component(n))
        g.add_dependency("b", "a")
        g.add_dependency("c", "a")

        dependents = g.get_dependents("a")
        assert set(dependents) == {"b", "c"}


class TestSerialization:
    def test_roundtrip(self):
        g = KnowledgeGraph()
        g.source_repo = "https://github.com/test/repo"
        g.source_commit = "abc123"

        g.add_component(make_component("a"))
        g.add_component(make_component("b", deps=["a"]))
        g.add_dependency("b", "a")
        g.add_external_service(
            ExternalService(
                id="redis",
                name="Redis",
                category=ExternalServiceCategory.CACHE,
            )
        )
        g.add_integration("a", "redis")

        d = g.to_dict()
        g2 = KnowledgeGraph.from_dict(d)

        assert g2.source_repo == "https://github.com/test/repo"
        assert g2.source_commit == "abc123"
        assert len(g2.components) == 2
        assert len(g2.external_services) == 1
        assert len(g2.edges) == 2  # depends_on + integrates_with
        assert g2.get_dependencies("b") == ["a"]
