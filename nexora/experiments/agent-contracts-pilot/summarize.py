"""Recompute the paired pilot summary from results.jsonl using only the standard library."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.jsonl"


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - radius, center + radius


def exact_mcnemar_p(source_only: int, prompt_only: int) -> float:
    discordant = source_only + prompt_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(source_only, prompt_only) + 1)) / (2**discordant)
    return min(1.0, 2 * tail)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 72:
        raise SystemExit(f"Expected 72 runs, found {len(rows)}")
    keys = {(r["task_id"], r["seed"], r["condition"]) for r in rows}
    if len(keys) != 72:
        raise SystemExit(f"Expected 72 unique task/seed/condition rows, found {len(keys)}")
    if any(r.get("protocol_version") != 2 for r in rows):
        raise SystemExit("Results contain a row outside protocol v2")

    print("Condition | Passed | Rate | Wilson 95% CI | Contract retention/adoption")
    for condition in ("prompt_only", "prompt_plus_source"):
        group = [r for r in rows if r["condition"] == condition]
        passed = sum(r.get("all_hidden_cases_pass") is True for r in group)
        lo, hi = wilson(passed, len(group))
        if condition == "prompt_only":
            metric = f"added contracts {sum(r.get('baseline_added_any_contract') is True for r in group)}/{len(group)}"
        else:
            metric = f"retained contracts {sum(r.get('all_contracts_retained') is True for r in group)}/{len(group)}"
        print(f"{condition} | {passed}/{len(group)} | {passed/len(group):.1%} | {lo:.1%}–{hi:.1%} | {metric}")

    paired: dict[tuple[str, int], dict[str, bool]] = defaultdict(dict)
    for row in rows:
        paired[(row["task_id"], row["seed"])][row["condition"]] = row.get("all_hidden_cases_pass") is True
    outcomes = Counter()
    for pair in paired.values():
        prompt = pair["prompt_only"]
        source = pair["prompt_plus_source"]
        outcomes["both_pass" if prompt and source else "both_fail" if not prompt and not source else "source_only" if source else "prompt_only"] += 1
    p = exact_mcnemar_p(outcomes["source_only"], outcomes["prompt_only"])
    print("Pairs | " + " | ".join(f"{key}={outcomes[key]}" for key in ("both_pass", "both_fail", "source_only", "prompt_only")))
    print(f"Exact two-sided McNemar p={p:.4f}; paired difference={(outcomes['source_only']-outcomes['prompt_only'])/len(paired):+.1%}")

    print("Task-level passes")
    for task in sorted({r["task_id"] for r in rows}):
        values = []
        for condition in ("prompt_only", "prompt_plus_source"):
            group = [r for r in rows if r["task_id"] == task and r["condition"] == condition]
            values.append(f"{condition} {sum(r.get('all_hidden_cases_pass') is True for r in group)}/3")
        print(f"{task}: " + ", ".join(values))

    print("Failed-run first diagnostics")
    for row in rows:
        if row.get("all_hidden_cases_pass"):
            continue
        output = row.get("check_and_hidden_cases", {}).get("check_output", "")
        first_line = output.splitlines()[0] if output else "run failed"
        print(f"{row['task_id']} {row['condition']} seed={row['seed']}: {first_line}")


if __name__ == "__main__":
    main()
