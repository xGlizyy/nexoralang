"""Multi-file, diagnostics-feedback follow-up for the local contract pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SEEDS = (17, 29, 43)

# Each task deliberately spans a reusable policy module and a consuming workflow.
TASKS = [
    {
        "id": "checkout-discount",
        "request": "Fix the checkout so a discount larger than the item price cannot make the final amount negative. The checkout should use the shared pricing policy, and the policy must keep its public function's documented behavior.",
        "requirements": "Price and discount are non-negative. A discounted unit price is between zero and the original price. A checkout total is the discounted unit price times quantity; quantity is positive.",
        "files": {
            "pricing.nex": 'pub fn discounted_price(price: Int, discount: Int) gives Int\n    needs price >= 0\n    needs discount >= 0\n    promises result >= 0\n    promises result <= price\n{\n    return price - discount\n}\n',
            "checkout.nex": 'import "pricing.nex"\n\nfn checkout_total(price: Int, discount: Int, quantity: Int) gives Int\n    needs quantity > 0\n    promises result >= 0\n{\n    return pricing.discounted_price(price, discount) * quantity\n}\n\nfn main() {\n    print(checkout_total(100, 20, 3))\n    print(checkout_total(50, 80, 2))\n}\n',
        },
        "contracts": {"pricing.nex": ["needs price >= 0", "needs discount >= 0", "promises result >= 0", "promises result <= price"], "checkout.nex": ["needs quantity > 0", "promises result >= 0"]},
        "expected": "240\n0\n",
    },
    {
        "id": "inventory-restock",
        "request": "Fix the restock workflow so it orders only the shortfall and never requests a negative quantity when current stock exceeds the target. Keep the policy reusable by the warehouse workflow.",
        "requirements": "Current stock and target stock are non-negative. The restock amount is the target minus current stock when the target is higher, otherwise zero. The warehouse order forwards that amount unchanged.",
        "files": {
            "stock.nex": 'pub fn restock_amount(current: Int, target: Int) gives Int\n    needs current >= 0\n    needs target >= 0\n    promises result >= 0\n{\n    return target - current\n}\n',
            "warehouse.nex": 'import "stock.nex"\n\nfn warehouse_order(current: Int, target: Int) gives Int\n    needs current >= 0\n    needs target >= 0\n    promises result >= 0\n{\n    return stock.restock_amount(current, target)\n}\n\nfn main() {\n    print(warehouse_order(3, 10))\n    print(warehouse_order(14, 10))\n}\n',
        },
        "contracts": {"stock.nex": ["needs current >= 0", "needs target >= 0", "promises result >= 0"], "warehouse.nex": ["needs current >= 0", "needs target >= 0", "promises result >= 0"]},
        "expected": "7\n0\n",
    },
    {
        "id": "budget-reimbursement",
        "request": "Fix reimbursement approval so the approved amount never exceeds the claim or the policy limit. Keep the shared policy and the expense workflow consistent.",
        "requirements": "Claim and policy limit are non-negative. Approval is the smaller of the claim and policy limit. The expense workflow returns exactly the amount approved by the shared policy.",
        "files": {
            "policy.nex": 'pub fn approved_amount(claim: Int, limit: Int) gives Int\n    needs claim >= 0\n    needs limit >= 0\n    promises result >= 0\n    promises result <= claim\n    promises result <= limit\n{\n    return claim\n}\n',
            "expenses.nex": 'import "policy.nex"\n\nfn reimbursement(claim: Int, limit: Int) gives Int\n    needs claim >= 0\n    needs limit >= 0\n    promises result >= 0\n{\n    return policy.approved_amount(claim, limit)\n}\n\nfn main() {\n    print(reimbursement(80, 100))\n    print(reimbursement(120, 100))\n}\n',
        },
        "contracts": {"policy.nex": ["needs claim >= 0", "needs limit >= 0", "promises result >= 0", "promises result <= claim", "promises result <= limit"], "expenses.nex": ["needs claim >= 0", "needs limit >= 0", "promises result >= 0"]},
        "expected": "80\n100\n",
    },
]


def request_model(base_url: str, model: str, messages: list[dict], seed: int) -> tuple[str, float]:
    payload = {"model": model, "messages": messages, "stream": False, "think": False,
               "keep_alive": "1h", "options": {"temperature": 0.6, "top_p": 0.9,
               "num_ctx": 4096, "num_predict": 1800, "seed": seed}}
    req = urllib.request.Request(base_url.rstrip("/") + "/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=900) as response:
        answer = json.loads(response.read()).get("message", {}).get("content", "")
    return answer, time.monotonic() - started


def extract_files(answer: str, allowed: set[str]) -> dict[str, str]:
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        return {}
    try:
        value = json.loads(match.group())
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict) or set(value) != allowed or not all(isinstance(v, str) for v in value.values()):
        return {}
    return value


def run_project(files: dict[str, str], entry: str) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "nexora" / "src")
    with tempfile.TemporaryDirectory(prefix="nexora-repair-study-") as temp:
        root = Path(temp)
        for name, contents in files.items():
            (root / name).write_text(contents, encoding="utf-8")
        path = root / entry
        check = subprocess.run([sys.executable, "-m", "nexora", "check", str(path)], cwd=REPO, env=env, text=True, capture_output=True, timeout=30)
        if check.returncode:
            return {"check_exit": check.returncode, "diagnostic": check.stdout + check.stderr, "run_exit": None, "stdout": "", "stderr": ""}
        run = subprocess.run([sys.executable, "-m", "nexora", "run", str(path)], cwd=REPO, env=env, text=True, capture_output=True, timeout=30)
        return {"check_exit": check.returncode, "diagnostic": run.stderr, "run_exit": run.returncode, "stdout": run.stdout, "stderr": run.stderr}


def clauses_preserved(files: dict[str, str], task: dict) -> bool:
    return all(clause in files[name] for name, clauses in task["contracts"].items() for clause in clauses)


def evaluate(files: dict[str, str], task: dict) -> tuple[dict, bool]:
    entry = next(name for name in files if name in ("checkout.nex", "warehouse.nex", "expenses.nex"))
    observed = run_project(files, entry)
    passed = observed["check_exit"] == 0 and observed["run_exit"] == 0 and observed["stdout"] == task["expected"] and observed["stderr"] == ""
    return observed, passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:26b")
    parser.add_argument("--results", type=Path, default=HERE / "repair-replication.jsonl")
    args = parser.parse_args()
    with urllib.request.urlopen(args.base_url.rstrip("/") + "/api/version", timeout=10) as response:
        ollama_version = json.loads(response.read()).get("version", "unknown")
    nex_version = subprocess.run([sys.executable, "-m", "nexora", "--version"], cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO / "nexora" / "src")}, capture_output=True, text=True, check=True).stdout.strip()
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.results.parent.mkdir(parents=True, exist_ok=True)
    done_keys = set()
    if args.results.exists():
        for line in args.results.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if not row.get("error"):
                    done_keys.add((row["task_id"], row["seed"], row["condition"]))
            except (ValueError, KeyError):
                pass
    # Fixed interleaving avoids running all of one condition together.
    order = [(task, seed, condition) for task in TASKS for seed in SEEDS for condition in ("prompt_only", "prompt_plus_source")]
    with args.results.open("a", encoding="utf-8") as out:
        for task, seed, condition in order:
            key = (task["id"], seed, condition)
            if key in done_keys:
                continue
            initial = dict(task["files"])
            if condition == "prompt_only":
                for filename, clauses in task["contracts"].items():
                    initial[filename] = "\n".join(line for line in initial[filename].splitlines() if not any(line.strip().startswith(c) for c in clauses)) + "\n"
            task_prompt = ("You are editing a small NEXORA project. Return a JSON object whose keys are exactly the listed file names and whose values are each complete updated file as strings. Do not use Markdown.\n\n"
                f"Request: {task['request']}\nRequirements: {task['requirements']}\n"
                "Change both listed files as needed. Preserve public APIs, imports, and unrelated behavior. NEXORA supports if/else blocks, return, and integer arithmetic; it has no min, max, or % operator.\n"
                + "Files:\n" + "\n".join(f"--- {name} ---\n{contents}" for name, contents in initial.items()))
            messages = [{"role": "user", "content": task_prompt}]
            elapsed = []
            try:
                answer1, sec = request_model(args.base_url, args.model, messages, seed); elapsed.append(sec)
                candidate = extract_files(answer1, set(initial))
                attempt1, pass1 = evaluate(candidate, task) if candidate else ({"diagnostic": "Response was not valid JSON with all required files"}, False)
                answer2 = ""
                final_files = candidate
                attempt2, passed = attempt1, pass1
                if not pass1:
                    repair_prompt = ("Your previous project edit did not pass. Use the diagnostics and actual acceptance-case outputs below to repair it. Return the same JSON object format with every complete file.\n\n"
                        f"Diagnostics and evaluator output:\n{json.dumps(attempt1, ensure_ascii=False)}\nExpected stdout: {task['expected']!r}\n"
                        f"Your files:\n{json.dumps(candidate, ensure_ascii=False)}")
                    messages.append({"role": "assistant", "content": answer1}); messages.append({"role": "user", "content": repair_prompt})
                    answer2, sec = request_model(args.base_url, args.model, messages, seed); elapsed.append(sec)
                    repaired = extract_files(answer2, set(initial))
                    if repaired:
                        final_files = repaired; attempt2, passed = evaluate(repaired, task)
                    else:
                        attempt2, passed = {"diagnostic": "Repair response was not valid JSON with all required files"}, False
                row = {"protocol_version": 3, "task_id": task["id"], "seed": seed, "condition": condition,
                    "model": args.model, "ollama_version": ollama_version, "nexora_version": nex_version,
                    "python_version": sys.version.split()[0], "platform": platform.platform(), "task_set_sha256": sha,
                    "temperature": 0.6, "top_p": 0.9, "num_ctx": 4096, "max_turns": 2,
                    "created_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": elapsed,
                    "prompt": task_prompt, "initial_answer": answer1, "first_attempt": attempt1,
                    "first_attempt_passed": pass1, "repair_answer": answer2, "final_files": final_files,
                    "final_attempt": attempt2, "final_passed": passed,
                    "clauses_retained": clauses_preserved(final_files, task) if condition == "prompt_plus_source" else None}
            except Exception as exc:
                row = {"protocol_version": 3, "task_id": task["id"], "seed": seed, "condition": condition,
                    "model": args.model, "ollama_version": ollama_version, "nexora_version": nex_version,
                    "task_set_sha256": sha, "error": type(exc).__name__ + ": " + str(exc)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
            print(f"{task['id']} {condition} seed={seed}: first={row.get('first_attempt_passed')} final={row.get('final_passed')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
