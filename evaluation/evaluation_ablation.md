# PawPal AI — Ablation Experiments

### 1. Retrieval ablation (does RAG change behavior?)

| retrieval k | records extracted |
| ----------- | ----------------- |
| 0 | 0 |
| 2 | 4 |
| 4 | 4 |

With `k=0` the model receives no retrieved passages and extracts nothing; with `k=4` it extracts the full set. Retrieval demonstrably drives output.

### 2. Grounding / specialization (does it stop fabrication?)

Document states an *administered* date but **no due date**.

| system | invented a due date? |
| ------ | -------------------- |
| Baseline extractor (guesses +1 year) | YES — raw output = ['2026-06-10'] |
| Specialized grounded pipeline | no — due_date = null, flagged missing |

Measured: baseline fabricates **1** due date(s); the grounded pipeline fabricates **0**. The evidence check + null-when-absent prompt is what removes the invented value.
