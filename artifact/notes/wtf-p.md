# WTF-P (Write The F***ing Paper) — Deep Study Notes

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-parser/artifact/repos/wtf-p`
Source: `github.com/akougkas/wtf-p`.
Version studied: **v0.5.0**. This repo is the source of the `/wtfp:*` skills present in this environment.

---

## 1. Purpose, Tech Stack, Install/Run, License

**Purpose.** WTF-P installs structured *academic writing* commands into an AI coding assistant (Claude Code, Gemini CLI, OpenCode), turning it into a spec-driven paper-writing system. It is NOT "write me a paper": every section is planned before written, verified after, and grounded in the user's actual BibTeX. Covers the "4 P's": **P**aper, **P**roposal, **P**resentation, **P**oster (`README.md:7-9`, `ROADMAP.md:70-75`).

**Tech stack.** Pure **Node.js** CLI (`"engines": {"node": ">=16.7.0"}`, `package.json:59`). No runtime npm deps for the installer — uses only Node builtins (`fs`, `path`, `os`, `https`, `child_process`). One optional peer dep: `@marp-team/marp-cli` (slides/posters). The "intelligence" is *not* code — it lives in **Markdown prompt files** (commands, agents, workflows) that the host LLM runtime executes. The Node code is just an installer + a citation API toolkit + a WCN compressor.

**Install / run.** Published to npm as `wtf-p`. Entry points (`package.json:5-9`):
- `bin/install.js` → `wtfp` / `wtf-p`
- `bin/uninstall.js` → `wtf-p-uninstall`

```bash
npx wtf-p                  # interactive install (Claude Code default)
npx wtf-p --global         # ~/.claude (recommended)
npx wtf-p --local          # ./.claude
npx wtf-p --gemini         # ~/.config/gemini
npx wtf-p --opencode       # ~/.opencode
npx wtf-p --all            # all three runtimes
npx wtf-p status|doctor|update|uninstall
```
Then in the assistant: `/wtfp:new-paper` → `/wtfp:create-outline` → `/wtfp:plan-section 1` → `/wtfp:write-section`.

**License.** **MIT** (`LICENSE:1-3`).

---

## 2. Full Repo Structure

```
wtf-p/
├── package.json, README.md, ROADMAP.md, CHANGELOG.md, CONTRIBUTING.md, LICENSE
├── bin/
│   ├── install.js, uninstall.js          # CLI entry points (arg parse + banner)
│   ├── commands/                          # install-logic, status, doctor, update, list
│   └── lib/                               # ★ Node libs installed into <cfg>/bin/
│       ├── manifest.js                    # per-runtime install map (the adapter table)
│       ├── utils.js, checkpoint.js, context-primer.js, wcn-compiler.js
│       ├── citation-fetcher.js, citation-ranker.js, semantic-scholar.js,
│       │   scholar-lookup.js, bib-format.js, bib-index.js, analyze-impact.js
├── core/write-the-f-paper/               # ★ VENDOR-AGNOSTIC SHARED CORE
│   ├── workflows/                        # 17 workflows × {.md verbose, .wcn.md compressed}
│   ├── references/                       # 17 canonical docs (orchestrator-pattern, agent-model-matrix, ...)
│   ├── templates/                        # PLAN/STATE/PROJECT/SUMMARY/config.json/base-prefs.yaml/...
│   │   ├── project-context/  posters/  slides/
│   └── venues/                           # acm-cs, ieee-cs, arxiv-ml, nature, thesis-chapter (.yaml)
├── vendors/                              # ★ PER-RUNTIME ADAPTERS
│   ├── claude/
│   │   ├── commands/wtfp/   (36 .md + YAML frontmatter)
│   │   ├── agents/wtfp/     (11 .md + YAML frontmatter)
│   │   ├── skills/wtfp/     (marp, echarts — SKILL.md)
│   │   ├── mcp/research-server/  (MCP stdio server, ArXiv + Semantic Scholar)
│   │   └── .claude-plugin/plugin.json    (marketplace manifest)
│   ├── gemini/  commands/wtfp/ (36 .toml)  + agents/wtfp/ (11 .md)
│   └── opencode/ commands/wtfp/ (36 .md)   + agents/wtfp/ (11 .md)
├── tools/wcn/                            # WCN compression: cli.js, converter.js, SPEC.md, swap-workflows.sh
├── scripts/  (release.js, preflight.js)
├── test/     (sanity, paths, linter, wcn-integrity, dry-run, feature, installer)
└── tests/e2e/  (real worked example: structured-prompting paper)
```

Key insight: `core/` is shared and runtime-neutral; `vendors/<runtime>/` are thin per-runtime wrappers. `bin/lib/` ships into the install dir as `bin/` so agents can shell out to citation tools.

---

## 3. Architecture: Thin Orchestrator → Specialized Agents → Quality Loop

Canonical doc: `core/write-the-f-paper/references/orchestrator-pattern.md`. README summary at `README.md:222-239`.

**Layers:**
1. **Specification first** — `/wtfp:new-paper` interviews the user → `PROJECT.md`.
2. **Hierarchical planning** — Paper Vision → Section Outline → Section Plan → Paragraph Execution; each level is its own document.
3. **Isolated execution** — each section written in a *fresh agent context* containing only paper vision, that section's plan, relevant citations, prior sections. "No context pollution."
4. **Quality loops** — pre-write plan validation (7 dimensions, ≤3 revisions) + post-write goal-backward verification.

**Thin orchestrator pattern** (`orchestrator-pattern.md:1-11`): commands are *lightweight routers*. They (1) validate env, (2) load context, (3) resolve model profile, (4) `Task()`-spawn an agent, (5) parse the agent's structured return header, (6) optionally spawn a quality agent, (7) present "Next Up". Heavy work lives in agents so they get a clean context window. Spawning convention (`orchestrator-pattern.md:93-100`):

```
Task(
  prompt="First, read ~/.claude/agents/wtfp/{agent}.md for your role.\n\n" + filled_prompt,
  subagent_type="general-purpose",
  model="{resolved_model}",
  description="[Action] Section {X}"
)
```
Note: orchestrators **inline context content into the prompt** rather than passing file refs (agents can't read what the orchestrator could) — explicitly called out as an anti-pattern to avoid (`orchestrator-pattern.md:148-167`).

**Structured returns** drive deterministic routing — every agent ends with one of:
`## {ACTION} COMPLETE` / `## CHECKPOINT REACHED` / `## {ACTION} BLOCKED` (also VERIFIED / GAPS FOUND / HUMAN NEEDED for verifiers). See `orchestrator-pattern.md:109-116`.

---

## 4. The 11 Specialized Agents

Defined in `vendors/<runtime>/agents/wtfp/*.md`. **Claude versions** (`vendors/claude/agents/wtfp/`) are the canonical packaging. Each is a **Markdown file with YAML frontmatter** (`name`, `description`, `allowed-tools`) followed by an XML-tagged body (`<role>`, `<context_fidelity>`, `<execution_flow>`, `<structured_returns>`, `<success_criteria>`).

| # | Agent (frontmatter name) | Role | File |
|---|---|---|---|
| 1 | `wtfp-outliner` | PROJECT.md → outline.md, argument-map.md, narrative-arc.md, ROADMAP.md (section breakdown, word budgets, wave assignments, research flags) | `agents/wtfp/outliner.md` |
| 2 | `wtfp-section-planner` | Creates executable PLAN.md (argument decomposition, word budgets, citation mapping, checkpoint placement); honors CONTEXT.md locked decisions | `agents/wtfp/section-planner.md` |
| 3 | `wtfp-plan-checker` | Pre-write validation of plans against **7 quality dimensions**; returns PASSED / ISSUES FOUND (blocker/warning/info) | `agents/wtfp/plan-checker.md` |
| 4 | `wtfp-section-writer` | Executes PLAN.md → prose in co-author/scaffold/reviewer mode; per-task git commits, SUMMARY.md, STATE.md | `agents/wtfp/section-writer.md` |
| 5 | `wtfp-argument-verifier` | Goal-backward verification of written sections (claims made AND supported); VERIFIED / GAPS FOUND / HUMAN NEEDED | `agents/wtfp/argument-verifier.md` |
| 6 | `wtfp-section-reviewer` | 3-layer review (citation/coherence/rubric) with reviewer persona; produces ISSUES.md | `agents/wtfp/section-reviewer.md` |
| 7 | `wtfp-coherence-checker` | Cross-section consistency: terminology, argument coverage, narrative flow, cross-refs, contradictions | `agents/wtfp/coherence-checker.md` |
| 8 | `wtfp-prose-polisher` | De-AI-ify prose, sentence variety, apply voice profile (Authoritative/Measured/Accessible/Technical) | `agents/wtfp/prose-polisher.md` |
| 9 | `wtfp-research-synthesizer` | Literature investigation via citation pipeline + web search → RESEARCH.md | `agents/wtfp/research-synthesizer.md` |
| 10 | `citation-expert` | Searches Semantic Scholar/CrossRef, analyzes bib coverage vs argument map → suggested.bib (never overwrites references.bib) | `agents/wtfp/citation-expert.md` |
| 11 | `citation-formatter` | Audits BibTeX (missing keys, dups, format), cross-refs in-text cites → suggested file only | `agents/wtfp/citation-formatter.md` |

(Note: `agent-model-matrix.md` also lists a `citation-retriever` profile row, but only 11 agent files ship per runtime — that row is aspirational/duplicated with citation-expert.)

**How agents are defined — frontmatter example** (`citation-expert.md:1-8`):
```yaml
---
name: citation-expert
description: Searches academic databases (Semantic Scholar, CrossRef)...
allowed-tools:
  - Bash
  - Read
  - Write
---
```

**Full agent definition quoted: `vendors/claude/agents/wtfp/plan-checker.md`** (the quality gate; abridged structure shown, the 7 dimensions are the load-bearing part):

```yaml
---
name: wtfp-plan-checker
description: Validates section plans against 7 quality dimensions: argument coverage,
  citation planning, word budgets, outline compliance, CONTEXT.md fidelity, style
  consistency, and task completeness. Returns VERIFICATION PASSED or ISSUES FOUND...
allowed-tools: [Read, Bash, Glob, Grep]
---
<role>You verify that section plans WILL produce quality writing, not just that
they look complete. Spawned by /wtfp:plan-section. Goal-backward verification of
PLANS before writing.</role>

<core_principle>Plan completeness ≠ Section quality. A task "write methods" can be
in the plan while the methodology justification is missing.</core_principle>

<verification_dimensions>
## Dimension 1: Argument Coverage — every claim in argument-map.md has covering task(s)
## Dimension 2: Citation Coverage — evidence-requiring claims have sources
## Dimension 3: Word Budget Compliance — task targets sum to section target ±15%
## Dimension 4: Outline Compliance — plan subsections match outline.md
## Dimension 5: CONTEXT.md Fidelity — honor locked decisions, exclude deferred ideas
## Dimension 6: Style Consistency — writing modes match section types (warning only)
## Dimension 7: Task Completeness — every task has target+claims+action+verify+done
</verification_dimensions>

<structured_returns>
## VERIFICATION PASSED  (Dimensions: 7/7 passed, Issues: 0 blockers...)
## ISSUES FOUND          (Blockers / Warnings / Info with fix_hint)
</structured_returns>
```
Issues are emitted as structured YAML with `dimension`, `severity`, `description`, `plan`, `fix_hint` (`plan-checker.md:72-79`).

---

## 5. The 36 Commands / Skills (`/wtfp:*`)

36 commands per runtime (verified: `vendors/claude/commands/wtfp/` = 36, gemini = 36, opencode = 36). Full README reference: `README.md:104-181`. Enumeration:

**Setup (4):** new-paper, create-outline, map-project, analyze-bib
**Planning (4):** discuss-section, plan-section, list-assumptions, research-gap
**Writing (6):** write-section, execute-outline, quick, progress, pause-writing, resume-writing
**Review (5):** review-section, verify-work, plan-revision, polish-prose, check-refs
**Structure (4):** create-poster, create-slides, insert-section, remove-section
**Export/Submission (4):** export-latex, audit-milestone, plan-milestone-gaps, submit-milestone
**Settings/Productivity (5):** settings, checkpoint, add-todo, check-todos, update
**Help/Contributing (4):** help, report-bug, request-feature, contribute

That's 36. (Skills are separate from commands — Claude Code also gets 2 *skills*: `wtfp-marp`, `wtfp-echarts` in `vendors/claude/skills/wtfp/`.)

**Command structure** = YAML frontmatter (`name`, `description`, `argument-hint`, `allowed-tools` incl. `Task`) + body: `<execution_context>` (@-refs to workflows/references), `<objective>` (with **Orchestrator role** + **Why subagents**), `<context>` ($ARGUMENTS), `<process>` (numbered phases), `<offer_next>`, `<success_criteria>`.

**Command example quoted: `vendors/claude/commands/wtfp/write-section.md`** (head):
```yaml
---
name: wtfp:write-section
description: Write a section by executing its plan
argument-hint: "[path-to-PLAN.md]"
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, Task, AskUserQuestion]
---
<execution_context>
@~/.claude/write-the-f-paper/workflows/execute-section.md
@~/.claude/write-the-f-paper/references/git-integration.md
</execution_context>
<objective>
Execute a PLAN.md file to write section content.
**Orchestrator role:** Validate plan, resolve model profile, read context files,
spawn section-writer agent, optionally run argument-verifier post-write, route...
**Why subagents:** Writing burns context fast. Fresh agent gets peak prose quality.
Verification in fresh context catches what writer missed.
</objective>
<process>
## 1. Validate Environment and Resolve Model Profile
## 2. Read Context Files
## 3. Gate Check: Confirm Before Writing
## 4. Spawn wtfp-section-writer Agent  (Task(...subagent_type="general-purpose"...))
## 5. Handle Writer Return (WRITING COMPLETE / CHECKPOINT / BLOCKED)
## 6. Goal-Backward Verification (spawn wtfp-argument-verifier if config.workflow.verifier)
## 7. Git Branch Merge ...
</process>
```
The orchestrator reads config values out of `.planning/config.json` with `grep -o` one-liners (no jq dependency assumed) — e.g. model_profile, confirm_write, verifier, commit_docs, branching_strategy (`write-section.md:44-160`).

---

## 6. Workflows: verbose .md vs compressed .wcn.md + WCN

`core/write-the-f-paper/workflows/` holds **17 workflows, each in two forms**: `name.md` (verbose) and `name.wcn.md` (compressed). Examples: create-outline, plan-section, execute-section, execute-outline, research-gap, review-section, verify-work, discuss-section, list-assumptions, map-project, resume-paper, submit-draft, transition, lit-review-phase.

**WCN = Workflow Compression Notation** (`tools/wcn/SPEC.md`). v1.0.0, inspired by TOON/POML. A *prose compression notation for agent instructions* (not a data format). Goal: **40–60% token reduction** while *improving* comprehension for smaller (Haiku-class) models. Lossless, human-editable, no build step. Core syntax: `[step:name p=1] ... [/step]`, inline `IF cond → action`, `NAME{f1,f2}:` tables, `ROUTE{cond → output → next}:`, inline cmds `RUN:/READ:/WRITE:/PARSE:/ASK:/COMMIT:/EMIT:`, `@context{a,b,c}`, `[rule:...]`, `VERIFY{layer,checks}:`. Code blocks / XML structure tags / output templates are kept verbatim (`SPEC.md:297-304`).

**Measured savings (line counts, this repo):**
| Workflow | verbose | wcn | reduction |
|---|---|---|---|
| create-outline | 462 | 194 | ~58% |
| plan-section | 409 | 229 | ~44% |
| execute-section | 704 | 191 | ~73% |
| review-section | 329 | 90 | ~73% |
| verify-work | 251 | 74 | ~71% |
| research-gap | 493 | 135 | ~73% |

SPEC per-construct targets: step block 70%, route logic 80%, verify list 80%; overall 40–60% tokens. `tools/wcn/converter.js` computes real char-level reduction via `bin/lib/wcn-compiler.js` (`compile()`).

**Swapping:** `tools/wcn/swap-workflows.sh wcn|verbose` renames `*.md ↔ *.md.verbose` and copies `*.wcn.md` over the active `*.md` in `~/.claude/write-the-f-paper/workflows/` (`swap-workflows.sh:7-29`). `test/wcn-integrity.js` enforces that every `<step>` in the verbose file has a `[step:name]` in the WCN file (with an allowlist for plan-section/execute-section, intentionally *restructured* for the thin-orchestrator rewrite, not merely compressed).

---

## 7. Vendor Adapter Pattern (the key to Claude Code packaging)

Same capability, three runtime encodings. The map lives in **`bin/lib/manifest.js`** — one entry per runtime with `name`, `configDirEnv`, `defaultDir`, and a `components[]` list of `{id, src, dest}` copy rules.

| Concept | Claude Code | Gemini CLI | OpenCode |
|---|---|---|---|
| Config dir | `~/.claude` (`CLAUDE_CONFIG_DIR`) | `~/.config/gemini` (`GEMINI_CONFIG_DIR`) | `~/.opencode` (`OPENCODE_CONFIG_DIR`) |
| Command format | **Markdown + YAML frontmatter** | **TOML** (`description=`, `prompt='''...'''`, `{{args}}`) | **Markdown + YAML** (`$ARGUMENTS`) |
| Agent format | Markdown + YAML | Markdown + YAML | Markdown + YAML |
| Arg placeholder | `$ARGUMENTS` | `{{args}}` | `$ARGUMENTS` |
| Extras | skills, MCP server, plugin.json | — | — |
| @-path prefix | `~/.claude/...` | `~/.config/gemini/...` | `~/.opencode/...` |

The **same `write-section` orchestrator** appears as `vendors/claude/commands/wtfp/write-section.md` (YAML+md), `vendors/gemini/commands/wtfp/write-section.toml` (TOML wrapping the identical prose, `{{args}}` instead of `$ARGUMENTS`), and `vendors/opencode/commands/wtfp/write-section.md` (md, ASCII-only box chars). The *body prose is essentially identical*; only the wrapper/placeholder/paths differ.

**Path rewriting at install time:** `install-logic.js:45-51` `processContent()` rewrites every `~/.claude/` to the runtime's `pathPrefix` (e.g. `~/.config/gemini/`) when copying `.md`/`.json`. So the core docs are authored once with Claude paths and retargeted per runtime.

**Claude-only components** (`manifest.js:5-54`): `skills/wtfp` (marp, echarts SKILL.md), `mcp/research-server` (a real `@modelcontextprotocol/sdk` stdio server, ArXiv + Semantic Scholar, `vendors/claude/mcp/research-server/src/index.js`), and `.claude-plugin/plugin.json` (marketplace manifest, name `wtf-p`). Installer has a safety guard to never overwrite a *foreign* `plugin.json` (`install-logic.js:162-172`). All three runtimes share `core/write-the-f-paper` and the `bin/lib` scripts (installed to `<cfg>/bin/`).

---

## 8. Citation Grounding, Section Isolation, Quality, Model Profiles

**Citation grounding.**
- Tiered pipeline (v0.4.0): Semantic Scholar (primary, free) → SerpAPI/Google Scholar (optional/seminal) → CrossRef (fallback). Code in `bin/lib/citation-fetcher.js` (orchestrator), `semantic-scholar.js`, `scholar-lookup.js`, `citation-ranker.js` (impact scoring: citations, velocity, recency, venue), `bib-format.js`, `bib-index.js`, `analyze-impact.js`.
- Provenance: `wtfp_*` BibTeX fields; dedup via DOI/ScholarID.
- **Zero-risk rule:** agents write to `suggested.bib`/`suggested.*` only — never overwrite the user's `references.bib` (`citation-expert.md` & `citation-formatter.md` descriptions; ROADMAP principle #8).
- `/wtfp:analyze-bib` → citation-expert; `/wtfp:check-refs` → citation-formatter; `/wtfp:research-gap` → research-synthesizer.

**Section isolation.** Each section written by a fresh `section-writer` agent whose prompt inlines only: full PLAN.md, PROJECT+STATE+argument-map, CONTEXT.md user decisions, and `paper/*.md | head -500` for continuity (`write-section.md:99-110`). Prevents context pollution / lets each section get peak context budget.

**Quality verification.**
- *Pre-write*: `plan-checker` runs **7 dimensions** (argument coverage, citation coverage, word budget ±15%, outline compliance, CONTEXT.md fidelity, style consistency, task completeness), up to 3 revision iterations (`plan-checker.md:56-191`).
- *Post-write*: `argument-verifier` does goal-backward checking (claims made AND supported).
- *Review*: `section-reviewer` runs **3 layers** (Citation / Coherence / Rubric) under a selectable **persona** — Reviewer #2 (Hostile), Area Chair, Camera-Ready Editor, Friendly Mentor — each adjusting severity calibration (`section-reviewer.md:32-134`). Note: README/quality-loop language says "7 quality dimensions" = the plan-checker dimensions; reviewer is the separate 3-layer/4-persona system.
- All toggled via `config.json` `workflow.{research,plan_check,verifier}` and `verification.{citation_check,coherence_check,rubric_check}`.

**Model profiles** (`references/agent-model-matrix.md`). `model_profile` ∈ quality | balanced(default) | budget, resolved at runtime from config. Per-agent matrix, e.g.:
| Agent | quality | balanced | budget |
|---|---|---|---|
| section-planner | opus | opus | sonnet |
| section-writer | opus | sonnet | sonnet |
| plan-checker / argument-verifier | sonnet | sonnet | haiku |
| citation-formatter | sonnet | haiku | haiku |
balanced keeps the *planner* at opus (argument quality) but drops the *writer* to sonnet (cost).

---

## 9. Config Schema (`.planning/config.json`)

Template: `core/write-the-f-paper/templates/config.json`. Lives in the user's `.planning/` dir. Top-level keys:
- `mode` ("interactive"), `depth` ("standard"), `document_type` ("paper"), `output_format` ("markdown"), `model_profile` ("balanced"), `venue_template` (null).
- `gates{}` — 8 confirmation gates (confirm_outline, confirm_plan, confirm_write, confirm_review, execute_next_section, issues_review, confirm_transition, confirm_submission). A `mode: "yolo"` auto-approves (`section-writer.md:122-126`).
- `writing{}` — claude_mode ("co-author"), citation_style ("apa"), verify_on_complete.
- `workflow{}` — research / plan_check / verifier toggles.
- `verification{}` — citation_check / coherence_check / rubric_check.
- `planning{}` — commit_docs, search_gitignored.
- `parallelization{}` — enabled, plan_level, task_level, skip_checkpoints, max_concurrent_agents (3), min_plans_for_parallel (2). Wave-based parallel writing via `wave`/`depends_on` in PLAN.md.
- `safety{}` — always_confirm_destructive, always_confirm_external_services, backup_before_major_edits.
- `git{}` — branching_strategy ("none"|"section"|"submission"), section/submission branch templates, squash_on_merge.

Preference inheritance chain (`templates/base-prefs.yaml:1-6`): `~/.wtfp/base.yaml` → `.planning/prefs.yaml` → `config.json` (runtime). base-prefs covers style voice/person/hedging, citation style, prose, workflow defaults, model_profile override.

---

## Reusable for clio-parser

The **Claude Code packaging pattern** here is the most transferable asset:

1. **Markdown-as-program.** All agent/command intelligence is plain Markdown + YAML frontmatter (`name`, `description`, `allowed-tools`) with an XML-tagged body. No code to ship the "logic" — the runtime executes the prompt files. clio-parser can package its own agents/commands the same way under `<cfg>/agents/<ns>/` and `<cfg>/commands/<ns>/`.
2. **Thin orchestrator → agent → quality-loop.** Command = router that resolves config, `Task()`-spawns a `general-purpose` agent told to "First, read ~/.claude/agents/<ns>/<agent>.md", inlines runtime context into the prompt, then parses a **structured return header** (COMPLETE/CHECKPOINT/BLOCKED) for deterministic control flow. A second "checker" agent verifies in a fresh context. This is a clean, copyable multi-agent contract.
3. **Manifest-driven multi-runtime installer.** `bin/lib/manifest.js` is a tiny declarative `{runtime → {configDir, components[{id,src,dest}]}}` map; `install-logic.js` walks it, does conflict resolution (overwrite/skip/backup/all), rewrites `~/.claude/` paths per runtime, and writes a version-tracking manifest for clean uninstall. Pure Node builtins, zero deps — trivially vendorable.
4. **WCN compression** for fitting verbose agent instructions into small context windows (40–73% reduction measured), with a swap script and an integrity test that proves the compressed form preserves every step. Directly relevant if clio-parser ships large prompt files.
5. **Provenance + zero-risk file policy** (write to `suggested.*`, never the user's source of truth) and **git-as-state** (per-task commits, checkpoints via git tags in `bin/lib/checkpoint.js`).
6. **Config-as-dial.** Single `config.json` with `grep -o` parsing inside prompts (no jq dependency) toggles gates, model profiles, parallelism, verification layers — lets the same prompts behave differently per project.

---

## Open Questions

- `agent-model-matrix.md` lists 12 rows (incl. `citation-retriever`) but only **11 agent files** ship per runtime; is citation-retriever a planned/merged agent or stale doc?
- The MCP `research-server` (`vendors/claude/mcp/research-server`) is Claude-only and at v0.4.0 while the package is v0.5.0 — is it still wired in, and how does it relate to the duplicate `bin/lib/*` citation libs (which path do agents actually use at runtime)?
- WCN files are *swapped in manually* via `swap-workflows.sh`; there's no config flag to auto-select WCN by model_profile — is small-model routing meant to be automatic eventually?
- `parallelization.enabled` defaults `false` and relies on `wave`/`depends_on` in PLAN.md — how mature/tested is the wave scheduler vs documented intent?
- Reviewer "personas" (Hostile/Area Chair/Editor/Mentor) — where is the persona selected? (Appears orchestrator-supplied; not surfaced in config.json schema.)

---

## 10-Line Summary

1. WTF-P (MIT, v0.5.0) is a Node CLI (`npx wtf-p`) that installs academic-writing commands into Claude Code / Gemini CLI / OpenCode.
2. The "intelligence" is Markdown prompt files, not code; the Node side is only an installer + citation API toolkit + WCN compressor.
3. Architecture: **thin orchestrator (command) → specialized agent (Task-spawned, fresh context) → quality loop (checker agent)**, with structured return headers for routing.
4. **11 agents** (outliner, section-planner, plan-checker, section-writer, argument-verifier, section-reviewer, coherence-checker, prose-polisher, research-synthesizer, citation-expert, citation-formatter) in `vendors/<rt>/agents/wtfp/`, defined as md+YAML frontmatter.
5. **36 commands** (`/wtfp:*`) per runtime in `vendors/<rt>/commands/wtfp/`; structure = frontmatter + `<execution_context>/<objective>/<process>/<offer_next>`.
6. Vendor adapter pattern: shared `core/`; per-runtime wrappers (Claude md+YAML, Gemini TOML, OpenCode md); `bin/lib/manifest.js` maps components and the installer rewrites `~/.claude/` paths per runtime.
7. Workflows ship verbose `.md` + compressed `.wcn.md`; **WCN** is a prose-compression notation (~40–73% reduction here) for small-context models, swappable via `swap-workflows.sh`.
8. Quality = pre-write **plan-checker (7 dimensions)** + post-write **argument-verifier (goal-backward)** + **section-reviewer (3 layers × 4 personas)**; all config-gated.
9. Citation grounding is a tiered Semantic Scholar→SerpAPI→CrossRef pipeline with impact scoring and a strict write-to-`suggested.*`-only policy; model_profile (quality/balanced/budget) routes each agent via `agent-model-matrix.md`.
10. Config is one `.planning/config.json` (gates, workflow toggles, parallelization, safety, git) layered over `base-prefs.yaml`; git is the source of truth (per-task commits, tagged checkpoints).
</content>
</invoke>
