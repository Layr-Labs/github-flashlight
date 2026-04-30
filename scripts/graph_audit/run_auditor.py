"""Run the graph-auditor subagent against each repo and diff vs deterministic graph.

For each audit_out/{slug}/ directory produced by run_discovery.py, this:
  1. Loads components.json + edges.json
  2. Feeds them into a graph-auditor LLM loop (reuses flashlight tools)
  3. Parses the auditor's JSON proposal
  4. Diffs proposed vs deterministic, categorizes each discrepancy
  5. Writes audit.json + auditor_raw.txt

Enforces a corpus-wide USD budget and halts before exceeding it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# Add repo root to sys.path so we can import agent.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.burr_app import (  # noqa: E402
    AVAILABLE_TOOLS,
    SUBAGENT_TOOL_FUNCTIONS,
    _chat_completion,
)

logger = logging.getLogger(__name__)


# Rough per-model pricing (USD per 1M tokens). Used only for budget enforcement;
# overstate slightly so we stop before the actual bill catches up.
MODEL_PRICING = {
    "anthropic/claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4.6": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Unknown model — assume Sonnet-tier to avoid underestimating
        pricing = MODEL_PRICING["anthropic/claude-sonnet-4-6"]
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def build_audit_prompt(
    components: list[dict],
    edges: list[dict],
    service_name: str,
) -> str:
    template = (
        Path(__file__).resolve().parents[2]
        / "agent/prompts/subagents/graph_auditor.txt"
    ).read_text()
    return (
        template.replace("{SERVICE_NAME}", service_name)
        .replace("{components_json}", json.dumps(components, indent=2))
        .replace("{edges_json}", json.dumps(edges, indent=2))
    )


FINALIZE_DIRECTIVE = (
    "You have reached the exploration budget. Stop calling tools. "
    "Produce your final JSON object now, based on what you've already read. "
    "A partial, honest answer is better than more exploration. "
    "Respond with the JSON object only, no preamble or code fence."
)


def run_auditor_loop(
    user_prompt: str,
    system_prompt: str,
    model: str,
    max_iterations: int = 40,
) -> tuple[str, dict[str, int]]:
    """Lightweight ReAct loop that returns (final_content, token_counts).

    Mirrors _run_subagent_loop in burr_app.py but exposes token usage so we
    can enforce the corpus-wide budget. If the model runs out of exploration
    budget, we send a finalize directive and give it one more turn with no
    tools available to produce the final JSON.
    """
    subagent_tools = [
        t for t in AVAILABLE_TOOLS if t["function"]["name"] != "spawn_subagent"
    ]

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    total_input = 0
    total_output = 0

    def run_one(tools: list | None) -> tuple[str, list]:
        nonlocal total_input, total_output
        response = _chat_completion(messages=messages, model=model, tools=tools)
        usage = response.get("usage", {})
        total_input += usage.get("prompt_tokens", 0)
        total_output += usage.get("completion_tokens", 0)
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        messages.append(msg)
        return content, tool_calls

    for iteration in range(max_iterations):
        content, tool_calls = run_one(subagent_tools)

        if not tool_calls:
            return content or "(no response)", {"input": total_input, "output": total_output}

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_id = tool_call["id"]
            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                messages.append(
                    {"role": "tool", "tool_call_id": tool_id, "content": f"Error parsing args: {e}"}
                )
                continue

            if tool_name in SUBAGENT_TOOL_FUNCTIONS:
                try:
                    result = SUBAGENT_TOOL_FUNCTIONS[tool_name](**tool_args)
                except Exception as e:
                    result = f"Error: {e}"
            else:
                result = f"Unknown tool: {tool_name}"

            messages.append({"role": "tool", "tool_call_id": tool_id, "content": result})

    messages.append({"role": "user", "content": FINALIZE_DIRECTIVE})
    content, _ = run_one(tools=None)
    return content or "(no response)", {"input": total_input, "output": total_output}


def extract_json_object(text: str) -> dict | None:
    """Find the first top-level JSON object in the auditor's response."""
    # Try fenced first
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # Fall back to first { ... } that balances
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def categorize_edge(
    source: str,
    target: str,
    evidence_type: str,
    in_deterministic: bool,
) -> str:
    """Classify a proposed vs deterministic edge discrepancy."""
    if in_deterministic:
        return "agrees"
    if evidence_type in ("http_call", "shared_db", "other"):
        return "dynamic_edge"  # Not expected from manifest — no regression
    if evidence_type in ("import", "path_dep"):
        return "plugin_gap"  # Manifest-level edge the parser should have caught
    return "ambiguous"


def diff_graphs(
    deterministic_components: list[dict],
    deterministic_edges: list[dict],
    audit: dict,
) -> dict:
    det_component_names = {c["name"] for c in deterministic_components}
    det_edges = {
        (e["source"], e["target"])
        for e in deterministic_edges
        if e.get("type", "depends_on") == "depends_on"
    }
    det_kinds = {c["name"]: c.get("kind") for c in deterministic_components}

    findings = {
        "kind_mismatches": [],
        "edge_discrepancies": [],
        "missed_components": audit.get("missed_components", []),
    }

    for cls in audit.get("classifications", []):
        name = cls.get("component_name")
        proposed = cls.get("proposed_kind")
        det = det_kinds.get(name)
        if det is None or proposed is None:
            continue
        if det != proposed:
            findings["kind_mismatches"].append(
                {
                    "component": name,
                    "deterministic": det,
                    "proposed": proposed,
                    "evidence_file": cls.get("evidence_file"),
                    "reasoning": cls.get("reasoning"),
                }
            )

    for edge in audit.get("proposed_edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source not in det_component_names and source not in {
            m.get("proposed_name") for m in findings["missed_components"]
        }:
            continue
        evidence_type = edge.get("evidence_type", "unknown")
        in_det = (source, target) in det_edges
        category = categorize_edge(source, target, evidence_type, in_det)
        if category == "agrees":
            continue
        findings["edge_discrepancies"].append(
            {
                "source": source,
                "target": target,
                "evidence_type": evidence_type,
                "evidence_file": edge.get("evidence_file"),
                "evidence_lines": edge.get("evidence_lines"),
                "evidence_snippet": edge.get("evidence_snippet"),
                "reasoning": edge.get("reasoning"),
                "category": category,
            }
        )

    return findings


def audit_repo(
    repo_dir: Path,
    service_name: str,
    model: str,
) -> tuple[dict, dict[str, int]]:
    components = json.loads((repo_dir / "components.json").read_text())
    edges = json.loads((repo_dir / "edges.json").read_text())

    if not components:
        return {"status": "empty_discovery", "components": 0}, {"input": 0, "output": 0}

    prompt = build_audit_prompt(components, edges, service_name)
    system = (
        "You are a graph auditor for a deterministic code-component discovery "
        "engine. You respond with a single JSON object, no prose."
    )

    raw, tokens = run_auditor_loop(prompt, system, model)
    (repo_dir / "auditor_raw.txt").write_text(raw)

    audit = extract_json_object(raw)
    if audit is None:
        return (
            {
                "status": "parse_failed",
                "components": len(components),
                "edges": len(edges),
                "tokens": tokens,
            },
            tokens,
        )

    findings = diff_graphs(components, edges, audit)
    return (
        {
            "status": "ok",
            "service_name": service_name,
            "components": len(components),
            "edges": len(edges),
            "tokens": tokens,
            "findings": findings,
            "raw_audit": audit,
        },
        tokens,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=Path("audit_out"))
    parser.add_argument(
        "--model",
        default=os.environ.get("AUDITOR_MODEL", "anthropic/claude-sonnet-4-6"),
    )
    parser.add_argument("--budget-usd", type=float, default=45.0)
    parser.add_argument("--limit", type=int, help="Only process first N repos")
    parser.add_argument("--only", help="Only process this slug (for dry runs)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    summary_path = args.out_root / "discovery_summary.json"
    discovery_summary = json.loads(summary_path.read_text())

    eligible = [r for r in discovery_summary if r.get("status") == "ok"]
    if args.only:
        eligible = [r for r in eligible if r["slug"] == args.only]
    if args.limit:
        eligible = eligible[: args.limit]

    total_input = 0
    total_output = 0
    audit_summaries = []

    for repo in eligible:
        slug = repo["slug"]
        repo_dir = args.out_root / slug
        print(f"\n[{slug}] auditing ({repo['component_count']} components, {repo['edge_count']} edges)")

        projected = estimate_cost(args.model, total_input, total_output)
        if projected >= args.budget_usd:
            print(f"  BUDGET EXHAUSTED (${projected:.2f} / ${args.budget_usd:.2f}) — halting")
            break

        try:
            result, tokens = audit_repo(repo_dir, slug, args.model)
        except Exception as e:
            logger.exception("Audit failed for %s", slug)
            result = {"status": "error", "error": str(e)}
            tokens = {"input": 0, "output": 0}

        total_input += tokens["input"]
        total_output += tokens["output"]
        running_cost = estimate_cost(args.model, total_input, total_output)
        print(
            f"  -> {result.get('status')} (tokens: {tokens['input']} in / "
            f"{tokens['output']} out, running ${running_cost:.2f})"
        )

        (repo_dir / "audit.json").write_text(json.dumps(result, indent=2))
        audit_summaries.append(
            {
                "slug": slug,
                "status": result.get("status"),
                "tokens": tokens,
                "cumulative_cost_usd": running_cost,
            }
        )

    (args.out_root / "audit_summary.json").write_text(
        json.dumps(
            {
                "model": args.model,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_cost_usd": estimate_cost(args.model, total_input, total_output),
                "per_repo": audit_summaries,
            },
            indent=2,
        )
    )
    print(f"\nFinal cost: ${estimate_cost(args.model, total_input, total_output):.2f}")


if __name__ == "__main__":
    main()
