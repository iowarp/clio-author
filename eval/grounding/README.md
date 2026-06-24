# Grounding-integrity benchmark

The experiment behind AUTHOR's headline claim: **of everything a paper asserts, what fraction is
actually traceable to a real source end-to-end** — a number AUTHOR can compute (it holds both the
citations and the claims on one substrate) but a single-slice tool cannot.

## Run it

```bash
# bundled sample (offline, deterministic citation half):
uv run python scripts/benchmark_grounding.py

# your own cases + a JSON report:
uv run python scripts/benchmark_grounding.py --cases eval/grounding/cases.sample.json --out report.json
```

## The finding

A **citation-only** checker only sees the bibliography; a **claim-only** checker only sees the prose.
Each is blind to the other failure mode, so per paper its grounding estimate is wrong — and on some
papers it reports "false confidence" (looks ≥90% grounded on a paper that's actually <75%). AUTHOR's
unified score is the honest end-to-end figure.

## Cases format

Each case is `{name, markdown, bibtex, claim_integrity?, claims?}`:
- `markdown` + `bibtex` → the **citation integrity** half is computed deterministically by the real
  `ground` action (no model needed).
- `claim_integrity` is a ground-truth fraction for the **claim** half (lets the sample run offline).
  With `CLIO_LLM` set and a `claims` list per case instead, AUTHOR computes the claim half itself.

To run on real papers: ingest them, export each `paper.md` + `references.bib`, and list the intended
claims (e.g. from `plan`'s output) per case.
