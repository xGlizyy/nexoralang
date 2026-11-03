"""Fixed paired tasks for the local contracts pilot."""


TASKS = [
    {
        "id": "invoice-discount-floor",
        "domain": "invoicing",
        "shape": "postcondition",
        "signature": "fn invoice_total(subtotal: Int, discount: Int) gives Int",
        "clauses": ["needs subtotal >= 0", "needs discount >= 0", "promises result >= 0", "promises result <= subtotal"],
        "requirements_text": "Subtotal and discount are non-negative. The final invoice total must be at least zero and no more than the subtotal.",
        "request": "Fix discounts larger than the subtotal: the final invoice total must stop at zero, never become negative.",
        "body": "    return subtotal - discount",
        "cases": [([1200, 200], 1000), ([100, 150], 0), ([0, 0], 0), ([75, 75], 0)],
    },
    {
        "id": "invoice-tax-round-up",
        "domain": "invoicing",
        "shape": "boundary-rounding",
        "signature": "fn total_with_tax(subtotal: Int, tax_percent: Int) gives Int",
        "clauses": ["needs subtotal >= 0", "needs tax_percent >= 0 and tax_percent <= 100", "promises result >= subtotal"],
        "requirements_text": "Subtotal is non-negative. The tax rate is between zero and one hundred percent. The total cannot be below the subtotal, and fractional cents of tax round up.",
        "request": "Round tax up to the next whole cent whenever the exact tax has a fractional cent; otherwise keep the exact total.",
        "body": "    return subtotal + subtotal * tax_percent / 100",
        "cases": [([100, 7], 107), ([101, 8], 110), ([1, 5], 2), ([200, 10], 220)],
    },
    {
        "id": "invoice-split-ceiling",
        "domain": "invoicing",
        "shape": "precondition-and-rounding",
        "signature": "fn amount_per_person(total: Int, people: Int) gives Int",
        "clauses": ["needs total >= 0", "needs people > 0", "promises result * people >= total"],
        "requirements_text": "The total is non-negative and the number of people is positive. Return the smallest whole-cent amount per person whose combined payments cover the total; never round down.",
        "request": "Return the smallest whole-cent amount per person whose combined payments cover the total; never round down.",
        "body": "    return total / people",
        "cases": [([100, 3], 34), ([99, 3], 33), ([1, 9], 1), ([0, 4], 0)],
    },
    {
        "id": "invoice-credit-cap",
        "domain": "invoicing",
        "shape": "interacting-bounds",
        "signature": "fn amount_after_credit(amount: Int, credit: Int) gives Int",
        "clauses": ["needs amount >= 0", "needs credit >= 0", "promises result >= 0", "promises result <= amount"],
        "requirements_text": "Amount and credit are non-negative. Apply the credit, capped at the amount, so the result stays between zero and the original amount.",
        "request": "Apply the credit, but cap it at the invoice amount so the remaining amount is never negative.",
        "body": "    return amount - credit",
        "cases": [([800, 250], 550), ([100, 200], 0), ([10, 10], 0), ([0, 0], 0)],
    },
    {
        "id": "inventory-available-stock",
        "domain": "inventory",
        "shape": "postcondition",
        "signature": "fn available_stock(on_hand: Int, reserved: Int) gives Int",
        "clauses": ["needs on_hand >= 0", "needs reserved >= 0", "promises result >= 0", "promises result <= on_hand"],
        "requirements_text": "Stock on hand and reserved stock are non-negative. Available stock is never negative and never exceeds stock on hand.",
        "request": "Calculate unreserved stock; if reservations exceed stock, report zero rather than a negative quantity.",
        "body": "    return on_hand - reserved",
        "cases": [([12, 5], 7), ([4, 9], 0), ([0, 0], 0), ([7, 7], 0)],
    },
    {
        "id": "inventory-restock-gap",
        "domain": "inventory",
        "shape": "interacting-bounds",
        "signature": "fn restock_quantity(on_hand: Int, minimum: Int) gives Int",
        "clauses": ["needs on_hand >= 0", "needs minimum >= 0", "promises result >= 0"],
        "requirements_text": "Current stock and the minimum are non-negative. Return only the quantity needed to reach the minimum, or zero when current stock already meets it.",
        "request": "Return the quantity needed to reach the minimum stock, or zero when stock is already at or above the minimum.",
        "body": "    return minimum - on_hand",
        "cases": [([3, 10], 7), ([10, 10], 0), ([14, 10], 0), ([0, 0], 0)],
    },
    {
        "id": "inventory-pick-cap",
        "domain": "inventory",
        "shape": "postcondition",
        "signature": "fn fulfilled_pick(requested: Int, on_hand: Int) gives Int",
        "clauses": ["needs requested >= 0", "needs on_hand >= 0", "promises result >= 0", "promises result <= requested", "promises result <= on_hand"],
        "requirements_text": "The request and stock on hand are non-negative. Fulfill no more than either quantity, and never return a negative quantity.",
        "request": "Fulfill at most the requested quantity and at most what is on hand; never return a negative quantity.",
        "body": "    return requested",
        "cases": [([5, 8], 5), ([9, 4], 4), ([0, 5], 0), ([7, 7], 7)],
    },
    {
        "id": "inventory-boxes-ceiling",
        "domain": "inventory",
        "shape": "precondition-and-rounding",
        "signature": "fn boxes_required(items: Int, per_box: Int) gives Int",
        "clauses": ["needs items >= 0", "needs per_box > 0", "promises result >= 0", "promises result * per_box >= items"],
        "requirements_text": "The item count is non-negative and the capacity of a box is positive. Return the minimum number of boxes; a partly filled final box still counts.",
        "request": "Return the minimum number of boxes needed; a partially filled last box still counts as one.",
        "body": "    return items / per_box",
        "cases": [([10, 4], 3), ([8, 4], 2), ([1, 9], 1), ([0, 5], 0)],
    },
    {
        "id": "budget-remaining-floor",
        "domain": "budgeting",
        "shape": "postcondition",
        "signature": "fn remaining_budget(allocated: Int, spent: Int) gives Int",
        "clauses": ["needs allocated >= 0", "needs spent >= 0", "promises result >= 0", "promises result <= allocated"],
        "requirements_text": "Allocation and spending are non-negative. Remaining budget is never negative and never exceeds the original allocation.",
        "request": "Report the unspent budget, clamped to zero when spending exceeds the allocation.",
        "body": "    return allocated - spent",
        "cases": [([10000, 4500], 5500), ([100, 150], 0), ([0, 0], 0), ([70, 70], 0)],
    },
    {
        "id": "budget-utilization-cap",
        "domain": "budgeting",
        "shape": "boundary-rounding",
        "signature": "fn utilization_percent(spent: Int, limit: Int) gives Int",
        "clauses": ["needs spent >= 0", "needs limit > 0", "promises result >= 0 and result <= 100"],
        "requirements_text": "Spending is non-negative and the limit is positive. Report utilization as a whole percentage rounded up, capped at one hundred percent.",
        "request": "Report utilization as a whole percentage rounded up, but cap the result at 100 when spending exceeds the limit.",
        "body": "    return spent * 100 / limit",
        "cases": [([1, 3], 34), ([1, 4], 25), ([100, 10], 100), ([0, 10], 0)],
    },
    {
        "id": "budget-reimbursement-cap",
        "domain": "budgeting",
        "shape": "interacting-bounds",
        "signature": "fn approved_reimbursement(claim: Int, policy_limit: Int) gives Int",
        "clauses": ["needs claim >= 0", "needs policy_limit >= 0", "promises result >= 0", "promises result <= claim", "promises result <= policy_limit"],
        "requirements_text": "The claim and policy limit are non-negative. Approved reimbursement must be no more than either the claim or the policy limit.",
        "request": "Approve the claim only up to the policy limit; the result must never exceed either the claim or the limit.",
        "body": "    return claim",
        "cases": [([80, 100], 80), ([120, 100], 100), ([0, 100], 0), ([30, 30], 30)],
    },
    {
        "id": "budget-shift-hours-cap",
        "domain": "budgeting",
        "shape": "postcondition",
        "signature": "fn remaining_shift_hours(shift_limit: Int, worked: Int) gives Int",
        "clauses": ["needs shift_limit >= 0", "needs worked >= 0", "promises result >= 0", "promises result <= shift_limit"],
        "requirements_text": "The shift limit and logged hours are non-negative. Remaining hours never go below zero or above the shift limit.",
        "request": "Calculate remaining shift hours and clamp the answer to zero if the logged hours exceed the shift limit.",
        "body": "    return shift_limit - worked",
        "cases": [([8, 3], 5), ([8, 10], 0), ([0, 0], 0), ([5, 5], 0)],
    },
]


def source(task, with_contracts):
    if with_contracts:
        lines = [task["signature"]]
        lines.extend("    " + clause for clause in task["clauses"])
        lines.append("{")
    else:
        lines = [task["signature"] + " {"]
    lines.extend([task["body"], "}"])
    return "\n".join(lines)


def prompt(task, program):
    return f"""You are editing a NEXORA 0.15 function. Make the requested behavior change.

Request: {task['request']}

Requirements: {task['requirements_text']}

Use NEXORA statement syntax: `if condition {{ ... }} else {{ ... }}`; return from the function with `return`. There is no `min`, `max`, `%`, or `if` expression. All inputs in the acceptance cases are non-negative integers.

Only change the function body. Keep the signature and header unchanged. Return only the complete updated function, with no Markdown fences or explanation. Do not add main().

Current source:
```nex
{program}
```"""
