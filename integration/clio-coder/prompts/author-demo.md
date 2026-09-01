---
description: Run the clio-author live demo (deterministic acts by default)
argument-hint: "[act number | 'all' | 'deterministic']"
---

Run the clio-author demo from DEMO.md in this repository. Act selection: $1
(default when empty: the deterministic, no-model acts — 1, 8, and 9).

Procedure, per act:

1. Print the exact command before running it.
2. Run it.
3. Quote the real output, then give the one-line "Say:" framing DEMO.md records for that act.

Rules:

- Prefer the declared checks where one exists: `verify(check="author-capabilities")`,
  `verify(check="author-lifecycle")`, `verify(check="test-author")`,
  `verify(check="author-grounding-benchmark")`.
- Stop and report if any command exits non-zero. Do not continue past a failure.
- Never fabricate or paraphrase output. If a result begins with `[echo]`, say that
  `CLIO_LLM` is unset rather than presenting the placeholder as a result.
- Acts 2, 6, and 7 take minutes (act 7 took ~18). Warn before starting one.
