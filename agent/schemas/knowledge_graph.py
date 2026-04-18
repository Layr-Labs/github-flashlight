"""Unified knowledge graph schema.

Replaces the fragmented library_graph / application_graph / citation_index
with a single typed graph where:

- Nodes are Components (all 8 kinds, not collapsed to binary)
- Edges are typed relationships with metadata
- Analysis results are structured properties on nodes
- Citations are edges from claims to code locations

The graph is the source of truth. Markdown renderings are derived views.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from .core import Component, ComponentKind, CodeCitation, ExternalDependency


# ---------------------------------------------------------------------------
# Edge Types
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    """Types of relationships between nodes in the knowledge graph."""

    # Structural dependencies (discovered deterministically)
    DEPENDS_ON = "depends_on"  # Component depends on another component (any kind)

    # Runtime interactions (discovered during analysis)
    CALLS = "calls"  # Runtime call: HTTP, gRPC, message queue, etc.
    READS_FROM = "reads_from"  # Reads data from (database, cache, file)
    WRITES_TO = "writes_to"  # Writes data to (database, cache, file)

    # External integrations
    INTEGRATES_WITH = "integrates_with"  # Uses external service (AWS, Stripe, etc.)

    # Provenance
    CITED_BY = "cited_by"  # Code location supports an analysis claim


class CommunicationProtocol(str, Enum):
    """Protocol used for CALLS edges."""

    HTTP = "http"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    WEBSOCKET = "websocket"
    MESSAGE_QUEUE = "message_queue"
    EVENT_BUS = "event_bus"
    SHARED_DATABASE = "shared_database"
    SHARED_FILESYSTEM = "shared_filesystem"
    IPC = "ipc"
    UNKNOWN = "unknown"


class ExternalServiceCategory(str, Enum):
    """Categories of external services for INTEGRATES_WITH edges."""

    DATABASE = "database"
    CACHE = "cache"
    OBJECT_STORAGE = "object_storage"
    MESSAGE_BROKER = "message_broker"
    SEARCH = "search"
    MONITORING = "monitoring"
    LOGGING = "logging"
    AUTH = "auth"
    PAYMENT = "payment"
    EMAIL = "email"
    SMS = "sms"
    CDN = "cdn"
    DNS = "dns"
    BLOCKCHAIN = "blockchain"
    AI_ML = "ai_ml"
    ANALYTICS = "analytics"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Edge Data
# ---------------------------------------------------------------------------


@dataclass
class Edge:
    """A typed, directed edge in the knowledge graph."""

    source: str  # Source node ID (component name or external service ID)
    target: str  # Target node ID
    edge_type: EdgeType
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Optional fields populated based on edge_type
    protocol: Optional[CommunicationProtocol] = None  # For CALLS edges
    description: str = ""
    confidence: float = 1.0  # 1.0 = deterministic, <1.0 = inferred by LLM

    def to_dict(self) -> dict:
        d = {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type.value,
        }
        if self.protocol:
            d["protocol"] = self.protocol.value
        if self.description:
            d["description"] = self.description
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            source=data["source"],
            target=data["target"],
            edge_type=EdgeType(data["type"]),
            protocol=CommunicationProtocol(data["protocol"])
            if data.get("protocol")
            else None,
            description=data.get("description", ""),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# External Service Node (not a Component, but a node in the graph)
# ---------------------------------------------------------------------------


@dataclass
class ExternalService:
    """An external service that components integrate with.

    External services are nodes in the graph but not Components (they don't
    have source code, manifests, or analysis). They exist to be targets of
    INTEGRATES_WITH edges.
    """

    id: str  # Unique identifier (e.g., "aws-s3", "postgresql", "stripe")
    name: str  # Display name (e.g., "AWS S3", "PostgreSQL", "Stripe")
    category: ExternalServiceCategory
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "node_type": "external_service",
        }
        if self.description:
            d["description"] = self.description
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExternalService":
        return cls(
            id=data["id"],
            name=data["name"],
            category=ExternalServiceCategory(data["category"]),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Analysis Properties (the "body" of a node)
# ---------------------------------------------------------------------------


@dataclass
class APIEndpoint:
    """An API endpoint exposed by a component."""

    path: str
    method: str = ""  # GET, POST, etc. (empty for non-HTTP)
    description: str = ""
    auth_required: bool = False
    request_schema: str = ""  # JSON schema or type reference
    response_schema: str = ""

    def to_dict(self) -> dict:
        d = {"path": self.path}
        if self.method:
            d["method"] = self.method
        if self.description:
            d["description"] = self.description
        if self.auth_required:
            d["auth_required"] = True
        if self.request_schema:
            d["request_schema"] = self.request_schema
        if self.response_schema:
            d["response_schema"] = self.response_schema
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "APIEndpoint":
        return cls(
            path=data["path"],
            method=data.get("method", ""),
            description=data.get("description", ""),
            auth_required=data.get("auth_required", False),
            request_schema=data.get("request_schema", ""),
            response_schema=data.get("response_schema", ""),
        )


@dataclass
class DataFlow:
    """A data flow through the component."""

    name: str
    steps: List[str]  # Ordered list of step descriptions
    description: str = ""
    mermaid: str = ""  # Optional Mermaid diagram

    def to_dict(self) -> dict:
        d = {"name": self.name, "steps": self.steps}
        if self.description:
            d["description"] = self.description
        if self.mermaid:
            d["mermaid"] = self.mermaid
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataFlow":
        return cls(
            name=data["name"],
            steps=data.get("steps", []),
            description=data.get("description", ""),
            mermaid=data.get("mermaid", ""),
        )


@dataclass
class DesignDecision:
    """A design decision captured during analysis."""

    decision: str
    rationale: str
    alternatives: List[str] = field(default_factory=list)
    consequences: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {"decision": self.decision, "rationale": self.rationale}
        if self.alternatives:
            d["alternatives"] = self.alternatives
        if self.consequences:
            d["consequences"] = self.consequences
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DesignDecision":
        return cls(
            decision=data["decision"],
            rationale=data.get("rationale", ""),
            alternatives=data.get("alternatives", []),
            consequences=data.get("consequences", []),
        )


@dataclass
class AnalysisResult:
    """Structured analysis result that becomes node properties.

    This is the "body" of a component node — the knowledge extracted
    by the LLM subagent during analysis.
    """

    # Summary
    summary: str = ""
    architecture_pattern: str = ""  # e.g., "hexagonal", "layered", "event-driven"

    # Structure
    key_modules: List[Dict[str, str]] = field(
        default_factory=list
    )  # [{name, path, description}]
    api_endpoints: List[APIEndpoint] = field(default_factory=list)
    data_flows: List[DataFlow] = field(default_factory=list)

    # Design
    design_decisions: List[DesignDecision] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)

    # Quality observations
    security_notes: List[str] = field(default_factory=list)
    performance_notes: List[str] = field(default_factory=list)
    scalability_notes: List[str] = field(default_factory=list)

    # Provenance
    citations: List[CodeCitation] = field(default_factory=list)

    # Raw markdown (for rendering, not querying)
    raw_markdown: str = ""

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {}
        if self.summary:
            d["summary"] = self.summary
        if self.architecture_pattern:
            d["architecture_pattern"] = self.architecture_pattern
        if self.key_modules:
            d["key_modules"] = self.key_modules
        if self.api_endpoints:
            d["api_endpoints"] = [e.to_dict() for e in self.api_endpoints]
        if self.data_flows:
            d["data_flows"] = [f.to_dict() for f in self.data_flows]
        if self.design_decisions:
            d["design_decisions"] = [dd.to_dict() for dd in self.design_decisions]
        if self.tech_stack:
            d["tech_stack"] = self.tech_stack
        if self.security_notes:
            d["security_notes"] = self.security_notes
        if self.performance_notes:
            d["performance_notes"] = self.performance_notes
        if self.scalability_notes:
            d["scalability_notes"] = self.scalability_notes
        if self.citations:
            d["citations"] = [c.to_dict() for c in self.citations]
        # Note: raw_markdown is not serialized to JSON to save space
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisResult":
        return cls(
            summary=data.get("summary", ""),
            architecture_pattern=data.get("architecture_pattern", ""),
            key_modules=data.get("key_modules", []),
            api_endpoints=[
                APIEndpoint.from_dict(e) for e in data.get("api_endpoints", [])
            ],
            data_flows=[DataFlow.from_dict(f) for f in data.get("data_flows", [])],
            design_decisions=[
                DesignDecision.from_dict(dd) for dd in data.get("design_decisions", [])
            ],
            tech_stack=data.get("tech_stack", []),
            security_notes=data.get("security_notes", []),
            performance_notes=data.get("performance_notes", []),
            scalability_notes=data.get("scalability_notes", []),
            citations=[CodeCitation.from_dict(c) for c in data.get("citations", [])],
            raw_markdown=data.get("raw_markdown", ""),
        )


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeGraph:
    """Unified knowledge graph for a codebase.

    Contains:
    - Component nodes (all 8 kinds)
    - External service nodes
    - Typed edges (depends_on, calls, integrates_with, etc.)
    - Analysis results as node properties

    The graph supports:
    - Topological ordering for analysis phase scheduling
    - Traversal queries (what depends on X? what does Y call?)
    - Filtering by node kind, edge type, etc.
    """

    # Nodes
    components: Dict[str, Component] = field(default_factory=dict)  # name -> Component
    external_services: Dict[str, ExternalService] = field(
        default_factory=dict
    )  # id -> ExternalService

    # Analysis results (separate from Component to allow incremental updates)
    analysis_results: Dict[str, AnalysisResult] = field(
        default_factory=dict
    )  # component name -> analysis

    # Edges
    edges: List[Edge] = field(default_factory=list)

    # Metadata
    source_repo: str = ""
    source_commit: str = ""
    schema_version: str = "2.0.0"  # Bump from 1.0.0 to indicate new unified schema

    # -----------------------------------------------------------------------
    # Node operations
    # -----------------------------------------------------------------------

    def add_component(self, component: Component) -> None:
        """Add a component node."""
        self.components[component.name] = component

    def add_external_service(self, service: ExternalService) -> None:
        """Add an external service node."""
        self.external_services[service.id] = service

    def set_analysis(self, component_name: str, analysis: AnalysisResult) -> None:
        """Set the analysis result for a component."""
        self.analysis_results[component_name] = analysis

    def get_node_ids(self) -> Set[str]:
        """Get all node IDs (components + external services)."""
        return set(self.components.keys()) | set(self.external_services.keys())

    # -----------------------------------------------------------------------
    # Edge operations
    # -----------------------------------------------------------------------

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def add_dependency(
        self,
        source: str,
        target: str,
        description: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Add a DEPENDS_ON edge (structural dependency)."""
        self.edges.append(
            Edge(
                source=source,
                target=target,
                edge_type=EdgeType.DEPENDS_ON,
                description=description,
                confidence=confidence,
            )
        )

    def add_call(
        self,
        source: str,
        target: str,
        protocol: CommunicationProtocol,
        description: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Add a CALLS edge (runtime interaction)."""
        self.edges.append(
            Edge(
                source=source,
                target=target,
                edge_type=EdgeType.CALLS,
                protocol=protocol,
                description=description,
                confidence=confidence,
            )
        )

    def add_integration(
        self,
        component: str,
        service_id: str,
        description: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Add an INTEGRATES_WITH edge."""
        self.edges.append(
            Edge(
                source=component,
                target=service_id,
                edge_type=EdgeType.INTEGRATES_WITH,
                description=description,
                confidence=confidence,
            )
        )

    def get_edges_from(
        self, node_id: str, edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges originating from a node."""
        edges = [e for e in self.edges if e.source == node_id]
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return edges

    def get_edges_to(
        self, node_id: str, edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges pointing to a node."""
        edges = [e for e in self.edges if e.target == node_id]
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return edges

    def get_dependencies(self, component_name: str) -> List[str]:
        """Get direct dependencies of a component (DEPENDS_ON targets)."""
        return [
            e.target for e in self.get_edges_from(component_name, EdgeType.DEPENDS_ON)
        ]

    def get_dependents(self, component_name: str) -> List[str]:
        """Get components that depend on this component."""
        return [
            e.source for e in self.get_edges_to(component_name, EdgeType.DEPENDS_ON)
        ]

    # -----------------------------------------------------------------------
    # Analysis ordering (replaces the binary library/application phases)
    # -----------------------------------------------------------------------

    def get_depth_order(self) -> List[List[str]]:
        """Get depth-ordered analysis buckets for all components.

        Returns a list of lists where:
            depth[0] = components with no dependencies (can analyze in parallel)
            depth[1] = components depending only on depth 0
            depth[N] = components depending on depth N-1 or lower

        This replaces the old binary Phase 1 (libraries) / Phase 2 (applications)
        with an N-level ordering based on actual dependency structure.
        """
        # Build adjacency for DEPENDS_ON edges only
        component_names = set(self.components.keys())
        adj: Dict[str, List[str]] = defaultdict(list)

        for edge in self.edges:
            if edge.edge_type == EdgeType.DEPENDS_ON:
                if edge.source in component_names and edge.target in component_names:
                    adj[edge.source].append(edge.target)

        # Tarjan's SCC to handle cycles
        sccs = self._find_sccs(component_names, adj)

        # Assign each node to its SCC index
        node_to_scc: Dict[str, int] = {}
        for i, scc in enumerate(sccs):
            for node in scc:
                node_to_scc[node] = i

        # Build DAG of SCCs
        scc_edges: Dict[int, Set[int]] = {i: set() for i in range(len(sccs))}
        for node in component_names:
            for dep in adj.get(node, []):
                src_scc = node_to_scc[node]
                dst_scc = node_to_scc[dep]
                if src_scc != dst_scc:
                    scc_edges[src_scc].add(dst_scc)

        # Compute depth on SCC DAG
        scc_depth: Dict[int, int] = {}

        def compute_depth(scc_idx: int) -> int:
            if scc_idx in scc_depth:
                return scc_depth[scc_idx]
            deps = scc_edges.get(scc_idx, set())
            if not deps:
                scc_depth[scc_idx] = 0
                return 0
            max_dep = max(compute_depth(d) for d in deps)
            scc_depth[scc_idx] = max_dep + 1
            return scc_depth[scc_idx]

        for i in range(len(sccs)):
            compute_depth(i)

        # Map nodes to depths
        depth_map: Dict[str, int] = {}
        for node in component_names:
            depth_map[node] = scc_depth[node_to_scc[node]]

        # Group by depth
        if not depth_map:
            return []

        max_depth = max(depth_map.values())
        levels: List[List[str]] = [[] for _ in range(max_depth + 1)]
        for node, depth in sorted(depth_map.items()):
            levels[depth].append(node)

        return levels

    def _find_sccs(
        self,
        nodes: Set[str],
        adj: Dict[str, List[str]],
    ) -> List[List[str]]:
        """Find strongly connected components using Tarjan's algorithm."""
        index_counter = [0]
        stack: List[str] = []
        lowlinks: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Dict[str, bool] = {}
        sccs: List[List[str]] = []

        def strongconnect(node: str):
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            for dep in adj.get(node, []):
                if dep not in nodes:
                    continue
                if dep not in index:
                    strongconnect(dep)
                    lowlinks[node] = min(lowlinks[node], lowlinks[dep])
                elif on_stack.get(dep, False):
                    lowlinks[node] = min(lowlinks[node], index[dep])

            if lowlinks[node] == index[node]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == node:
                        break
                sccs.append(scc)

        for node in nodes:
            if node not in index:
                strongconnect(node)

        return sccs

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    def components_by_kind(self, kind: ComponentKind) -> List[Component]:
        """Get all components of a specific kind."""
        return [c for c in self.components.values() if c.kind == kind]

    def components_with_analysis(self) -> List[str]:
        """Get names of components that have analysis results."""
        return list(self.analysis_results.keys())

    def components_without_analysis(self) -> List[str]:
        """Get names of components missing analysis results."""
        return [name for name in self.components if name not in self.analysis_results]

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "schema_version": self.schema_version,
            "source_repo": self.source_repo,
            "source_commit": self.source_commit,
            "nodes": {
                "components": {
                    name: comp.to_dict() for name, comp in self.components.items()
                },
                "external_services": {
                    id: svc.to_dict() for id, svc in self.external_services.items()
                },
            },
            "edges": [e.to_dict() for e in self.edges],
            "analysis": {
                name: analysis.to_dict()
                for name, analysis in self.analysis_results.items()
            },
            "metadata": {
                "component_count": len(self.components),
                "external_service_count": len(self.external_services),
                "edge_count": len(self.edges),
                "analyzed_count": len(self.analysis_results),
                "by_kind": {
                    kind.value: sum(
                        1 for c in self.components.values() if c.kind == kind
                    )
                    for kind in ComponentKind
                    if any(c.kind == kind for c in self.components.values())
                },
                "by_edge_type": {
                    etype.value: sum(1 for e in self.edges if e.edge_type == etype)
                    for etype in EdgeType
                    if any(e.edge_type == etype for e in self.edges)
                },
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGraph":
        """Deserialize from dictionary."""
        graph = cls(
            source_repo=data.get("source_repo", ""),
            source_commit=data.get("source_commit", ""),
            schema_version=data.get("schema_version", "2.0.0"),
        )

        # Load components
        nodes = data.get("nodes", {})
        for name, comp_data in nodes.get("components", {}).items():
            graph.components[name] = Component.from_dict(comp_data)

        # Load external services
        for id, svc_data in nodes.get("external_services", {}).items():
            graph.external_services[id] = ExternalService.from_dict(svc_data)

        # Load edges
        for edge_data in data.get("edges", []):
            graph.edges.append(Edge.from_dict(edge_data))

        # Load analysis results
        for name, analysis_data in data.get("analysis", {}).items():
            graph.analysis_results[name] = AnalysisResult.from_dict(analysis_data)

        return graph


# ---------------------------------------------------------------------------
# Builder for constructing graph from discovery + analysis
# ---------------------------------------------------------------------------


class KnowledgeGraphBuilder:
    """Builds a KnowledgeGraph from discovered components.

    Replaces the old DependencyGraphBuilder which only handled libraries.
    This builder:
    1. Takes all components (any kind)
    2. Creates DEPENDS_ON edges from internal_dependencies
    3. Returns a KnowledgeGraph ready for analysis phase scheduling
    """

    def __init__(self, components: List[Component]):
        self.components = {c.name: c for c in components}
        self.graph = KnowledgeGraph()

    def build(
        self,
        source_repo: str = "",
        source_commit: str = "",
    ) -> KnowledgeGraph:
        """Build the knowledge graph from components.

        This creates the initial graph structure with:
        - All component nodes
        - DEPENDS_ON edges from internal_dependencies

        Analysis results and runtime edges (CALLS, INTEGRATES_WITH) are
        added later during the analysis phase.
        """
        self.graph.source_repo = source_repo
        self.graph.source_commit = source_commit

        # Add all components as nodes
        for comp in self.components.values():
            self.graph.add_component(comp)

        # Add DEPENDS_ON edges from internal_dependencies
        for comp in self.components.values():
            for dep_name in comp.internal_dependencies:
                if dep_name in self.components:
                    self.graph.add_dependency(
                        source=comp.name,
                        target=dep_name,
                        confidence=1.0,  # Deterministic from manifest
                    )

        return self.graph

    def get_analysis_order(self) -> List[List[str]]:
        """Get depth-ordered component buckets for analysis scheduling."""
        return self.graph.get_depth_order()
