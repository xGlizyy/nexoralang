"""Reference tasks for the analysis tools.

Each task is something a person or an AI agent may need to find out about a NEXORA program.
For each one this file fixes the input available, the tool that answers it and the expected
answer. `test_tooling_tasks.py` checks every answer against the real tools, so the set is a
reproducible measure of what the tools can and cannot tell: "the tools answer N of N tasks".

It measures the deterministic tools, not any AI model. Whether a model that uses these tools
writes better NEXORA than one that does not is a separate question, and it has not been
evaluated. docs/ai-tooling.md describes how such an evaluation would have to be run.
"""

INVENTORY = '''fn unit_price(total_cents: Int, units: Int) gives Int
    needs units > 0
    promises result >= 0
{
    return total_cents / units
}

fn label(cents: Int) gives Text {
    return to_text(cents) + " cents"
}

fn report(total_cents: Int, units: Int) {
    let price = unit_price(total_cents, units)
    print(label(price))
}

fn main() {
    report(1200, 3)
    report(500, 0)
}
'''

WRONG_ARGUMENT = INVENTORY.replace("print(label(price))", "print(label(2.5))")

TASKS = [
    {
        "id": "list-functions-and-types",
        "question": "Which functions does the program declare, and what are their signatures?",
        "source": INVENTORY,
        "tool": "get_context",
        "answer": lambda d: [f["signature"] for f in d["functions"]],
        "expected": [
            "fn unit_price(total_cents: Int, units: Int) gives Int",
            "fn label(cents: Int) gives Text",
            "fn report(total_cents: Int, units: Int)",
            "fn main()",
        ],
    },
    {
        "id": "type-of-a-local-variable",
        "question": "What is the type of 'price' in 'report'? It has no annotation.",
        "source": INVENTORY,
        "tool": "get_symbols",
        "arguments": {"name": "price"},
        "answer": lambda d: [(s["category"], s["function"], s["type"]) for s in d["symbols"]],
        "expected": [("variable", "report", "Int")],
    },
    {
        "id": "who-calls-a-function",
        "question": "Before changing 'unit_price': who calls it, and what does it promise?",
        "source": INVENTORY,
        "tool": "get_context",
        "answer": lambda d: next((f["called_by"], [(c["clause"], c["condition"]) for c in f["contracts"]])
                                 for f in d["functions"] if f["name"] == "unit_price"),
        "expected": (["report"], [("needs", "units > 0"), ("promises", "result >= 0")]),
    },
    {
        "id": "every-use-of-a-parameter",
        "question": "Where is the parameter 'units' of 'unit_price' used?",
        "source": INVENTORY,
        "tool": "get_symbols",
        "arguments": {"function": "unit_price", "name": "units"},
        "answer": lambda d: [(r["line"], r["column"]) for s in d["symbols"] for r in s["references"]],
        "expected": [(2, 11), (5, 26)],
    },
    {
        "id": "detect-a-wrong-argument",
        "question": "Is the program valid? If not, what is wrong and where?",
        "source": WRONG_ARGUMENT,
        "tool": "check_source",
        "answer": lambda d: [(x["code"], x["category"], x["line"], x["column"], x["label"], x["hint"])
                             for x in d["diagnostics"]],
        "expected": [("E2011", "type", 14, 17, "Expected Int, found Float",
                      "Convert the Float explicitly with to_int(...), which drops the fractional part.")],
    },
    {
        "id": "valid-versus-invalid",
        "question": "Two versions of a program differ in one line. Which one is valid?",
        "source": [INVENTORY, WRONG_ARGUMENT],
        "tool": "check_source",
        "answer": lambda documents: [d["ok"] for d in documents],
        "expected": [True, False],
    },
    {
        "id": "explain-a-diagnostic-with-the-specification",
        "question": "The check reported E2011. What does the official specification say that code means?",
        "source": None,
        "tool": "get_language_spec",
        "arguments": {"section": "113-diagnostic-codes"},
        "answer": lambda d: next(line for line in d["section"]["text"].split("\n") if line.startswith("| `E2011`")),
        "expected": "| `E2011` | Type mismatch | `type` | A type is not the one the corresponding rule requires |",
    },
    {
        "id": "locate-a-broken-precondition",
        "question": "The program passes the check. Does it break a contract when it runs, and at which call?",
        "source": INVENTORY,
        # Static analysis cannot answer this: it depends on the values. It needs an execution.
        "tool": "run_source",
        "answer": lambda r: (r["status"], r["output"], r["diagnostics"][0]["code"], r["diagnostics"][0]["line"],
                             r["diagnostics"][0]["notes"][:2]),
        "expected": ("contract_violation", "400 cents\n", "E4001", 13,
                     ["The condition at line 2 is false: needs units > 0",
                      "It was called with: total_cents = 500, units = 0"]),
    },
    {
        "id": "limits-of-static-analysis",
        "question": "Does the static analysis notice that report(500, 0) will break the contract?",
        "source": INVENTORY,
        "tool": "get_context",
        # The honest answer is no, and the tool says why instead of implying the program is safe.
        "answer": lambda d: (d["ok"], any("not that they hold" in note for note in d["notes"])),
        "expected": (True, True),
    },
]
