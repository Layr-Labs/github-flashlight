"""Roll up per-repo audit.json findings into a corpus-wide report.

Produces audit_report.json with per-language/per-plugin failure patterns
ranked by frequency, plus exemplar citations for each pattern.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=Path("audit_out"))
    parser.add_argument("--output", type=Path, default=Path("audit_out/audit_report.json"))
    args = parser.parse_args()

    corpus = json.loads(Path("scripts/graph_audit/corpus.json").read_text())
    lang_by_slug = {r["full_name"].replace("/", "__"): r["language"] for r in corpus}

    discovery = json.loads((args.out_root / "discovery_summary.json").read_text())

    repos = []
    for entry in discovery:
        if entry.get("status") != "ok":
            continue
        audit_path = args.out_root / entry["slug"] / "audit.json"
        if not audit_path.exists():
            continue
        repos.append((entry["slug"], json.loads(audit_path.read_text())))

    # Per-language counters
    kind_mismatch_by_lang: dict[str, Counter] = defaultdict(Counter)
    edge_discrepancy_by_lang: dict[str, Counter] = defaultdict(Counter)
    missed_by_lang: dict[str, int] = defaultdict(int)

    # Exemplars (first 3 per bucket) for each (lang, category)
    exemplars: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for slug, audit in repos:
        if audit.get("status") != "ok":
            continue
        lang = lang_by_slug.get(slug, "unknown")
        findings = audit.get("findings", {})

        for km in findings.get("kind_mismatches", []):
            key = f"{km['deterministic']} -> {km['proposed']}"
            kind_mismatch_by_lang[lang][key] += 1
            bucket = (lang, f"kind:{key}")
            if len(exemplars[bucket]) < 3:
                exemplars[bucket].append({"slug": slug, **km})

        for ed in findings.get("edge_discrepancies", []):
            category = ed.get("category", "unknown")
            edge_discrepancy_by_lang[lang][category] += 1
            bucket = (lang, f"edge:{category}")
            if len(exemplars[bucket]) < 3:
                exemplars[bucket].append({"slug": slug, **ed})

        missed_by_lang[lang] += len(findings.get("missed_components", []))

    report = {
        "repos_audited": len(repos),
        "per_language": {},
    }
    for lang in sorted(
        set(list(kind_mismatch_by_lang) + list(edge_discrepancy_by_lang) + list(missed_by_lang))
    ):
        report["per_language"][lang] = {
            "kind_mismatches": dict(kind_mismatch_by_lang[lang].most_common()),
            "edge_discrepancies_by_category": dict(edge_discrepancy_by_lang[lang].most_common()),
            "missed_component_count": missed_by_lang[lang],
            "exemplars": {
                key: samples
                for (l, key), samples in exemplars.items()
                if l == lang
            },
        }

    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote corpus report to {args.output}")
    print(f"  Repos audited: {len(repos)}")
    for lang, data in report["per_language"].items():
        plugin_gap = data["edge_discrepancies_by_category"].get("plugin_gap", 0)
        print(
            f"  {lang}: {plugin_gap} plugin_gap edge(s), "
            f"{sum(data['kind_mismatches'].values())} kind mismatch(es), "
            f"{data['missed_component_count']} missed component(s)"
        )


if __name__ == "__main__":
    main()
