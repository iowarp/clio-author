# Changelog

All notable changes to clio-parser are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.1]

### Added
- **Citation backend auto-wiring.** The CLI now selects the citation backend via the `CLIO_SCHOLAR`
  environment variable (`auto` (default) = real Semantic Scholar, reading `SEMANTIC_SCHOLAR_API_KEY`;
  `off`/`none` = disabled). `resolve_scholar_client()` makes `clio-parser cite` work out of the box.
- **`CHANGELOG.md`.**

### Changed
- **Pinned `torch`/`torchvision` to the CPU index** in `pyproject.toml` (`[tool.uv.sources]` +
  `[[tool.uv.index]] pytorch-cpu`) and regenerated the lock, so `uv sync --all-extras` resolves
  matching CPU wheels and avoids the `torchvision::nms` mismatch. GPU users can override the index.

## [0.2.0]

### Added
- **Visible ingest output.** `clio-parser ingest <id|url|title|topic|path>` writes a browsable
  `./clio-out/<slug>/` containing `paper.md`, `blocks.json`, and `img/figureN.png`. `IngestorExpert`
  now honors `out_dir` from the task payload and persists the Markdown + memory blocks.
- **Comprehensive `README.md`** + reconciled `docs/USAGE.md`: the 11-action catalog, every optional
  extra, model/env configuration, output locations, testing, CI, and troubleshooting.

### Changed
- Package version bumped to match the release line.

## [0.1.2]

### Added
- **GitHub Actions CI** — ruff (lint + format), mypy, and the hermetic pytest suite on every PR and
  push to `main`.
- **Ingest by paper title or topic** — `search_arxiv_pdf` / `resolve_source` resolve a title (exact
  match first) or topic to an arXiv PDF via the arXiv API, in addition to arXiv id / URL / local PDF.

## [0.1.1]

### Added
- **CLI real-provider selection** via `CLIO_LLM` (`echo` (default, offline) | `claude` | `codex` |
  `ollama`; model via `CLIO_LLM_MODEL`, Ollama URL via `CLIO_OLLAMA_URL`). Ready-made `LLMClient`
  providers in `clio_parser.llm.providers`.

## [0.1.0]

### Added
- Initial release: a standalone, pure-Python multi-agent harness for processing, reviewing, and
  writing scientific papers (roadmap milestones M0–M8).
- **Harness** — `BaseAgent`/`AgentProtocol`/`Engine` + patterns (`Sequential`, `Parallel`,
  `CriticRefine`), `SessionContext`, Pydantic types; pluggable `LLMClient` (`EchoLLMClient` default).
- **Ingest** — Docling + PyMuPDF extraction with a deterministic academic post-process pass
  (sections, citations, equations, figures, bibliography, tables, cleanup) → memory blocks.
- **Retrieval** — `HashingEmbedder` + in-memory retriever (hermetic) and an optional
  SentenceTransformer + LanceDB backend; Semantic Scholar citation verification (suggestions only).
- **Experts** — ingestor, paper_qa, citation, reviewer, meta_reviewer, writer, editor, figure_agent.
- **Tools** — `SafeFiles` sandboxed read/write/edit; `eval/report.py` metrics.
- **Integration** — `ClioParserAgent` routing, `ClioParserSubagent` adapter, and the `clio-parser` CLI.
- BSD-3-Clause. Adapted from paper-to-md (MIT), PaperBanana/PaperOrchestra (Apache-2.0); protoneo
  concepts re-implemented (not copied). ~300 hermetic tests.

[0.2.1]: https://github.com/SIslamMun/clio-Parser/releases/tag/v0.2.1
[0.2.0]: https://github.com/SIslamMun/clio-Parser/releases/tag/v0.2.0
[0.1.2]: https://github.com/SIslamMun/clio-Parser/releases/tag/v0.1.2
[0.1.1]: https://github.com/SIslamMun/clio-Parser/releases/tag/v0.1.1
[0.1.0]: https://github.com/SIslamMun/clio-Parser/releases/tag/v0.1.0
