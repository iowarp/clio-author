#!/usr/bin/env python
"""Build the AUTHOR deck as BOTH PowerPoint and PDF from one content model.

Content is defined once in SLIDES; rendered to docs/AUTHOR.pptx (python-pptx)
and docs/AUTHOR.pdf (fpdf2) so the two never drift. Run with:
    uv run --with python-pptx --with fpdf2 python scripts/build_presentation.py
"""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
PPTX = DOCS / "AUTHOR.pptx"
PDF = DOCS / "AUTHOR.pdf"

NAVY = (0x1F, 0x3A, 0x5F)
GREY = (0x44, 0x44, 0x44)
ACCENT = (0x2E, 0x7D, 0x32)
WHITE = (0xFF, 0xFF, 0xFF)
LIGHT = (0xEE, 0xF2, 0xF7)

SLIDES: list[dict] = [
    {
        "type": "title",
        "title": "AUTHOR",
        "subtitle": (
            "Agentic Understanding for Thesis, Hypothesis, and Objective Research\n"
            "One host-invocable package across the whole scientific-paper lifecycle:\n"
            "read -> understand -> verify citations -> review -> plan -> write -> illustrate -> export"
        ),
        "footer": "Invoked by the CLIO agent as a subagent   .   27 actions   .   grounded, not hallucinated",
    },
    {
        "type": "bullets",
        "title": "1 . What this is (and the paper)",
        "bullets": [
            (
                0,
                "AUTHOR: one Python package that turns a paper (arXiv link / PDF / title) into clean Markdown + memory blocks, then runs specialized expert agents to answer, verify, review, plan, write, illustrate, and export - behind one interface a host agent can call.",
            ),
            (
                0,
                "Paper title: AUTHOR - Agentic Understanding for Thesis, Hypothesis, and Objective Research.",
            ),
            (
                0,
                "Core claim: the contribution is unifying the lifecycle in one grounded, composable package - not any single capability in isolation.",
            ),
            (
                0,
                "Status: built end-to-end - 27 actions, ~587 hermetic tests, CI green; validated live (Claude / Codex / Ollama / Gemini vision / live citation backends).",
            ),
        ],
    },
    {
        "type": "bullets",
        "title": "2 . Motivation - why this is needed",
        "bullets": [
            (
                0,
                "Scientific output is exploding while the tools to process it stay siloed - reading, checking, and writing papers is still mostly manual or glued together by hand.",
            ),
            (
                0,
                "Fragmentation tax: a researcher stitches together a PDF parser, a literature-QA tool, a citation auditor, a writing agent, a figure agent, and a LaTeX exporter - none sharing a data model, each re-parsing the same paper.",
            ),
            (
                0,
                "Hallucination is the central failure mode: LLM writing fabricates citations at high rates (78-90% reported for GPT-4o); survey generators are uniformly weak on reference quality. Adoption demands grounding, not free-form generation.",
            ),
            (
                0,
                "Closed pipelines don't compose: end-to-end 'AI scientist' systems emit one artifact and stop - a host agent can't reach in and invoke just the review step, or just ingestion.",
            ),
            (
                0,
                "Hosts need an on-demand capability: a larger agent (CLIO) should load paper processing/writing, use it, and drop it - like calling a library, not running a monolith.",
            ),
            (
                0,
                "One substrate, reused: ingest once -> the same memory blocks feed Q&A, review, planning, and writing - no lossy re-parsing between stages.",
            ),
        ],
    },
    {
        "type": "bullets",
        "title": "2b . The cost today (concretely)",
        "bullets": [
            (
                0,
                "A typical 'process + review + write related work' task today touches 4-6 disjoint tools:",
            ),
            (1, "PDF -> Markdown: Docling / MinerU (no writing, no citation check)"),
            (1, "Ask questions about it: PaperQA2 / OpenScholar (separate index, separate API)"),
            (
                1,
                "Check the references: a citation auditor (CiteCheck) - yet another tool, another format",
            ),
            (
                1,
                "Draft text: a survey/writing agent (AutoSurvey / PaperOrchestra) - starts over, re-ingests",
            ),
            (1, "Make a figure: PaperBanana; export LaTeX: a sixth step"),
            (
                0,
                "Each boundary loses structure, repeats work, and adds a place for hallucinated or unverifiable output to slip in. Nothing carries the paper's grounded representation across all stages.",
            ),
            (
                0,
                "AUTHOR replaces that chain with one grounded substrate and one interface - the integration is the point.",
            ),
        ],
    },
    {
        "type": "table",
        "title": "3 . The gap - nobody unifies the lifecycle",
        "headers": ["Camp", "Examples", "Does well", "Omits"],
        "rows": [
            [
                "Ingest-only parsers",
                "Docling, MinerU",
                "PDF->MD + vision",
                "write / review / verify / host API",
            ],
            [
                "End-to-end generators",
                "AI Scientist, Agent Lab, CycleResearcher",
                "ideate->experiment->write (closed)",
                "external ingest, cite-verify, host API",
            ],
            [
                "Single-slice specialists",
                "AutoSurvey, PaperBanana, CiteCheck, PaperQA2",
                "one capability, very well",
                "every other capability",
            ],
        ],
        "note": "The quadrant {vision ingest + grounded QA + cite-verify + review + write + figures + export} as ONE host-invocable package is held by no one. That is AUTHOR's position.",
        "col0": 52,
        "font": 12,
    },
    {
        "type": "bullets",
        "title": "3b . Gap - even the closest systems miss most of it",
        "bullets": [
            (
                0,
                "AI Scientist v2 - generates NEW research end-to-end and reviews its own output, but does not ingest external PDFs, does no grounded Q&A, does not verify citations against scholarly DBs, and is a closed CLI with no host tool-surface.",
            ),
            (
                0,
                "PaperOrchestra - strongest writing system (write + figures + export), but: no ingest, only partial QA, only partial citation-verify, no review, no host API.",
            ),
            (
                0,
                "AutoSurvey / SurveyForge - write cited surveys from a curated abstract DB; cannot ingest arbitrary PDFs with vision, do not verify against external DBs, no review/figures/export.",
            ),
            (
                0,
                "PaperQA2 / OpenScholar - excellent grounded literature-QA and host-invocable, but verify their OWN answers against a corpus, not a manuscript's bibliography; no ingest-with-vision, review, writing, figures, or export.",
            ),
            (0, "Docling / MinerU - best-in-class ingest, then stop: nothing downstream."),
            (
                0,
                "Takeaway: the capabilities exist but are disjoint across systems and don't interoperate - exactly the integration gap AUTHOR closes.",
            ),
        ],
    },
    {
        "type": "table",
        "title": "4 . Capability coverage (AUTHOR vs the field)",
        "headers": ["System", "In", "QA", "CV", "Rv", "Wr", "Fg", "Ex", "1pkg", "Host"],
        "rows": [
            ["AUTHOR", "Y", "Y", "Y", "Y", "Y", "Y", "Y", "Y", "Y"],
            ["AI Scientist v2", "N", "N", "P", "Y", "Y", "Y", "Y", "P", "N"],
            ["PaperOrchestra", "N", "P", "P", "P", "Y", "Y", "Y", "P", "N"],
            ["AutoSurvey", "N", "Y", "P", "N", "Y", "N", "N", "P", "N"],
            ["PaperBanana", "N", "P", "N", "P", "N", "Y", "P", "N", "P"],
            ["Docling / MinerU", "Y", "N", "N", "N", "N", "N", "P", "Y", "Y"],
            ["PaperQA2", "N", "Y", "P", "N", "N", "N", "N", "N", "Y"],
        ],
        "note": "No row but AUTHOR is all-Y.  In=ingest QA=grounded-QA CV=cite-verify Rv=review Wr=write Fg=figures Ex=export.  Full matrix + a source per cell: docs/MOTIVATION.md",
        "col0": 42,
        "font": 12,
    },
    {
        "type": "bullets",
        "title": "5 . What we built - the 27 actions",
        "bullets": [
            (
                0,
                "Read / understand: ingest (PDF->MD + blocks + figures), ask (grounded Q&A), kg (content knowledge graph)",
            ),
            (
                0,
                "Discover/verify: discover (find real papers via scholarly search), cite (verify; 4-source cascade), check_refs (BibTeX audit)",
            ),
            (
                0,
                "Review: review (decision + scores + --ground; multimodal - sees figures via vision), meta_review (panel), rebuttal (point-by-point), write_review (loop)",
            ),
            (
                0,
                "Write: plan, write, edit, polish, coherence, compose (whole paper), export (-> LaTeX + PDF via --pdf)",
            ),
            (0, "Illustrate: plot, describe_figures (Gemini vision), figure_refine (loop)"),
            (
                0,
                "Research/verify: research (grounded lit brief), verify_work (claim coverage), check_refs (BibTeX audit), section_review (3-layer), audit (pre-submission)",
            ),
            (
                0,
                "Knowledge graph: kg (single-shot) and kg --full (6-stage pipeline: ontology->extraction->coref->verification, clean-room protoneo)",
            ),
            (0, "Drive: orchestrate (goal -> plan a sequence of the above -> execute)"),
            (
                0,
                "One adapter (capabilities() + run(action, payload)) + a CLI - stateless, JSON in/out, never raises.",
            ),
        ],
    },
    {
        "type": "bullets",
        "title": "6 . References & artifacts we built on",
        "bullets": [
            (0, "Combined (the mandate):"),
            (1, "Processing - paper-to-md (+ phagocyte) and PaperBanana (arXiv 2601.23265)"),
            (1, "Writing / editing - wtf-p and PaperOrchestra (arXiv 2604.05018)"),
            (0, "Harness references (concepts re-implemented, not copied):"),
            (
                1,
                "papervizagent - orchestrator + expert agents + critic loop -> CriticRefine + figure_agent",
            ),
            (
                1,
                "protoneo/knowledge (AGPL) - BaseAgent / deliberation patterns / KG -> harness/ + kg",
            ),
            (
                0,
                "All cloned in artifact/repos/; both papers in artifact/papers/; deep-study notes in artifact/notes/.",
            ),
            (
                0,
                "License-clean (BSD-3-Clause; no AGPL code copied - protoneo concepts re-implemented from scratch).",
            ),
        ],
    },
    {
        "type": "diagram",
        "title": "7 . Design - how it's put together",
        "diagram": (
            "host (CLIO)  --->  ClioAuthorSubagent   (capabilities + run; JSON; never-raises)\n"
            "                        |\n"
            "                   Main agent (router)  +  orchestrate (goal -> plan -> execute)\n"
            "                        |\n"
            "    expert agents:  ingestor . paper_qa . citation . reviewer/meta .\n"
            "    planner . writer/editor . polish . coherence . figure_agent . kg .\n"
            "    compose . export\n"
            "                        |\n"
            "    backends:  retrieval (RAG + scholarly cascade) . vision (Gemini) .\n"
            "    SafeFiles (read/write/edit, sandboxed) . LLM (claude/codex/ollama/echo)"
        ),
        "note": "Principles: expert agents + retrieval + read/write/edit tools  .  grounded (verify, source-bound)  .  standalone harness, thin host bridge  .  hermetic-first (offline echo model; heavy paths gated).",
    },
    {
        "type": "table",
        "title": "8 . How we'll prove it - evaluation plan",
        "headers": ["Track", "Why we need it", "Baselines"],
        "rows": [
            [
                "PDF->MD fidelity",
                "ingest errors propagate to every action",
                "paper-to-md, Docling, MinerU",
            ],
            [
                "Figures",
                "high-bar, easily-judged; backs 'writes a paper'",
                "PaperBanana, DeTikZify",
            ],
            [
                "Citation verify",
                "the grounding claim; hallucination is the top failure",
                "CiteCheck, PaperOrchestra",
            ],
            [
                "Review",
                "must track ground-truth decisions; does --ground help?",
                "AgentReview, DeepReview (data: ASAP-Review, PeerRead, ORB, MMReview)",
            ],
            [
                "Writing",
                "most visible output; parity = credible, not marketing",
                "PaperOrchestra, AutoSurvey",
            ],
            ["Orchestration + cost", "composability is part of the novelty; budgets", "-"],
        ],
        "note": "Review datasets secured: PeerRead, ASAP-Review, NLPeer, MOPRD, ORB, MMReview (cross-domain + multimodal).  Phasing: Phase 0 automated metrics (now) -> Phase 1 LLM/VLM-as-Judge -> Phase 2 human win-rates.  Full plan: docs/BENCHMARK-PLAN.md",
        "col0": 40,
        "font": 12,
    },
    {
        "type": "bullets",
        "title": "9 . Justification - why this is worth doing",
        "bullets": [
            (
                0,
                "A real, unoccupied gap: surveyed 20+ systems; none unify the lifecycle as one grounded, host-invocable package (slides 3-4).",
            ),
            (
                0,
                "Fixes the trust problem: verification + source-grounded writing vs hallucination-prone generators.",
            ),
            (
                0,
                "A reusable substrate, not a one-off: a host (CLIO) gains paper read/review/write as composable, on-demand capabilities; experts compose in any order.",
            ),
            (
                0,
                "Already real: built, tested, demonstrable today; the benchmark plan turns the claim into numbers a reviewer will accept.",
            ),
            (
                0,
                "External validation: the newest cross-domain + multimodal review benchmark (MMReview) tests exactly our edge - vision-grounded review across 17 domains, which text-only reviewers structurally can't do.",
            ),
            (
                0,
                "Objection - 'isn't this just tool orchestration?': frameworks (MCP, LangGraph) are domain-agnostic plumbing that ship zero paper-lifecycle capability. AUTHOR is the missing domain package; MCP is just how a host reaches it.",
            ),
        ],
    },
    {
        "type": "bullets",
        "title": "10 . Status & next steps",
        "bullets": [
            (
                0,
                "Done: 27 actions . ~587 hermetic tests + CI . live-validated (Claude/Codex/Ollama/Gemini, real citation backends) . motivation + benchmark plan . dynamic orchestrate.",
            ),
            (0, "Next:"),
            (
                1,
                "Demo - prove a host agent (Claude/Codex) invokes AUTHOR as a subagent end-to-end.",
            ),
            (
                1,
                "CLIO integration - thin MCP bridge (CLIO invokes external capability via MCP); file a CLIO feature request for an in-process subagent hook.",
            ),
            (1, "Benchmarks - run Phase 0 metrics; scope datasets / judge models / human eval."),
            (
                0,
                "Open decisions: the bar (beat specialists vs parity + unification) . dataset access (PaperBananaBench / PaperWritingBench) . human-eval resourcing.",
            ),
            (
                0,
                "Repo: github.com/SIslamMun/clio-author  .  docs/MOTIVATION.md, BENCHMARK-PLAN.md, RUNBOOK.md",
            ),
        ],
    },
]


def build_pptx() -> int:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    def rgb(c):
        return RGBColor(*c)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    sw = prs.slide_width

    def textbox(slide, left, top, width, height):
        tf = slide.shapes.add_textbox(left, top, width, height).text_frame
        tf.word_wrap = True
        return tf

    def header(slide, title, idx):
        bar = slide.shapes.add_shape(1, 0, 0, sw, Inches(0.95))
        bar.fill.solid()
        bar.fill.fore_color.rgb = rgb(NAVY)
        bar.line.fill.background()
        bar.shadow.inherit = False
        bar.text_frame.margin_left = Inches(0.4)
        r = bar.text_frame.paragraphs[0].add_run()
        r.text = title
        r.font.size = Pt(25)
        r.font.bold = True
        r.font.color.rgb = rgb(WHITE)
        pn = textbox(slide, Inches(12.5), Inches(7.05), Inches(0.7), Inches(0.4))
        pr = pn.paragraphs[0].add_run()
        pr.text = str(idx)
        pr.font.size = Pt(11)
        pr.font.color.rgb = rgb(GREY)

    for idx, s in enumerate(SLIDES):
        slide = prs.slides.add_slide(blank)
        if s["type"] == "title":
            band = slide.shapes.add_shape(1, 0, Inches(2.3), sw, Inches(1.6))
            band.fill.solid()
            band.fill.fore_color.rgb = rgb(NAVY)
            band.line.fill.background()
            band.shadow.inherit = False
            band.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            r = band.text_frame.paragraphs[0].add_run()
            r.text = s["title"]
            r.font.size = Pt(48)
            r.font.bold = True
            r.font.color.rgb = rgb(WHITE)
            tf = textbox(slide, Inches(0.8), Inches(4.15), Inches(11.7), Inches(1.9))
            for i, line in enumerate(s["subtitle"].split("\n")):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.alignment = PP_ALIGN.CENTER
                rr = p.add_run()
                rr.text = line
                rr.font.size = Pt(18 if i == 0 else 15)
                rr.font.color.rgb = rgb(NAVY if i == 0 else GREY)
                rr.font.bold = i == 0
            tf2 = textbox(slide, Inches(0.8), Inches(6.5), Inches(11.7), Inches(0.7))
            tf2.paragraphs[0].alignment = PP_ALIGN.CENTER
            rr = tf2.paragraphs[0].add_run()
            rr.text = s["footer"]
            rr.font.size = Pt(13)
            rr.font.italic = True
            rr.font.color.rgb = rgb(ACCENT)
            continue

        header(slide, s["title"], idx)

        if s["type"] == "bullets":
            tf = textbox(slide, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.9))
            first = True
            for level, text in s["bullets"]:
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.level = level
                p.space_after = Pt(7)
                lead = "-  " if level == 0 else ".  "
                if level == 0 and ":" in text and text.index(":") < 60:
                    head, rest = text.split(":", 1)
                    r = p.add_run()
                    r.text = lead + head + ":"
                    r.font.bold = True
                    r.font.size = Pt(16)
                    r.font.color.rgb = rgb(NAVY)
                    r2 = p.add_run()
                    r2.text = rest
                    r2.font.size = Pt(16)
                    r2.font.color.rgb = rgb(GREY)
                else:
                    r = p.add_run()
                    r.text = ("   " if level else "") + lead + text
                    r.font.size = Pt(15 if level else 16)
                    r.font.color.rgb = rgb(GREY)

        elif s["type"] == "diagram":
            tf = textbox(slide, Inches(0.6), Inches(1.25), Inches(12.1), Inches(3.9))
            r = tf.paragraphs[0].add_run()
            r.text = s["diagram"]
            r.font.name = "Courier New"
            r.font.size = Pt(13)
            r.font.color.rgb = rgb(NAVY)
            tf2 = textbox(slide, Inches(0.6), Inches(5.4), Inches(12.1), Inches(1.7))
            r = tf2.paragraphs[0].add_run()
            r.text = s["note"]
            r.font.size = Pt(14)
            r.font.color.rgb = rgb(GREY)

        elif s["type"] == "table":
            headers, rows = s["headers"], s["rows"]
            ncols, nrows = len(headers), len(rows) + 1
            top = Inches(1.25)
            height = Inches(0.42) * nrows
            table = slide.shapes.add_table(
                nrows, ncols, Inches(0.5), top, Inches(12.33), height
            ).table
            for c, h in enumerate(headers):
                cell = table.cell(0, c)
                cell.text = h
                rp = cell.text_frame.paragraphs[0].runs[0]
                rp.font.size = Pt(s.get("font", 12))
                rp.font.bold = True
                rp.font.color.rgb = rgb(WHITE)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(NAVY)
            for ri, row in enumerate(rows, start=1):
                for c, val in enumerate(row):
                    cell = table.cell(ri, c)
                    cell.text = val
                    rp = cell.text_frame.paragraphs[0].runs[0]
                    rp.font.size = Pt(s.get("font", 12))
                    if c == 0:
                        rp.font.bold = True
                        rp.font.color.rgb = rgb(NAVY)
                    else:
                        rp.font.color.rgb = rgb(GREY)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = rgb(WHITE if ri % 2 else LIGHT)
            if s.get("note"):
                tf = textbox(
                    slide, Inches(0.5), top + height + Inches(0.15), Inches(12.33), Inches(1.2)
                )
                r = tf.paragraphs[0].add_run()
                r.text = s["note"]
                r.font.size = Pt(12)
                r.font.italic = True
                r.font.color.rgb = rgb(ACCENT)

    prs.save(str(PPTX))
    return len(SLIDES)


def build_pdf() -> int:
    from fpdf import FPDF

    W, H = 338.66, 190.5
    pdf = FPDF(orientation="L", unit="mm", format=(H, W))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)

    def setc(color):
        pdf.set_text_color(*color)

    def header(title, idx):
        pdf.set_fill_color(*NAVY)
        pdf.rect(0, 0, W, 22, "F")
        pdf.set_xy(10, 4)
        pdf.set_font("Helvetica", "B", 19)
        setc(WHITE)
        pdf.multi_cell(W - 20, 8, title)
        pdf.set_xy(W - 18, H - 10)
        pdf.set_font("Helvetica", "", 9)
        setc(GREY)
        pdf.cell(12, 6, str(idx))

    for idx, s in enumerate(SLIDES):
        pdf.add_page()
        if s["type"] == "title":
            pdf.set_fill_color(*NAVY)
            pdf.rect(0, 58, W, 40, "F")
            pdf.set_xy(0, 66)
            pdf.set_font("Helvetica", "B", 40)
            setc(WHITE)
            pdf.cell(W, 24, s["title"], align="C")
            pdf.set_xy(20, 108)
            for i, line in enumerate(s["subtitle"].split("\n")):
                pdf.set_x(20)
                pdf.set_font("Helvetica", "B" if i == 0 else "", 15 if i == 0 else 12)
                setc(NAVY if i == 0 else GREY)
                pdf.multi_cell(W - 40, 8, line, align="C")
            pdf.set_xy(20, 168)
            pdf.set_font("Helvetica", "I", 11)
            setc(ACCENT)
            pdf.multi_cell(W - 40, 6, s["footer"], align="C")
            continue

        header(s["title"], idx)
        y = 30

        if s["type"] == "bullets":
            for level, text in s["bullets"]:
                indent = 12 + level * 10
                pdf.set_xy(indent, y)
                bullet = "- " if level == 0 else ". "
                if level == 0 and ":" in text and text.index(":") < 60:
                    head, rest = text.split(":", 1)
                    pdf.set_font("Helvetica", "B", 12)
                    setc(NAVY)
                    lead_w = pdf.get_string_width(bullet + head + ": ")
                    pdf.cell(lead_w, 6, bullet + head + ":")
                    pdf.set_font("Helvetica", "", 12)
                    setc(GREY)
                    pdf.set_xy(indent + lead_w, y)
                    pdf.multi_cell(W - indent - lead_w - 12, 6, rest)
                else:
                    pdf.set_font("Helvetica", "", 11 if level else 12)
                    setc(GREY)
                    pdf.multi_cell(W - indent - 12, 6, bullet + text)
                y = pdf.get_y() + 2.5

        elif s["type"] == "diagram":
            pdf.set_xy(12, y)
            pdf.set_font("Courier", "", 11)
            setc(NAVY)
            for line in s["diagram"].split("\n"):
                pdf.set_x(12)
                pdf.cell(W - 24, 6, line)
                pdf.ln(6)
            pdf.ln(4)
            pdf.set_x(12)
            pdf.set_font("Helvetica", "", 12)
            setc(GREY)
            pdf.multi_cell(W - 24, 6, s["note"])

        elif s["type"] == "table":
            headers, rows = s["headers"], s["rows"]
            ncols = len(headers)
            if ncols > 2 and "col0" in s:
                c0 = s["col0"]
                rest_w = (W - 20 - c0) / (ncols - 1)
                widths = [c0] + [rest_w] * (ncols - 1)
            else:
                widths = [(W - 20) / ncols] * ncols
            fs = s.get("font", 11)
            rh = 9
            pdf.set_xy(10, y)
            pdf.set_font("Helvetica", "B", fs)
            pdf.set_fill_color(*NAVY)
            setc(WHITE)
            for c, h in enumerate(headers):
                pdf.cell(widths[c], rh, " " + h, border=0, fill=True)
            pdf.ln(rh)
            for ri, row in enumerate(rows):
                pdf.set_x(10)
                pdf.set_fill_color(*(LIGHT if ri % 2 else WHITE))
                for c, val in enumerate(row):
                    if c == 0:
                        pdf.set_font("Helvetica", "B", fs)
                        setc(NAVY)
                    else:
                        pdf.set_font("Helvetica", "", fs)
                        setc(GREY)
                    pdf.cell(widths[c], rh, " " + val, border=0, fill=True)
                pdf.ln(rh)
            if s.get("note"):
                pdf.ln(3)
                pdf.set_x(10)
                pdf.set_font("Helvetica", "I", 10.5)
                setc(ACCENT)
                pdf.multi_cell(W - 20, 5.5, s["note"])

    pdf.output(str(PDF))
    return len(SLIDES)


if __name__ == "__main__":
    n1 = build_pptx()
    n2 = build_pdf()
    print(f"wrote {PPTX} ({n1} slides) and {PDF} ({n2} pages)")
