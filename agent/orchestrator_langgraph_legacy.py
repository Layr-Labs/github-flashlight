"""Layer-aware parallel orchestration for multi-agent analysis.

This module implements deterministic, layer-based parallel dispatch of subagents
based on the component dependency graph. Instead of relying on LLM ReAct reasoning
to decide when to spawn subagents, we:

1. Build a dependency graph from discovered components
2. Compute topological layers (leaves first, then dependents)
3. Dispatch all subagents within a layer in parallel
4. Wait for layer completion before proceeding to the next layer
5. Pass accumulated context from prior layers to subsequent ones

Architecture:
                    ┌─────────────────────────────────────┐
                    │       Component Discovery            │
                    │   (discover_components from engine)  │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │      Dependency Graph Builder        │
                    │   (build_dependency_layers)          │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │            LAYER 0 (Leaves)          │
                    │     [parallel: crypto, utils, ...]   │
                    └─────────────────┬───────────────────┘
                                      │ await all
                    ┌─────────────────▼───────────────────┐
                    │            LAYER 1                   │
                    │     [parallel: auth, storage, ...]   │
                    └─────────────────┬───────────────────┘
                                      │ await all
                    ┌─────────────────▼───────────────────┐
                    │            LAYER N (Root)            │
                    │     [parallel: main-app, ...]        │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │       Synthesis (Lead Agent)         │
                    │   Combine all results into docs      │
                    └─────────────────────────────────────┘
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.callbacks import FlashlightCallbackHandler
from agent.schemas.core import Component, ComponentKind

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency graph and layer computation
# ---------------------------------------------------------------------------


def build_dependency_graph(
    components: List[Component],
) -> Dict[str, Set[str]]:
    """Build adjacency list representation of component dependencies.

    Args:
        components: List of discovered components with internal_dependencies.

    Returns:
        Dict mapping component name -> set of component names it depends on.
    """
    # Create name -> component mapping
    by_name = {c.name: c for c in components}

    # Build adjacency list (component -> its dependencies)
    graph: Dict[str, Set[str]] = {}
    for comp in components:
        deps = set()
        for dep_name in comp.internal_dependencies:
            if dep_name in by_name:
                deps.add(dep_name)
        graph[comp.name] = deps

    return graph


def compute_topological_layers(
    graph: Dict[str, Set[str]],
) -> List[List[str]]:
    """Compute topological layers using Kahn's algorithm variant.

    Layer 0 contains nodes with no dependencies (leaves).
    Layer N contains nodes whose dependencies are all in layers < N.

    Args:
        graph: Adjacency list (node -> set of dependencies).

    Returns:
        List of layers, where each layer is a list of component names
        that can be processed in parallel.

    Raises:
        ValueError: If the graph contains cycles.
    """
    # Compute in-degree (number of dependents) for each node
    # We want reverse topological order: leaves first
    # So we track how many deps each node has remaining
    remaining_deps: Dict[str, int] = {node: len(deps) for node, deps in graph.items()}

    # Reverse graph: for each node, who depends on it?
    dependents: Dict[str, Set[str]] = defaultdict(set)
    for node, deps in graph.items():
        for dep in deps:
            dependents[dep].add(node)

    layers: List[List[str]] = []
    processed: Set[str] = set()

    while len(processed) < len(graph):
        # Find all nodes with no remaining dependencies
        current_layer = [
            node
            for node, deps_left in remaining_deps.items()
            if deps_left == 0 and node not in processed
        ]

        if not current_layer:
            # No progress = cycle detected
            unprocessed = set(graph.keys()) - processed
            raise ValueError(f"Dependency cycle detected involving: {unprocessed}")

        layers.append(current_layer)

        # Mark as processed and update remaining deps for dependents
        for node in current_layer:
            processed.add(node)
            for dependent in dependents[node]:
                remaining_deps[dependent] -= 1

    return layers


def build_dependency_layers(
    components: List[Component],
) -> Tuple[List[List[Component]], Dict[str, Set[str]]]:
    """Build dependency layers from components.

    Args:
        components: List of discovered components.

    Returns:
        Tuple of (layers, dependency_graph) where layers is a list of
        component lists that can be processed in parallel.
    """
    graph = build_dependency_graph(components)
    layer_names = compute_topological_layers(graph)

    by_name = {c.name: c for c in components}
    layers = [
        [by_name[name] for name in layer if name in by_name] for layer in layer_names
    ]

    return layers, graph


# ---------------------------------------------------------------------------
# Subagent task and result types
# ---------------------------------------------------------------------------


@dataclass
class SubagentTask:
    """A task to be executed by a subagent."""

    component: Component
    subagent_type: str
    prompt: str
    layer_index: int
    prior_context: str = ""  # Accumulated results from prior layers

    @property
    def task_id(self) -> str:
        return f"L{self.layer_index}:{self.component.name}"


@dataclass
class SubagentResult:
    """Result from a subagent execution."""

    task: SubagentTask
    success: bool
    output: str
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    token_usage: Dict[str, int] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


# ---------------------------------------------------------------------------
# Parallel orchestrator
# ---------------------------------------------------------------------------


class ParallelOrchestrator:
    """Orchestrates parallel execution of subagents by dependency layer.

    Usage:
        orchestrator = ParallelOrchestrator(
            components=discovered_components,
            subagent_runner=my_subagent_runner_fn,
            callback_handler=my_callback_handler,
        )

        results = orchestrator.run()
    """

    def __init__(
        self,
        components: List[Component],
        subagent_runner: Callable[[SubagentTask], SubagentResult],
        callback_handler: Optional[FlashlightCallbackHandler] = None,
        max_workers: int = 10,
        agent_prompts: Optional[Dict[str, str]] = None,
    ):
        """Initialize the orchestrator.

        Args:
            components: Discovered components to analyze.
            subagent_runner: Function that executes a single subagent task.
            callback_handler: Optional callback handler for observability.
            max_workers: Maximum parallel subagents per layer.
            agent_prompts: Map of subagent type -> system prompt.
        """
        self.components = components
        self.subagent_runner = subagent_runner
        self.callback_handler = callback_handler
        self.max_workers = max_workers
        self.agent_prompts = agent_prompts or {}

        # Build dependency layers
        self.layers, self.dep_graph = build_dependency_layers(components)

        # Track results by component name
        self.results: Dict[str, SubagentResult] = {}

    def _determine_subagent_type(self, component: Component) -> str:
        """Determine which subagent type should analyze this component."""
        if component.kind == ComponentKind.LIBRARY:
            return "code-library-analyzer"
        elif component.kind in (
            ComponentKind.SERVICE,
            ComponentKind.CLI,
            ComponentKind.FRONTEND,
        ):
            return "application-analyzer"
        elif component.kind == ComponentKind.CONTRACT:
            return "code-library-analyzer"  # Contracts are analyzed like libraries
        elif component.kind == ComponentKind.INFRA:
            return "external-service-analyzer"
        else:
            return "code-library-analyzer"  # Default

    def _build_prompt(
        self,
        component: Component,
        prior_context: str,
    ) -> str:
        """Build the prompt for analyzing a component."""
        deps_info = ""
        if component.internal_dependencies:
            deps_info = f"\n\nThis component depends on: {', '.join(component.internal_dependencies)}"
            # Include analysis results of dependencies
            dep_analyses = []
            for dep_name in component.internal_dependencies:
                if dep_name in self.results:
                    dep_result = self.results[dep_name]
                    if dep_result.success:
                        dep_analyses.append(
                            f"### {dep_name}\n{dep_result.output[:2000]}..."
                            if len(dep_result.output) > 2000
                            else f"### {dep_name}\n{dep_result.output}"
                        )
            if dep_analyses:
                deps_info += "\n\n## Prior Analysis of Dependencies:\n" + "\n\n".join(
                    dep_analyses
                )

        return f"""Analyze the following component:

**Name:** {component.name}
**Type:** {component.type}
**Kind:** {component.kind.value}
**Root Path:** {component.root_path}
**Description:** {component.description or "No description available"}
{deps_info}

Please provide a comprehensive analysis including:
1. Main purpose and responsibilities
2. Key interfaces and APIs
3. Internal architecture patterns
4. Dependencies and how they're used
5. Notable implementation details

{prior_context}
"""

    def _create_tasks_for_layer(
        self,
        layer_index: int,
        layer_components: List[Component],
    ) -> List[SubagentTask]:
        """Create subagent tasks for a layer of components."""
        # Build accumulated context from all prior layers
        prior_context = ""
        if layer_index > 0:
            completed_summaries = []
            for name, result in self.results.items():
                if result.success:
                    # Include brief summary
                    summary = (
                        result.output[:500] + "..."
                        if len(result.output) > 500
                        else result.output
                    )
                    completed_summaries.append(f"- **{name}**: {summary}")
            if completed_summaries:
                prior_context = "## Previously Analyzed Components:\n" + "\n".join(
                    completed_summaries
                )

        tasks = []
        for comp in layer_components:
            subagent_type = self._determine_subagent_type(comp)
            prompt = self._build_prompt(comp, prior_context)

            task = SubagentTask(
                component=comp,
                subagent_type=subagent_type,
                prompt=prompt,
                layer_index=layer_index,
                prior_context=prior_context,
            )
            tasks.append(task)

        return tasks

    def _log_layer_start(self, layer_index: int, tasks: List[SubagentTask]) -> None:
        """Log the start of a layer execution."""
        if self.callback_handler:
            self.callback_handler._log_to_jsonl(
                {
                    "event": "layer_start",
                    "timestamp": datetime.now().isoformat(),
                    "layer_index": layer_index,
                    "total_layers": len(self.layers),
                    "component_count": len(tasks),
                    "components": [t.component.name for t in tasks],
                }
            )

        logger.info(
            "=" * 60 + "\n"
            f"LAYER {layer_index}/{len(self.layers) - 1}: "
            f"Dispatching {len(tasks)} subagents in parallel\n"
            f"Components: {[t.component.name for t in tasks]}\n" + "=" * 60
        )

    def _log_layer_complete(
        self,
        layer_index: int,
        results: List[SubagentResult],
        duration: float,
    ) -> None:
        """Log the completion of a layer."""
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        if self.callback_handler:
            self.callback_handler._log_to_jsonl(
                {
                    "event": "layer_complete",
                    "timestamp": datetime.now().isoformat(),
                    "layer_index": layer_index,
                    "successful": successful,
                    "failed": failed,
                    "duration_seconds": duration,
                    "results": [
                        {
                            "component": r.task.component.name,
                            "success": r.success,
                            "duration": r.duration_seconds,
                            "error": r.error,
                        }
                        for r in results
                    ],
                }
            )

        logger.info(
            f"LAYER {layer_index} COMPLETE: "
            f"{successful} succeeded, {failed} failed "
            f"({duration:.1f}s total)"
        )

    def run(self) -> Dict[str, SubagentResult]:
        """Execute all subagents layer by layer with parallel dispatch.

        Returns:
            Dict mapping component name to its SubagentResult.
        """
        total_start = datetime.now()

        logger.info(
            f"Starting parallel orchestration: "
            f"{len(self.components)} components in {len(self.layers)} layers"
        )

        if self.callback_handler:
            self.callback_handler._log_to_jsonl(
                {
                    "event": "orchestration_start",
                    "timestamp": total_start.isoformat(),
                    "total_components": len(self.components),
                    "total_layers": len(self.layers),
                    "layer_sizes": [len(layer) for layer in self.layers],
                }
            )

        for layer_index, layer_components in enumerate(self.layers):
            if not layer_components:
                continue

            # Create tasks for this layer
            tasks = self._create_tasks_for_layer(layer_index, layer_components)
            self._log_layer_start(layer_index, tasks)

            layer_start = datetime.now()
            layer_results: List[SubagentResult] = []

            # Execute all tasks in parallel
            with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(tasks))
            ) as executor:
                # Submit all tasks
                future_to_task = {
                    executor.submit(self._run_single_task, task): task for task in tasks
                }

                # Collect results as they complete
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error(f"Task {task.task_id} raised exception: {exc}")
                        result = SubagentResult(
                            task=task,
                            success=False,
                            output="",
                            error=str(exc),
                            start_time=datetime.now(),
                            end_time=datetime.now(),
                        )

                    layer_results.append(result)
                    self.results[task.component.name] = result

            layer_duration = (datetime.now() - layer_start).total_seconds()
            self._log_layer_complete(layer_index, layer_results, layer_duration)

        total_duration = (datetime.now() - total_start).total_seconds()

        if self.callback_handler:
            successful = sum(1 for r in self.results.values() if r.success)
            self.callback_handler._log_to_jsonl(
                {
                    "event": "orchestration_complete",
                    "timestamp": datetime.now().isoformat(),
                    "total_duration_seconds": total_duration,
                    "successful": successful,
                    "failed": len(self.results) - successful,
                }
            )

        logger.info(
            f"Orchestration complete: {len(self.results)} components analyzed "
            f"in {total_duration:.1f}s"
        )

        return self.results

    def _run_single_task(self, task: SubagentTask) -> SubagentResult:
        """Execute a single subagent task with callback tracking."""
        start_time = datetime.now()

        # Set subagent context for callbacks
        if self.callback_handler:
            self.callback_handler.set_subagent_context(
                task.subagent_type,
                f"L{task.layer_index}:{task.component.name}",
            )

        try:
            result = self.subagent_runner(task)
            result.start_time = start_time
            result.end_time = datetime.now()
            return result
        except Exception as exc:
            return SubagentResult(
                task=task,
                success=False,
                output="",
                error=str(exc),
                start_time=start_time,
                end_time=datetime.now(),
            )
        finally:
            if self.callback_handler:
                self.callback_handler.clear_subagent_context()


# ---------------------------------------------------------------------------
# Helper to create a subagent runner from a LangGraph
# ---------------------------------------------------------------------------


def make_subagent_runner(
    build_graph_fn: Callable,
    agent_prompts: Dict[str, str],
    model_name: Optional[str] = None,
    callback_handler: Optional[FlashlightCallbackHandler] = None,
) -> Callable[[SubagentTask], SubagentResult]:
    """Create a subagent runner function from a graph builder.

    Args:
        build_graph_fn: Function that builds a subagent graph.
        agent_prompts: Map of subagent type -> system prompt.
        model_name: Model to use for subagents.
        callback_handler: Optional callback handler.

    Returns:
        A function that takes a SubagentTask and returns a SubagentResult.
    """

    def runner(task: SubagentTask) -> SubagentResult:
        from agent.tools import ANALYSIS_TOOLS, DOCUMENTER_TOOLS

        # Get system prompt and tools for this subagent type
        system_prompt = agent_prompts.get(task.subagent_type, "")
        if not system_prompt:
            return SubagentResult(
                task=task,
                success=False,
                output="",
                error=f"Unknown subagent type: {task.subagent_type}",
            )

        tools = ANALYSIS_TOOLS
        if task.subagent_type == "architecture-documenter":
            tools = DOCUMENTER_TOOLS

        # Build and run the graph
        graph = build_graph_fn(
            system_prompt=system_prompt,
            tools=tools,
            model_name=model_name,
        )

        config = {}
        if callback_handler:
            config["callbacks"] = [callback_handler]

        try:
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content=task.prompt)],
                    "subagent_type": task.subagent_type,
                    "description": task.component.name,
                    "service_name": "",
                    "repo_path": task.component.root_path,
                },
                config=config,
            )

            # Extract final output
            final_messages = result.get("messages", [])
            output = ""
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    if isinstance(msg.content, str):
                        output = msg.content
                    elif isinstance(msg.content, list):
                        text_parts = [
                            block.get("text", "")
                            for block in msg.content
                            if isinstance(block, dict) and block.get("type") == "text"
                        ]
                        output = "\n".join(text_parts)
                    break

            return SubagentResult(
                task=task,
                success=True,
                output=output or "Analysis completed (no text output)",
            )

        except Exception as exc:
            logger.error(f"Subagent {task.task_id} failed: {exc}", exc_info=True)
            return SubagentResult(
                task=task,
                success=False,
                output="",
                error=str(exc),
            )

    return runner
