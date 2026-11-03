# Evaluation protocol: contracts during agent edits

**Status: pilot v2 completed (2026-11-02).** The results are summarized in
[`results-summary.md`](../experiments/agent-contracts-pilot/results-summary.md). This protocol tests
the hypothesis in [decision 0006](decisions/0006-requisitos-verificables.md): executable
requirements in a program help an AI agent preserve those requirements while changing code.

## Question

When an agent changes a NEXORA program, does having a requirement both in the task instructions and
as an executable contract in the source reduce violations, compared with having the same
requirement only in the instructions?

This tests the added value of the source contract. It does not compare NEXORA with another language,
and it does not test whether NEXORA proves a program correct.

## Pilot set

The pilot contains 12 small single-function maintenance tasks across three CLI domains. It uses four
task shapes:

1. Clamp results to a postcondition bound.
2. Round up at a boundary.
3. Preserve a precondition while rounding a result.
4. Respect interacting upper and lower bounds.

Each task has a fixed function, one requested change, visible natural-language requirements, hidden
acceptance cases and a rationale for each case. The definitions, [case rationales](../experiments/agent-contracts-pilot/case-rationales.md)
and runner are in [`experiments/agent-contracts-pilot/`](../experiments/agent-contracts-pilot/).
The nine tasks in
`tests/tooling_tasks.py` are useful examples of what the deterministic tools can answer, but they are
not agent-edit tasks and are not counted as pilot results.

## Paired conditions

For every task, prepare two source variants with identical behavior and identical task instructions:

- **Prompt only:** the requirement appears in the instructions; the source has no executable clause
  for it.
- **Prompt plus source:** the same requirement appears in the instructions and as a NEXORA
  `needs`, `promises`, or refined-type condition in the source.

All task requirements in the prompt must be plain English, without NEXORA clause names or code
fragments. The only semantic difference between paired inputs is the executable clauses in the
source; brace placement follows the syntax needed for each header.
The requested change, other source code, hidden tests and model instructions stay the same. Each
session is a one-shot edit with no tool feedback or repair turn. This isolates the effect of seeing an
executable requirement in the initial source; it does not measure the value of feeding diagnostics
back to an agent. After the response, the evaluator runs `nex check` and the hidden acceptance cases
with `nex run`. Each session has a fresh request and no conversation history. Randomize which
condition runs first. Do not give the model the paired version or another run's output.

Use one fixed model version and fixed sampling settings for the pilot. Run each task three times per
condition with independent seeds or fresh sessions: 72 total runs. The recorded pilot uses the local
Ollama model `gemma4:26b`, temperature 0.6, top-p 0.9, context 4096 and seeds 17, 29 and 43. Record
the model identifier, Ollama version, date, settings, prompt, response, final function and command
results. If a provider cannot expose a seed, record that and use independently created sessions.

The first exploratory run (v1) is preserved in `results-v1-excluded.jsonl` but excluded from analysis:
its prompt encoded requirements using NEXORA `needs`/`promises` syntax, so the prompt-only
condition exposed executable clause text. Version 2 replaces that with plain-English requirements
before v2 was run.

## Measures

Report paired results per task and in aggregate:

- **Primary:** whether the final change passes every hidden acceptance test and preserves each
  stated requirement on its test cases.
- **Contract retention:** whether every source contract in the prompt-plus-source condition survives
  the edit unchanged.
- **Contract adoption:** whether an agent adds any executable contract in the prompt-only condition.
- **Validity and hidden-case result:** whether `nex check` passes and all hidden outputs match.
- **Cost:** wall-clock time for the model response. This one-shot pilot has one model turn and no
  tool calls per run. This is latency, not token or monetary cost.

The fixed arithmetic cases have objective expected outputs. Preserve the complete output and code
for every run, including syntax failures and model responses that cannot be parsed.

## Decision rule and reporting

Treat this as an exploratory pilot, not a language claim. Publish all tasks, prompts, test fixtures,
responses, per-run outcomes, exclusions and deviations. Show paired task-level counts and
uncertainty; do not report only a single success percentage. A larger, independent replication is
required before claiming that contracts improve agent performance.

Do not tune the task set or the decision rule after seeing outcomes. If the pilot is inconclusive,
revise the tasks or collect more runs and label the follow-up as a new experiment. If contracts catch
violations in a future diagnostics-feedback study but do not improve final correctness or cost, report
that distinction rather than treating more diagnostics as proof of better results.

For this pilot, the prompt in both conditions explicitly said to keep the function header unchanged.
Therefore, contract retention is reported as an observed outcome but cannot independently show that
the source clauses caused retention. The four host-specific temporary directory prefixes in recorded
diagnostics are normalized to `<TEMP>` in the published JSONL; responses, diagnostic content and
outcomes are otherwise retained.

## What this does not test

The pilot does not establish formal verification, safety, general coding ability, performance, or
advantages over other languages. It tests only whether these source-level contracts help an agent
make the specified changes on this fixed set of NEXORA tasks.
