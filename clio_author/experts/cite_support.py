"""The cite-support expert: does the cited source actually support the claim?

``cite`` verifies a citation *exists* (the title resolves to a real paper) and
``check_refs`` verifies the ``\\cite{key}`` resolves to a bibliography entry, but
neither checks the thing that matters most for integrity: **does the cited paper
actually say what the sentence attributes to it?** That is *claim-to-source
faithfulness*, and this expert is the missing rung.

For each ``<claim sentence> \\cite{key}`` pair in the prose it gathers the cited
work's text and asks the model to classify the relationship:

* **supported** — the source clearly substantiates the claim,
* **partial** — partly supported / weaker than stated,
* **unsupported** — the source does not establish the claim,
* **contradicted** — the source says the opposite.

Two evidence tiers (``mode``):

* ``"abstract"`` (default, cheap) — judge the claim against the cited paper's
  **abstract**, which ``cite`` already fetches. Absence from an abstract is a weak
  signal (most claims are supported by a paper's body), so an unsupported verdict
  here is reported as *not found in the abstract*, not a hard failure.
* ``"deep"`` (opt-in, strong) — judge against the cited paper's **full text**.
  The full text is supplied by an injected ``full_text_resolver`` (the network
  seam: e.g. ingest the cited arXiv id and return its Markdown); when a source
  cannot be fetched the pair falls back to the abstract.

Like the other experts this one **never raises**: missing inputs or any failure
produce an error-flagged :class:`AgentOutput` (appended once). The default
:class:`EchoLLMClient` yields no parseable JSON, so the echo path degrades to
``verdict="unknown"`` per pair and a ``None`` integrity — it never fabricates a
``supported`` verdict.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from clio_author.experts.bib_utils import extract_cite_keys
from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.tools.files import FileToolError, SafeFiles

# A resolver maps a citation key + its normalized record to the cited paper's
# full text (or None when it cannot be fetched). It is the network seam for
# ``mode="deep"`` and is injected (kept out of this pure expert) so the module
# stays hermetic and testable.
FullTextResolver = Callable[[str, dict[str, Any]], str | None]

CITE_SUPPORT_SYSTEM_PROMPT = (
    "You are the citation-faithfulness checker. You are given a CLAIM sentence "
    "from a paper and the SOURCE text of the work that sentence cites. Decide "
    "whether the source actually supports the claim. Judge ONLY from the source "
    "text provided; never assume support because the claim sounds plausible.\n\n"
    "Verdicts:\n"
    "- supported: the source clearly substantiates the claim.\n"
    "- partial: the source partly supports it, or it is weaker/narrower than stated.\n"
    "- unsupported: the source does not establish the claim.\n"
    "- contradicted: the source states the opposite of the claim.\n\n"
    "Respond with a single fenced JSON block:\n"
    "```json\n"
    '{"verdict": "supported", "evidence": "<short quote from the SOURCE>", '
    '"rationale": "<one sentence>"}\n'
    "```\n"
    "Keep the format precise; the JSON is parsed automatically."
)

# Per-verdict credit for the support-integrity score. ``unknown`` / ``no_source``
# are excluded from the denominator (we could not judge), not scored as failures.
_VERDICT_WEIGHT: dict[str, float] = {
    "supported": 1.0,
    "partial": 0.5,
    "unsupported": 0.0,
    "contradicted": 0.0,
}
_VALID_VERDICTS = frozenset(_VERDICT_WEIGHT) | {"unknown", "no_source"}

# Sentence segmentation that keeps the claim text around each citation small.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_CITE_TOKEN = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{[^}]*\}")


class ClaimCitation(BaseModel):
    """One ``claim sentence`` paired with one cited key it should be grounded in."""

    claim: str
    key: str


class ClaimSupport(BaseModel):
    """The faithfulness verdict for one claim-citation pair."""

    claim: str
    key: str
    verdict: str = "unknown"
    evidence: str = ""
    rationale: str = ""
    source_kind: str = "none"  # "full_text" | "abstract" | "none"


class CiteSupportResult(BaseModel):
    """Aggregate claim-to-source faithfulness over a manuscript."""

    items: list[ClaimSupport] = Field(default_factory=list)
    support_integrity: float | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    mode: str = "abstract"


def extract_claim_citations(prose: str, *, max_pairs: int = 200) -> list[ClaimCitation]:
    """Pull ``(claim sentence, cited key)`` pairs out of ``prose``.

    Each sentence containing one or more ``\\cite{...}`` keys becomes one pair per
    cited key; the ``\\cite{}`` tokens are stripped from the claim text so the
    model judges the assertion, not the citation markup. Capped at ``max_pairs``.
    """
    pairs: list[ClaimCitation] = []
    for sentence in _SENT_BOUNDARY.split(prose):
        seg = sentence.strip()
        if not seg:
            continue
        keys = extract_cite_keys(seg)
        if not keys:
            continue
        claim = _CITE_TOKEN.sub("", seg)
        claim = re.sub(r"\s+", " ", claim).strip(" ,;()[]").strip()
        if not claim:
            continue
        for key in sorted(keys):
            pairs.append(ClaimCitation(claim=claim, key=key))
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def _normalize_citations(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalize a citations input into ``{key: {title, abstract, source, record}}``.

    Accepts ``cite``'s ``verified`` items (``{citation_key, record:{title,
    abstract, external_ids, ...}}``) or a flat list/dict of
    ``{key|citation_key, title, abstract, source}``.
    """
    out: dict[str, dict[str, Any]] = {}
    # Unwrap cite's saved output: the full `{action, structured:{verified:[...]}}`
    # blob, or just its `structured`, both nest the list under `verified`.
    if isinstance(raw, dict):
        if isinstance(raw.get("structured"), dict) and "verified" in raw["structured"]:
            raw = raw["structured"]["verified"]
        elif "verified" in raw:
            raw = raw["verified"]

    items: list[Any]
    if isinstance(raw, dict):
        # already a {key: entry} map, or a single entry
        if "citation_key" in raw or "key" in raw:
            items = [raw]
        else:
            items = [{"key": k, **(v if isinstance(v, dict) else {})} for k, v in raw.items()]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return out

    for item in items:
        if not isinstance(item, dict):
            continue
        rec = item.get("record")
        record: dict[str, Any] = rec if isinstance(rec, dict) else item
        key = str(item.get("citation_key") or item.get("key") or "").strip()
        if not key:
            continue
        out[key] = {
            "title": str(record.get("title") or item.get("title") or ""),
            "abstract": str(record.get("abstract") or item.get("abstract") or ""),
            "source": item.get("source") or record.get("source"),
            "record": record,
        }
    return out


class CiteSupportExpert(BaseAgent):
    """Expert that checks whether cited sources actually support the claims."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        full_text_resolver: FullTextResolver | None = None,
    ) -> None:
        """Build a cite-support expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            full_text_resolver: Optional callable used only in ``mode="deep"`` to
                fetch a cited paper's full text (the network seam). When ``None``
                or it returns ``None``, deep mode falls back to the abstract.
        """
        super().__init__(
            role="cite_support",
            system_prompt=CITE_SUPPORT_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._resolver = full_text_resolver

    @staticmethod
    def _prose(payload: dict[str, Any]) -> str:
        for key in ("markdown", "text", "draft"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw
        sections = payload.get("sections")
        if isinstance(sections, (list, tuple)):
            parts: list[str] = []
            for s in sections:
                if isinstance(s, dict):
                    body = str(s.get("draft") or s.get("text") or s.get("content") or "")
                    if body.strip():
                        parts.append(body)
                elif isinstance(s, str) and s.strip():
                    parts.append(s)
            return "\n\n".join(parts)
        return ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Check claim-to-source faithfulness for every cited claim. Never raises.

        Reads the prose (``markdown`` / ``text`` / ``sections``) and the cited
        works' metadata (``citations`` — ``cite``'s ``verified`` output, or a flat
        list with ``abstract``/``source``). ``mode`` is ``"abstract"`` (default)
        or ``"deep"``. Returns a :class:`CiteSupportResult` in ``structured`` plus
        a headline ``support_integrity`` and per-verdict ``counts`` in
        ``metadata``; writes ``cite_support.json`` / ``cite_support.md`` under
        ``out_dir`` when given.
        """
        try:
            payload = task.payload
            prose = self._prose(payload)
            if not prose.strip():
                return self._error(session, "no 'markdown'/'text'/'sections' prose provided")
            citations = _normalize_citations(payload.get("citations"))
            if not citations:
                return self._error(
                    session, "no 'citations' provided (cite's verified output or a list)"
                )
            mode = "deep" if str(payload.get("mode") or "").lower() == "deep" else "abstract"
            pairs = extract_claim_citations(prose)
            if not pairs:
                return self._error(session, "no '\\cite{}' citations found in the prose")

            items = [self._judge(pair, citations, mode) for pair in pairs]
            result = _aggregate(items, mode)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        summary = _render_summary(result)
        wrote = _maybe_write(task.payload, result, summary)
        output = AgentOutput(
            agent=self.name,
            content=summary,
            structured=result.model_dump(),
            metadata={
                "support_integrity": result.support_integrity,
                "counts": result.counts,
                "num_pairs": len(result.items),
                "mode": mode,
                "wrote": wrote,
            },
        )
        session.add(output)
        return output

    def _source_text(self, key: str, entry: dict[str, Any], mode: str) -> tuple[str, str]:
        """Return ``(source_text, source_kind)`` for a cited key.

        Deep mode first tries the injected resolver (full text) and falls back to
        the abstract; abstract mode uses the abstract directly. ``source_kind`` is
        ``"full_text"`` / ``"abstract"`` / ``"none"``.
        """
        if mode == "deep" and self._resolver is not None:
            try:
                full = self._resolver(key, entry)
            except Exception:  # noqa: BLE001 - resolver failure -> fall back to abstract
                full = None
            if full and full.strip():
                return full.strip(), "full_text"
        abstract = str(entry.get("abstract") or "").strip()
        if abstract:
            return abstract, "abstract"
        return "", "none"

    def _judge(
        self, pair: ClaimCitation, citations: dict[str, dict[str, Any]], mode: str
    ) -> ClaimSupport:
        """Classify one claim-citation pair against its source (LLM call)."""
        entry = citations.get(pair.key)
        if entry is None:
            return ClaimSupport(
                claim=pair.claim, key=pair.key, verdict="no_source", source_kind="none"
            )
        source_text, source_kind = self._source_text(pair.key, entry, mode)
        if source_kind == "none":
            return ClaimSupport(
                claim=pair.claim, key=pair.key, verdict="no_source", source_kind="none"
            )

        messages = self._build_messages(pair, entry, source_text, source_kind)
        parsed = _extract_json_object(self.llm.complete(messages))
        if not isinstance(parsed, dict):
            return ClaimSupport(
                claim=pair.claim, key=pair.key, verdict="unknown", source_kind=source_kind
            )
        verdict = str(parsed.get("verdict") or "unknown").strip().lower()
        if verdict not in _VALID_VERDICTS:
            verdict = "unknown"
        return ClaimSupport(
            claim=pair.claim,
            key=pair.key,
            verdict=verdict,
            evidence=str(parsed.get("evidence") or "")[:600],
            rationale=str(parsed.get("rationale") or "")[:600],
            source_kind=source_kind,
        )

    def _build_messages(
        self,
        pair: ClaimCitation,
        entry: dict[str, Any],
        source_text: str,
        source_kind: str,
    ) -> list[Message]:
        title = entry.get("title") or pair.key
        kind = "FULL TEXT" if source_kind == "full_text" else "ABSTRACT"
        user = (
            f"CLAIM (cites {pair.key}):\n{pair.claim}\n\n"
            f'SOURCE — {kind} of "{title}":\n```\n{source_text[:8000]}\n```\n\n'
            "Classify whether the source supports the claim, in the required JSON format."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=user),
        ]


def _aggregate(items: list[ClaimSupport], mode: str) -> CiteSupportResult:
    """Roll per-pair verdicts up into counts + a support-integrity score."""
    counts: dict[str, int] = {v: 0 for v in sorted(_VALID_VERDICTS)}
    weighted = 0.0
    scored = 0
    for item in items:
        counts[item.verdict] = counts.get(item.verdict, 0) + 1
        if item.verdict in _VERDICT_WEIGHT:
            weighted += _VERDICT_WEIGHT[item.verdict]
            scored += 1
    integrity = (weighted / scored) if scored else None
    return CiteSupportResult(items=items, support_integrity=integrity, counts=counts, mode=mode)


def _render_summary(result: CiteSupportResult) -> str:
    c = result.counts
    pct = "n/a" if result.support_integrity is None else f"{round(result.support_integrity * 100)}%"
    return (
        f"Citation support ({result.mode}): {pct} of cited claims substantiated by their source "
        f"[{c.get('supported', 0)} supported, {c.get('partial', 0)} partial, "
        f"{c.get('unsupported', 0)} unsupported, {c.get('contradicted', 0)} contradicted, "
        f"{c.get('no_source', 0)} no-source, {c.get('unknown', 0)} unjudged]."
    )


def render_cite_support_markdown(result: CiteSupportResult, summary: str) -> str:
    """Render the cite-support result as a short Markdown report."""
    lines = ["# Citation-support report", "", summary, ""]
    if result.mode == "abstract":
        lines += [
            "_Mode: abstract — an `unsupported` verdict means *not found in the cited "
            "abstract*, which is a weak signal; re-run with deep mode for full-text checking._",
            "",
        ]
    for item in result.items:
        flag = {"supported": "✓", "partial": "~", "unsupported": "✗", "contradicted": "⚠"}.get(
            item.verdict, "?"
        )
        lines.append(f"- {flag} **{item.verdict}** `\\cite{{{item.key}}}` ({item.source_kind})")
        lines.append(f"  - claim: {item.claim}")
        if item.evidence:
            lines.append(f"  - evidence: {item.evidence}")
    return "\n".join(lines) + "\n"


def _maybe_write(payload: dict[str, Any], result: CiteSupportResult, summary: str) -> list[str]:
    out_dir = payload.get("out_dir")
    if not out_dir:
        return []
    files = SafeFiles(Path(str(out_dir)))
    try:
        files.root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    wrote: list[str] = []
    for name, content in (
        ("cite_support.json", json.dumps(result.model_dump(), indent=2)),
        ("cite_support.md", render_cite_support_markdown(result, summary)),
    ):
        try:
            wrote.append(str(files.write_new(name, content)))
        except FileToolError:
            continue
    return wrote


__all__ = [
    "CiteSupportExpert",
    "CiteSupportResult",
    "ClaimSupport",
    "ClaimCitation",
    "extract_claim_citations",
    "render_cite_support_markdown",
    "CITE_SUPPORT_SYSTEM_PROMPT",
]
