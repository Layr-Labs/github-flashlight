"""Builds context for code analyzers from upstream dependencies."""

from pathlib import Path
from typing import Dict, List
import json

from code_analysis_agent.schemas.analysis import ServiceAnalysis


class ContextBuilder:
    """Builds analysis context from upstream service analyses."""

    def __init__(self, analyses_dir: Path):
        self.analyses_dir = Path(analyses_dir)
        self.analyses_cache: Dict[str, ServiceAnalysis] = {}

    def load_analysis(self, service_name: str) -> ServiceAnalysis:
        """Load a completed service analysis from disk."""
        # Check cache first
        if service_name in self.analyses_cache:
            return self.analyses_cache[service_name]

        analysis_path = self.analyses_dir / f"{service_name}.json"

        if not analysis_path.exists():
            raise FileNotFoundError(f"Analysis not found for {service_name} at {analysis_path}")

        with open(analysis_path) as f:
            data = json.load(f)

        # Reconstruct ServiceAnalysis from dict
        analysis = ServiceAnalysis.from_dict(data)

        self.analyses_cache[service_name] = analysis
        return analysis

    def build_context(self, direct_dependencies: List[str]) -> Dict[str, str]:
        """
        Build context summary from DIRECT dependencies only.

        Args:
            direct_dependencies: List of service names that are direct dependencies

        Returns:
            Dictionary mapping service name to summary suitable for inclusion
            in analyzer prompt.
        """
        context = {}

        for dep_name in direct_dependencies:
            try:
                analysis = self.load_analysis(dep_name)

                # Create concise summary for context (limit to 300 chars per section)
                arch_summary = (
                    analysis.architecture[:300] + "..."
                    if len(analysis.architecture) > 300
                    else analysis.architecture
                )

                key_components = ", ".join(analysis.key_components[:5])
                if len(analysis.key_components) > 5:
                    key_components += f" (and {len(analysis.key_components) - 5} more)"

                api_summary = (
                    analysis.api_surface[:200] + "..."
                    if len(analysis.api_surface) > 200
                    else analysis.api_surface
                )

                external_deps = ", ".join(analysis.external_dependencies[:10])
                if len(analysis.external_dependencies) > 10:
                    external_deps += f" (and {len(analysis.external_dependencies) - 10} more)"

                summary = f"""## {dep_name} (Direct Dependency)

**Architecture**: {arch_summary}

**Key Components**: {key_components}

**API Surface**: {api_summary}

**External Dependencies**: {external_deps}
""".strip()

                context[dep_name] = summary

            except FileNotFoundError:
                # Dependency not yet analyzed - skip
                print(f"Warning: Dependency {dep_name} not yet analyzed, skipping context")
                continue
            except Exception as e:
                print(f"Error loading analysis for {dep_name}: {e}")
                continue

        return context

    def format_context_for_prompt(self, context: Dict[str, str]) -> str:
        """Format context dictionary into prompt-ready text."""
        if not context:
            return "No upstream dependencies have been analyzed yet. This service has no internal dependencies."

        sections = ["# Upstream Service Analyses\n"]
        sections.append(
            "The following services are DIRECT DEPENDENCIES of the service you are analyzing. "
            "Use this context to understand how this service integrates with its dependencies:\n"
        )

        for service_name in sorted(context.keys()):
            sections.append(context[service_name])
            sections.append("\n---\n")

        return "\n".join(sections)
