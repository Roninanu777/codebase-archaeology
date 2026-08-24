# Evals

Hand-dug eval cases live here. Each `dig-*.md` records questions where the true answer was
established by reading actual history, with every claim cited to a SHA. Milestone 1 turns these
into the JSONL case file consumed by the harness (`pytest` + report script, per DESIGN.md §8).

Conventions:
- Every claim carries a short SHA; verify against `.scratch/react`.
- Cases note which Path they exercise (A = symbol-anchored, B = retrieval) and expected
  behavior, including expected abstention.
