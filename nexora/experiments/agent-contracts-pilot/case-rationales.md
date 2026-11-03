# Hidden-case rationales

Each row maps, in order, to the four input/output pairs in `tasks.py`. These cases are evaluator-only
and are not included in model prompts.

| Task | Case rationales, in order |
|---|---|
| `invoice-discount-floor` | Ordinary discount; discount exceeds subtotal; zero-value invoice; discount exactly equals subtotal. |
| `invoice-tax-round-up` | Exact whole-cent tax; fractional cent rounds upward; tiny fractional tax still costs one cent; exact higher-rate tax. |
| `invoice-split-ceiling` | Non-divisible total rounds upward; exact division; total smaller than group size; zero total. |
| `invoice-credit-cap` | Credit below amount; credit exceeds amount; credit exactly equals amount; both values zero. |
| `inventory-available-stock` | Normal reservations; reservations exceed stock; empty stock; all stock reserved. |
| `inventory-restock-gap` | Stock below minimum; at minimum; above minimum; zero minimum and stock. |
| `inventory-pick-cap` | Request below stock; stock below request; zero request; request equals stock. |
| `inventory-boxes-ceiling` | Partially filled final box; exact number of boxes; fewer items than one box; zero items. |
| `budget-remaining-floor` | Spending below allocation; spending exceeds allocation; zero allocation and spending; fully spent allocation. |
| `budget-utilization-cap` | Fraction rounds upward; exact quarter; spending far above limit; zero spending. |
| `budget-reimbursement-cap` | Claim below limit; claim above limit; zero claim; claim equals limit. |
| `budget-shift-hours-cap` | Ordinary remaining hours; hours exceed shift limit; zero schedule; fully worked shift. |
