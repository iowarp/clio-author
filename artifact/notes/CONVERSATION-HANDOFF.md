# Conversation Handoff

This note preserves the working context from the clio-parser to clio-author rename period.
It is intentionally technical and omits API key values.

## Current Repository State Observed

- Repository path: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-author`
- Remote: `git@github.com:SIslamMun/clio-author.git`
- Branch observed: `main`
- Current package/CLI observed from capabilities:
  - CLI: `clio-author`
  - package name: `clio-author`
  - version: `0.3.0`
  - manifest name: `clio-author`
- Recent rename commits include:
  - `ed44375` - rename project clio-parser to clio-author
  - `e70ed1b` - CI rename follow-up
  - `6325f16` - README title/description update

## Important Rename Context

The project name changed from **clio-parser** to **clio-author**.

The README currently leads with:

```text
AUTHOR: Agentic Understanding for Thesis, Hypothesis, and Objective Research
```

The repository uses:

```text
clio_author/
ClioAuthorAgent
ClioAuthorSubagent
uv run clio-author ...
```

## Security Context

API keys were pasted earlier in chat for Gemini and Semantic Scholar. They must not be committed,
printed, logged, or copied into documentation.

The expected local pattern is:

```bash
cp .env.local.example .env.local
chmod 600 .env.local
```

The CLI loads `.env.local` automatically, or a custom path via `CLIO_ENV_FILE`. Real environment
variables override local env-file values.

## Semantic Scholar Rate-Limit Fix

A prior audit found that Semantic Scholar worked through `auto` but forced Semantic Scholar could
return `0 verified` due to rate limiting across separate CLI invocations.

The fix that was implemented before the rename:

- adds cross-process S2 throttling with a temp-file lock/state record;
- retries once after HTTP `429`;
- preserves no-raise expert behavior;
- documents the rate-limit behavior.

Verification at the time:

```text
ruff: passed
format: passed
mypy: passed
pytest: 409 passed, 3 skipped, 10 deselected
live forced Semantic Scholar cite: verified 1/1 for "Attention Is All You Need"
```

## Full CLI Audit Context

The earlier full audit exercised the CLI with real and hermetic paths:

- `capabilities`
- `ingest`
- `ask`
- `review`
- `write`
- `cite`
- `meta_review`
- `edit`
- `describe_figures`
- `plot`
- `write_review`
- `figure_refine`
- host adapter invocation

Important audit notes:

- Ingest of `2601.23265` produced `paper.md`, `blocks.json`, the PDF, and 12 figure images.
- `CLIO_LLM=codex` worked for text actions.
- `CLIO_SCHOLAR=auto` verified `Attention Is All You Need`.
- `CLIO_SCHOLAR=semantic` needed the cross-process rate-limit fix.
- Plot code rendered successfully through the gated `viz` helper.
- Default tests stayed hermetic.

## Removed Paper-Connector / Literature-Graph Direction

The conversation explored a Connected-Papers-style visual graph / paper connector feature. That
direction has since been removed from the current clio-author plan. Do **not** treat the graph work
below as active scope unless the project explicitly reopens it.

The explored feature would have shown:

- seed paper in the graph;
- prior works: older papers cited by the seed;
- derivative works: newer papers citing the seed;
- related works/recommendations where available;
- node color by publication year;
- node size by citation count;
- clickable paper links;
- a copyable `clio-author ingest ...` command per node.

The explored command shape was:

```bash
CLIO_GRAPH=semantic uv run --extra scholar clio-author graph \
  --seed "Attention Is All You Need" \
  --max-nodes 40 \
  --per-seed 10 \
  --out-dir clio-out/graphs/attention
```

The explored backend behavior was:

```text
CLIO_GRAPH=auto       Semantic Scholar first, OpenAlex fallback
CLIO_GRAPH=semantic   Semantic Scholar only
CLIO_GRAPH=openalex   OpenAlex only
CLIO_GRAPH=off        disabled/error path
```

Implementation lessons from the removed prototype, useful only if the idea is reopened:

- Semantic Scholar title search can return empty even when title-match works.
- Use S2 title-match for seed resolution.
- Strip any local `s2:` prefix before calling S2 edge APIs.
- S2 references and citations require endpoint-specific nested fields:
  - references: `citedPaper.*`
  - citations: `citingPaper.*`
- S2 graph runs need more conservative spacing than one-off citation checks because a graph run
  makes several requests.
- Generated HTML must embed raw JSON safely in `<script type="application/json">`; HTML-escaping it
  as `&quot;` causes a blank graph because `JSON.parse(...)` fails.

## Action Surface Note

The current observed `clio-author` capability manifest lists `kg` and does **not** list
`literature_graph`. That is expected after removing the paper connector / graph direction.

Observed actions from:

```bash
uv run clio-author capabilities
```

were:

```text
ingest, ask, review, meta_review, cite, write, edit, polish, coherence, kg,
describe_figures, plot, compose, export, write_review, figure_refine
```

If any docs still mention `literature_graph`, update them to match the current action surface.

## Removed Recent-Papers-Only Graph Idea

This was part of the removed graph/paper-connector direction:

```bash
CLIO_GRAPH=semantic uv run --extra scholar clio-author graph \
  --seed "Attention Is All You Need" \
  --direction derivative \
  --since-year 2022 \
  --max-nodes 40 \
  --per-seed 20 \
  --out-dir clio-out/graphs/attention-recent
```

Explored options:

```text
--direction all          prior + derivative + related
--direction prior        older cited papers only
--direction derivative   newer citing papers only
--direction related      recommendations/related only
--since-year 2022        drop older papers
--until-year 2026        optional upper year filter
```

## Project Title Discussion

The user did not like broad terms such as "framework" or vague "understanding" titles.

Researched nearby title styles:

- `PaperQA: Retrieval-Augmented Generative Agent for Scientific Research`
- `PaperBench: Evaluating AI's Ability to Replicate AI Research`
- `The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery`

Recommended direction after rename:

- keep **AUTHOR** as the project identity;
- avoid "framework";
- avoid listing every feature;
- use a short subtitle around authoring/research assistance rather than "parser".

Candidate title directions:

```text
AUTHOR: Agentic Scientific Authoring
AUTHOR: Agentic Research Authoring
AUTHOR: Scientific Authoring with Agentic Workflows
AUTHOR: From Scientific Papers to Research Drafts
AUTHOR: Agentic Tools for Scientific Authoring
```

The README currently uses:

```text
AUTHOR: Agentic Understanding for Thesis, Hypothesis, and Objective Research
```

If revisiting the title, prefer something shorter and less acronym-dependent.

## Useful Commands

Core checks:

```bash
uv run ruff check clio_author tests scripts
uv run ruff format --check clio_author tests scripts
uv run mypy clio_author
uv run pytest
```

Capabilities:

```bash
uv run clio-author capabilities
```

Citation check:

```bash
CLIO_SCHOLAR=auto uv run --extra scholar clio-author cite \
  --candidates-json '[{"title":"Attention Is All You Need","year":2017}]'
```

PDF ingest:

```bash
uv run --extra pdf clio-author ingest 2601.23265
```

Grounded question:

```bash
CLIO_LLM=codex uv run clio-author ask \
  --question "What is the main contribution?" \
  --blocks-file clio-out/2601.23265/blocks.json \
  --format prose
```
