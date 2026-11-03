# Pilot v2 results: contracts during agent edits

**Result:** this pilot found no observed advantage for either condition. It does not establish that
contracts help or do not help agents in general.

## Design and provenance

- 12 fixed arithmetic maintenance tasks across invoicing, inventory and budgeting.
- Two paired conditions per task: requirements in plain-English instructions only, or the same
  requirements in the instructions and as executable clauses in the source.
- Three fresh one-shot responses per task and condition: 36 matched pairs, 72 total runs.
- One local model: `gemma4:26b` through Ollama 0.40.13; temperature 0.6, top-p 0.9, context
  4096, maximum 300 generated tokens; seeds 17, 29 and 43. No tool feedback or repair turn.
- NEXORA 0.15.0, Python 3.12.10, Windows 11. Runs were recorded from 2026-11-02 18:20:32 to
  18:24:59 UTC. The task definition SHA-256 recorded on every run matches `tasks.py`.
- Every response was checked with `nex check` and run against the same four hidden acceptance cases
  using `nex run`. A run passed only when static checking succeeded and all expected output matched.
- The model-response time averaged 3.206 seconds (median 2.836; range 1.296–10.563) across 72
  calls. This is response time only; it does not include study setup or evaluation commands.

The complete per-run record—including prompts, responses, final functions, checker/run output,
contract retention, model settings, seed, timestamp and response time—is in [`results.jsonl`](results.jsonl).
The fixed tasks and runner are in this directory. The exploratory v1 data is preserved in
[`results-v1-excluded.jsonl`](results-v1-excluded.jsonl), but excluded because its prompts exposed
NEXORA contract syntax in the prompt-only condition. The v2 protocol fixed that leakage before the
reported runs. Host-specific temporary directory prefixes in four diagnostics were normalized to
`<TEMP>`; diagnostic content and outcomes were kept intact.

## Outcomes

| Condition | Passed all cases | Rate (Wilson 95% interval) | Contract check |
|---|---:|---:|---|
| Prompt only | 34/36 | 94.4% (81.9–98.5%) | Added contracts: 0/36 |
| Prompt plus source clauses | 34/36 | 94.4% (81.9–98.5%) | Retained all clauses: 36/36 |

| Paired outcome across 36 matched runs | Count |
|---|---:|
| Both conditions passed | 33 |
| Both conditions failed | 1 |
| Prompt plus source passed; prompt only failed | 1 |
| Prompt only passed; prompt plus source failed | 1 |

The paired difference is 0/36 (0 percentage points); exact two-sided McNemar `p = 1.0`. The two
discordant pairs went in opposite directions, so the pilot does not indicate which condition is
better. The Wilson intervals above describe each condition separately; with only 36 pairs, the
result remains imprecise.

| Task | Prompt only | Prompt plus source | Pair outcomes (both pass / both fail / source only / prompt only) |
|---|---:|---:|---:|
| `invoice-discount-floor` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `invoice-tax-round-up` | 2/3 | 1/3 | 1 / 1 / 0 / 1 |
| `invoice-split-ceiling` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `invoice-credit-cap` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `inventory-available-stock` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `inventory-restock-gap` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `inventory-pick-cap` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `inventory-boxes-ceiling` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `budget-remaining-floor` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `budget-utilization-cap` | 2/3 | 3/3 | 2 / 0 / 1 / 0 |
| `budget-reimbursement-cap` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |
| `budget-shift-hours-cap` | 3/3 | 3/3 | 3 / 0 / 0 / 0 |

All four failed runs were rejected by static checking before hidden outputs could be evaluated:
two prompt-plus-source tax-rounding answers used undeclared local variables (`E2005`), while one
prompt-only tax answer and one prompt-only budget-utilization answer used unsupported `%` syntax
(`E1001`). The source contracts were retained in all 36 prompt-plus-source responses. The prompt-only
responses added no contracts. The prompt explicitly instructed both conditions to keep the function
header unchanged, so the 36/36 retention result is descriptive and is not independent evidence that
source contracts caused agents to preserve clauses.

## Interpretation and limits

This is a small, single-model, one-shot pilot on arithmetic edits. Both conditions had a high pass
rate, and the paired outcomes tied. The result is **no observed difference**, not evidence of
equivalence and not proof that contracts have no effect. The study does not compare NEXORA with
another language, use a diagnostics-and-repair loop, measure weakening of requirements across
versions, or cover realistic multi-file work. It is not evidence of formal verification, safety,
general coding ability or lower cost in other settings.

The next study should use a larger set of preregistered, realistic multi-file tasks, include repair
turns with NEXORA diagnostics, and replicate across independent model families. Until then, NEXORA
must not claim a general AI-performance advantage.

## Follow-up feasibility attempt (excluded)

On 2026-11-03, a multi-file diagnostics-and-repair follow-up was attempted with the available local
`gemma4:26b` runtime. The GPU runner terminated with a CUDA initialization failure; a CPU-only short
probe took 230 seconds for a five-token response and returned no usable answer. The task run was
stopped before collecting any valid follow-up responses, so it contributes **zero observations** and
is not combined with pilot v2. A suitable inference runtime is required to resume that separate study.
