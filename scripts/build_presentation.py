#!/usr/bin/env python
"""Build docs/AUTHOR.pptx — a ~10-slide PowerPoint deck for AUTHOR (clio-author).

Mirrors docs/PRESENTATION.md. Plain python-pptx, no template; run with:
    uv run --with python-pptx python scripts/build_presentation.py
Output: docs/AUTHOR.pptx
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).resolve().parent.parent / "docs" / "AUTHOR.pptx"

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x44, 0x44, 0x44)
ACCENT = RGBColor(0x2E, 0x7D, 0x32)

prs = Presentation()
prs.slide_width = Inches(13.333)  # 16:9
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height


def _tb(slide, left, top, width, height):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    return tf


def title_slide(title: str, subtitle: str, footer: str) -> None:
    slide = prs.slides.add_slide(BLANK)
    band = slide.shapes.add_shape(1, 0, Inches(2.4), SW, Inches(1.5))
    band.fill.solid()
    band.fill.fore_color.rgb = NAVY
    band.line.fill.background()
    tf = band.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.size = Pt(46)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    tf2 = _tb(slide, Inches(1), Inches(4.1), Inches(11.33), Inches(1.6))
    p = tf2.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = subtitle
    r.font.size = Pt(20)
    r.font.color.rgb = GREY

    tf3 = _tb(slide, Inches(1), Inches(6.4), Inches(11.33), Inches(0.7))
    p = tf3.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = footer
    r.font.size = Pt(13)
    r.font.italic = True
    r.font.color.rgb = ACCENT


def _add_header(slide, title: str) -> None:
    bar = slide.shapes.add_shape(1, 0, 0, SW, Inches(0.95))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    tf = bar.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.4)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(26)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def bullet_slide(title: str, bullets: list[tuple[int, str, bool]]) -> None:
    """bullets: list of (level, text, bold-lead). Level 0/1 indent."""
    slide = prs.slides.add_slide(BLANK)
    _add_header(slide, title)
    tf = _tb(slide, Inches(0.6), Inches(1.2), Inches(12.1), Inches(6.0))
    first = True
    for level, text, bold in bullets:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.level = level
        p.space_after = Pt(8)
        # split a leading "**lead** rest" emphasis on first segment
        if bold and ":" in text:
            lead, rest = text.split(":", 1)
            r = p.add_run()
            r.text = ("• " if level == 0 else "– ") + lead + ":"
            r.font.size = Pt(17 if level == 0 else 15)
            r.font.bold = True
            r.font.color.rgb = NAVY
            r2 = p.add_run()
            r2.text = rest
            r2.font.size = Pt(17 if level == 0 else 15)
            r2.font.color.rgb = GREY
        else:
            r = p.add_run()
            r.text = ("• " if level == 0 else "– ") + text
            r.font.size = Pt(17 if level == 0 else 15)
            r.font.color.rgb = GREY
    return slide


def table_slide(title: str, headers: list[str], rows: list[list[str]], note: str = "",
                col0_wide: bool = True, font: int = 12) -> None:
    slide = prs.slides.add_slide(BLANK)
    _add_header(slide, title)
    ncols = len(headers)
    nrows = len(rows) + 1
    left, top = Inches(0.5), Inches(1.25)
    width = Inches(12.33)
    height = Inches(0.45) * nrows
    gtable = slide.shapes.add_table(nrows, ncols, left, top, width, height).table
    if col0_wide and ncols > 2:
        gtable.columns[0].width = Inches(3.6)
        rest = int((Inches(12.33) - Inches(3.6)) / (ncols - 1))
        for c in range(1, ncols):
            gtable.columns[c].width = Emu(rest)
    for c, h in enumerate(headers):
        cell = gtable.cell(0, c)
        cell.text = h
        para = cell.text_frame.paragraphs[0]
        para.runs[0].font.size = Pt(font)
        para.runs[0].font.bold = True
        para.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
    for ri, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = gtable.cell(ri, c)
            cell.text = val
            para = cell.text_frame.paragraphs[0]
            para.runs[0].font.size = Pt(font)
            if c == 0:
                para.runs[0].font.bold = True
                para.runs[0].font.color.rgb = NAVY
            else:
                para.runs[0].font.color.rgb = GREY
    if note:
        tf = _tb(slide, Inches(0.5), Inches(1.25) + height + Inches(0.1), Inches(12.33), Inches(0.8))
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = note
        r.font.size = Pt(12)
        r.font.italic = True
        r.font.color.rgb = ACCENT


# ---------------------------------------------------------------- slides
title_slide(
    "AUTHOR",
    "Agentic Understanding for Thesis, Hypothesis, and Objective Research\n"
    "One host-invocable package across the whole scientific-paper lifecycle:\n"
    "read → understand → verify citations → review → plan → write → illustrate → export",
    "Invoked by the CLIO agent as a subagent  ·  18 actions  ·  grounded, not hallucinated",
)

bullet_slide("1 · What this is (and the paper)", [
    (0, "AUTHOR: one Python package that turns a paper (arXiv link / PDF / title) into clean Markdown + memory blocks, then runs specialized expert agents to answer, verify, review, plan, write, illustrate, and export — behind one interface a host agent can call.", True),
    (0, "Paper title: AUTHOR — Agentic Understanding for Thesis, Hypothesis, and Objective Research.", True),
    (0, "Core claim: the contribution is unifying the lifecycle in one grounded, composable package — not any single capability in isolation.", True),
    (0, "Status: built end-to-end — 18 actions, ~460 hermetic tests, CI green; validated live (Claude / Codex / Ollama / Gemini vision / live citation backends).", True),
])

bullet_slide("2 · Motivation — why this is needed", [
    (0, "Fragmentation tax: researchers stitch together separate, non-interoperating tools — a parser, a literature-QA tool, a citation auditor, a writing agent, a figure agent, a LaTeX exporter — none sharing a data model.", True),
    (0, "Hallucination is the central failure: LLM writing fabricates citations at high rates (78–90% reported for GPT-4o); survey generators are uniformly weak on reference quality. Trust requires grounding, not generation.", True),
    (0, "Hosts need a composable capability, not a closed pipeline: a larger agent (CLIO) should invoke paper processing/writing on demand — load, use, drop.", True),
    (0, "One substrate, reused: ingest once → the same memory blocks feed Q&A, review, and writing.", True),
])

table_slide("3 · The gap — nobody unifies the lifecycle",
    ["Camp", "Examples", "Does", "Omits"],
    [
        ["Ingest-only parsers", "Docling, MinerU", "PDF→MD + vision", "write / review / verify"],
        ["End-to-end generators", "AI Scientist, Agent Lab, CycleResearcher", "ideate→experiment→write (closed)", "external ingest, cite-verify, host API"],
        ["Single-slice specialists", "AutoSurvey, PaperBanana, CiteCheck, PaperQA2", "one capability well", "everything else"],
    ],
    note="The quadrant {vision ingest + grounded QA + cite-verify + review + write + figures + export} as ONE host-invocable package is held by no one. That is AUTHOR's position.",
    font=13)

table_slide("4 · Capability coverage (AUTHOR vs the field)",
    ["System", "In", "QA", "CV", "Rv", "Wr", "Fg", "Ex", "1pkg", "Host"],
    [
        ["AUTHOR", "Y", "Y", "Y", "Y", "Y", "Y", "Y", "Y", "Y"],
        ["AI Scientist v2", "N", "N", "P", "Y", "Y", "Y", "Y", "P", "N"],
        ["PaperOrchestra", "N", "P", "P", "P", "Y", "Y", "Y", "P", "N"],
        ["AutoSurvey", "N", "Y", "P", "N", "Y", "N", "N", "P", "N"],
        ["PaperBanana", "N", "P", "N", "P", "N", "Y", "P", "N", "P"],
        ["Docling / MinerU", "Y", "N", "N", "N", "N", "N", "P", "Y", "Y"],
        ["PaperQA2", "N", "Y", "P", "N", "N", "N", "N", "N", "Y"],
    ],
    note="No row but AUTHOR is all-Y. In=ingest QA=grounded-QA CV=cite-verify Rv=review Wr=write Fg=figures Ex=export. Full matrix + a source per cell: docs/MOTIVATION.md",
    col0_wide=True, font=12)

bullet_slide("5 · What we built — the 18 actions", [
    (0, "Read / understand: ingest (PDF→MD + blocks + figures), ask (grounded Q&A), kg (content knowledge graph)", True),
    (0, "Verify: cite (Semantic Scholar → OpenAlex → Crossref → arXiv cascade; suggestions only, never edits)", True),
    (0, "Review: review (decision + scores + --ground), meta_review (panel), write_review (loop)", True),
    (0, "Write: plan (tasks/claims/sources), write, edit, polish, coherence, compose (whole paper), export (→ LaTeX)", True),
    (0, "Illustrate: plot, describe_figures (Gemini vision), figure_refine (loop)", True),
    (0, "Drive: orchestrate (goal → plan a sequence of the above → execute)", True),
    (0, "One adapter (capabilities() + run(action, payload)) + a CLI — stateless, JSON in/out, never raises.", False),
])

bullet_slide("6 · References & artifacts we built on", [
    (0, "Combined (the mandate):", True),
    (1, "Processing — paper-to-md (+ phagocyte) and PaperBanana (arXiv 2601.23265)", False),
    (1, "Writing / editing — wtf-p and PaperOrchestra (arXiv 2604.05018)", False),
    (0, "Harness references (concepts re-implemented, not copied):", True),
    (1, "papervizagent — orchestrator + expert agents + critic loop → CriticRefine + figure_agent", False),
    (1, "protoneo/knowledge (AGPL) — BaseAgent / deliberation patterns / KG → harness/ + kg", False),
    (0, "All cloned in artifact/repos/; both papers in artifact/papers/; deep-study notes in artifact/notes/. License-clean (BSD-3-Clause; no AGPL code copied).", False),
])

# design slide (monospace block)
sld = prs.slides.add_slide(BLANK)
_add_header(sld, "7 · Design — how it's put together")
diagram = (
    "host (CLIO)  ──►  ClioAuthorSubagent   (capabilities + run; JSON; never-raises)\n"
    "                        │\n"
    "                   Main agent (router)  +  orchestrate (goal → plan → execute)\n"
    "                        │\n"
    "        expert agents:  ingestor · paper_qa · citation · reviewer/meta ·\n"
    "        planner · writer/editor · polish · coherence · figure_agent · kg ·\n"
    "        compose · export\n"
    "                        │\n"
    "        backends:  retrieval (RAG + scholarly cascade) · vision (Gemini) ·\n"
    "        SafeFiles (read/write/edit, sandboxed) · LLM (claude/codex/ollama/echo)"
)
tf = _tb(sld, Inches(0.6), Inches(1.2), Inches(12.1), Inches(3.6))
p = tf.paragraphs[0]
r = p.add_run()
r.text = diagram
r.font.name = "Courier New"
r.font.size = Pt(13)
r.font.color.rgb = NAVY
tf2 = _tb(sld, Inches(0.6), Inches(5.2), Inches(12.1), Inches(1.8))
p = tf2.paragraphs[0]
r = p.add_run()
r.text = "Principles:  expert agents + retrieval + read/write/edit tools  ·  grounded (verify, source-bound)  ·  standalone harness, thin host bridge  ·  hermetic-first (offline echo model; heavy paths gated)."
r.font.size = Pt(15)
r.font.color.rgb = GREY

table_slide("8 · How we'll prove it — evaluation plan (why each matters)",
    ["Track", "Why we need it", "Baselines"],
    [
        ["PDF→MD fidelity", "ingest errors propagate to every action", "paper-to-md, Docling, MinerU"],
        ["Figures", "high-bar, easily-judged; backs 'writes a paper'", "PaperBanana, DeTikZify"],
        ["Citation verify", "the grounding claim; hallucination is the top failure", "CiteCheck, PaperOrchestra"],
        ["Review", "must track ground-truth decisions; does --ground help?", "AgentReview, DeepReview"],
        ["Writing", "most visible output; parity = credible, not marketing", "PaperOrchestra, AutoSurvey"],
        ["Orchestration + cost", "composability is part of the novelty; budgets", "—"],
    ],
    note="Phasing: Phase 0 automated metrics (now) → Phase 1 LLM/VLM-as-Judge → Phase 2 human win-rates. Full plan: docs/BENCHMARK-PLAN.md",
    col0_wide=True, font=12)

bullet_slide("9 · Justification — why this is worth doing", [
    (0, "A real, unoccupied gap: surveyed 20+ systems; none unify the lifecycle as one grounded, host-invocable package (slides 3–4).", True),
    (0, "Fixes the trust problem: verification + source-grounded writing vs hallucination-prone generators.", True),
    (0, "A reusable substrate, not a one-off: a host (CLIO) gains paper read/review/write as composable, on-demand capabilities; experts compose in any order.", True),
    (0, "Already real: built, tested, demonstrable today; the benchmark plan turns the claim into numbers a reviewer will accept.", True),
    (0, "Objection — 'isn't this just tool orchestration?': frameworks (MCP, LangGraph) are domain-agnostic plumbing that ship zero paper-lifecycle capability. AUTHOR is the missing domain package; MCP is just how a host reaches it.", True),
])

bullet_slide("10 · Status & next steps", [
    (0, "Done: 18 actions · ~460 hermetic tests + CI · live-validated (Claude/Codex/Ollama/Gemini, real citation backends) · motivation + benchmark plan · dynamic orchestrate.", True),
    (0, "Next:", True),
    (1, "Demo — prove a host agent (Claude/Codex) invokes AUTHOR as a subagent end-to-end.", False),
    (1, "CLIO integration — thin MCP bridge (CLIO invokes external capability via MCP); file a CLIO feature request for an in-process subagent hook.", False),
    (1, "Benchmarks — run Phase 0 metrics; scope datasets / judge models / human eval.", False),
    (0, "Open decisions: the bar (beat specialists vs parity + unification) · dataset access (PaperBananaBench / PaperWritingBench) · human-eval resourcing.", True),
    (0, "Repo: github.com/SIslamMun/clio-author  ·  docs/MOTIVATION.md, BENCHMARK-PLAN.md, RUNBOOK.md", False),
])

prs.save(str(OUT))
print(f"wrote {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
