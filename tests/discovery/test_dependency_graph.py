"""Tests for dependency graph with N-level depth and cycle handling."""

import pytest
from agent.schemas.dependency_graph import DependencyGraph


class TestDepthOrder:
    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.get_depth_order() == []

    def test_single_node(self):
        g = DependencyGraph()
        g.add_node("a")
        levels = g.get_depth_order()
        assert levels == [["a"]]

    def test_no_edges(self):
        g = DependencyGraph()
        for n in ["a", "b", "c"]:
            g.add_node(n)
        levels = g.get_depth_order()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_linear_chain(self):
        g = DependencyGraph()
        for n in ["a", "b", "c"]:
            g.add_node(n)
        g.add_edge("b", "a")  # b depends on a
        g.add_edge("c", "b")  # c depends on b

        levels = g.get_depth_order()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_diamond_dependency(self):
        g = DependencyGraph()
        for n in ["a", "b", "c", "d"]:
            g.add_node(n)
        g.add_edge("b", "a")
        g.add_edge("c", "a")
        g.add_edge("d", "b")
        g.add_edge("d", "c")

        levels = g.get_depth_order()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_wide_base(self):
        g = DependencyGraph()
        for n in ["a", "b", "c", "d", "e"]:
            g.add_node(n)
        g.add_edge("e", "a")
        g.add_edge("e", "b")
        g.add_edge("e", "c")
        g.add_edge("e", "d")

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b", "c", "d"}
        assert levels[1] == ["e"]


class TestCycleHandling:
    def test_simple_cycle(self):
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")

        levels = g.get_depth_order()
        # a and b form a cycle → same depth level
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b"}

    def test_cycle_with_dependent(self):
        g = DependencyGraph()
        for n in ["a", "b", "c"]:
            g.add_node(n)
        g.add_edge("a", "b")
        g.add_edge("b", "a")  # a ↔ b cycle
        g.add_edge("c", "a")  # c depends on the cycle

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b"}
        assert levels[1] == ["c"]

    def test_cycle_with_base(self):
        g = DependencyGraph()
        for n in ["base", "a", "b"]:
            g.add_node(n)
        g.add_edge("a", "base")
        g.add_edge("b", "base")
        g.add_edge("a", "b")
        g.add_edge("b", "a")  # a ↔ b cycle, both depend on base

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert levels[0] == ["base"]
        assert set(levels[1]) == {"a", "b"}

    def test_three_node_cycle(self):
        g = DependencyGraph()
        for n in ["a", "b", "c"]:
            g.add_node(n)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")

        levels = g.get_depth_order()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_multiple_sccs(self):
        g = DependencyGraph()
        for n in ["a", "b", "c", "d"]:
            g.add_node(n)
        g.add_edge("a", "b")
        g.add_edge("b", "a")  # scc1: {a, b}
        g.add_edge("c", "d")
        g.add_edge("d", "c")  # scc2: {c, d}
        g.add_edge("c", "a")  # scc2 depends on scc1

        levels = g.get_depth_order()
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b"}
        assert set(levels[1]) == {"c", "d"}


class TestLegacyInterface:
    def test_get_analysis_order(self):
        g = DependencyGraph()
        for n in ["a", "b", "c"]:
            g.add_node(n)
        g.add_edge("b", "a")
        g.add_edge("c", "b")

        phase1, phase2 = g.get_analysis_order()
        assert phase1 == ["a"]
        assert phase2 == ["b", "c"]

    def test_get_analysis_order_empty(self):
        g = DependencyGraph()
        phase1, phase2 = g.get_analysis_order()
        assert phase1 == []
        assert phase2 == []


class TestGraphOperations:
    def test_get_direct_dependencies(self):
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert g.get_direct_dependencies("a") == ["b"]
        assert g.get_direct_dependencies("b") == []

    def test_get_dependents(self):
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("b", "a")
        assert g.get_dependents("a") == ["b"]

    def test_serialization_roundtrip(self):
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("b", "a")

        d = g.to_dict()
        g2 = DependencyGraph.from_dict(d)
        assert set(g2.nodes) == {"a", "b"}
        assert g2.get_direct_dependencies("b") == ["a"]
