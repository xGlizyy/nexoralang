"""Run the paired agent-edit pilot against a local Ollama endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tasks import TASKS, prompt, source


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_RESULTS = HERE / "results.jsonl"
SEEDS = (17, 29, 43)


def call_model(base_url: str, model: str, text: str, seed: int) -> tuple[str, float, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "think": False,
        "stream": False,
        "keep_alive": "1h",
        "options": {
            "temperature": 0.6,
            "top_p": 0.9,
            "num_ctx": 4096,
            "num_predict": 300,
            "seed": seed,
        },
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=900) as response:
        data = json.loads(response.read())
    return data.get("message", {}).get("content", ""), time.monotonic() - started, data.get("done_reason", "")


def extract_function(answer: str, name: str) -> str:
    fenced = re.search(r"```(?:nex)?\s*(.*?)```", answer, re.IGNORECASE | re.DOTALL)
    text = fenced.group(1) if fenced else answer
    start = re.search(rf"(?m)^\s*fn\s+{re.escape(name)}\s*\(", text)
    if not start:
        return ""
    brace = text.find("{", start.start())
    if brace < 0:
        return ""
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start.start():index + 1].strip()
    return ""


def run_nex(code: str, cases: list[tuple[list[int], int]]) -> dict:
    main = ["fn main() {"]
    for arguments, _ in cases:
        joined = ", ".join(str(value) for value in arguments)
        main.append(f"    print(to_text({function_name(code)}({joined})))")
    main.append("}")
    program = code.rstrip() + "\n\n" + "\n".join(main) + "\n"
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(REPO / "nexora" / "src")
    with tempfile.TemporaryDirectory(prefix="nexora-agent-pilot-") as tmp:
        path = Path(tmp) / "candidate.nex"
        path.write_text(program, encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, "-m", "nexora", "check", str(path)],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if checked.returncode != 0:
            return {"check_exit": checked.returncode, "check_output": checked.stdout + checked.stderr}
        ran = subprocess.run(
            [sys.executable, "-m", "nexora", "run", str(path)],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        return {
            "check_exit": checked.returncode,
            "run_exit": ran.returncode,
            "stdout": ran.stdout,
            "stderr": ran.stderr,
        }


def function_name(code: str) -> str:
    match = re.search(r"(?m)^\s*fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
    return match.group(1) if match else "__missing_function__"


def clause_status(code: str, clauses: list[str]) -> dict[str, bool]:
    normalized = re.sub(r"\s+", " ", code)
    return {clause: re.sub(r"\s+", " ", clause) in normalized for clause in clauses}


def valid_output(observed: dict, cases: list[tuple[list[int], int]]) -> bool:
    if observed.get("check_exit") != 0 or observed.get("run_exit") != 0:
        return False
    expected = "".join(f"{value}\n" for _, value in cases)
    return observed.get("stdout") == expected and observed.get("stderr", "") == ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:26b")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--limit", type=int, default=0, help="run only the first N scheduled sessions")
    args = parser.parse_args()

    version_request = urllib.request.Request(args.base_url.rstrip("/") + "/api/version")
    with urllib.request.urlopen(version_request, timeout=10) as response:
        ollama_version = json.loads(response.read()).get("version", "unknown")
    nexora_version = subprocess.run(
        [sys.executable, "-m", "nexora", "--version"],
        cwd=REPO,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO / "nexora" / "src")},
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    task_set_sha256 = hashlib.sha256((HERE / "tasks.py").read_bytes()).hexdigest()

    scheduled = []
    order_rng = random.Random(20261102)
    for task in TASKS:
        for seed in SEEDS:
            conditions = ["prompt_only", "prompt_plus_source"]
            order_rng.shuffle(conditions)
            scheduled.extend((task, seed, condition) for condition in conditions)
    if args.limit:
        scheduled = scheduled[:args.limit]

    args.results.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if args.results.exists():
        for line in args.results.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                existing.add((row["task_id"], row["seed"], row["condition"]))
            except (ValueError, KeyError):
                continue

    todo = [
        item
        for item in scheduled
        if (item[0]["id"], item[1], item[2]) not in existing
    ]
    done = 0
    with args.results.open("a", encoding="utf-8") as output:
        for task, seed, condition in todo:
            has_contracts = condition == "prompt_plus_source"
            original = source(task, has_contracts)
            prompt_text = prompt(task, original)
            try:
                answer, elapsed, done_reason = call_model(args.base_url, args.model, prompt_text, seed)
                candidate = extract_function(answer, task["id"].replace("-", "_"))
                if not candidate:
                    # NEXORA function names are task-specific rather than task ids.
                    candidate = extract_function(answer, function_name(original))
                observed = run_nex(candidate, task["cases"]) if candidate else {"check_exit": None, "run_exit": None, "stdout": "", "stderr": "no function found"}
                clauses = clause_status(candidate, task["clauses"]) if candidate else {c: False for c in task["clauses"]}
                row = {
                    "protocol_version": 2,
                    "task_id": task["id"],
                    "domain": task["domain"],
                    "shape": task["shape"],
                    "condition": condition,
                    "seed": seed,
                    "model": args.model,
                    "ollama_version": ollama_version,
                    "nexora_version": nexora_version,
                    "python_version": sys.version.split()[0],
                    "platform": platform.platform(),
                    "task_set_sha256": task_set_sha256,
                    "temperature": 0.6,
                    "top_p": 0.9,
                    "num_ctx": 4096,
                    "num_predict": 300,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": round(elapsed, 3),
                    "done_reason": done_reason,
                    "prompt": prompt_text,
                    "answer": answer,
                    "candidate": candidate,
                    "check_and_hidden_cases": observed,
                    "all_hidden_cases_pass": valid_output(observed, task["cases"]),
                    "clauses_retained": clauses,
                    "all_contracts_retained": all(clauses.values()) if has_contracts else None,
                    "baseline_added_any_contract": any(clauses.values()) if not has_contracts else None,
                }
            except Exception as error:  # keep a failed run in the record rather than dropping it
                row = {
                    "protocol_version": 2,
                    "task_id": task["id"],
                    "domain": task["domain"],
                    "shape": task["shape"],
                    "condition": condition,
                    "seed": seed,
                    "model": args.model,
                    "ollama_version": ollama_version,
                    "nexora_version": nexora_version,
                    "python_version": sys.version.split()[0],
                    "platform": platform.platform(),
                    "task_set_sha256": task_set_sha256,
                    "error": type(error).__name__ + ": " + str(error),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            done += 1
            status = "PASS" if row.get("all_hidden_cases_pass") else "FAIL"
            print(f"[{done}/{len(todo)}] {task['id']} {condition} seed={seed}: {status} ({row.get('elapsed_seconds', 0)}s)", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
