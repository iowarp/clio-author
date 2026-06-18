"""The coherence expert: cross-section consistency checking of a manuscript.

:class:`CoherenceExpert` is given several manuscript sections and asks the LLM to
flag inconsistencies *across* them: terminology drift, contradictions,
undefined-term usage, duplication, and broken narrative flow. The response is
parsed into a structured issue list using the same tolerant JSON extractor as the
reviewer (:func:`~clio_author.experts.reviewer._extract_json_object`); no new
parser is introduced.

Like the reviewer, this expert never raises: missing input produces an
error-flagged :class:`AgentOutput`, and an LLM response that contains no
parseable JSON produces a ``parse_error``-flagged output (the default
:class:`EchoLLMClient` naturally exercises that branch, keeping the harness
offline).
"""

from __future__ import annotations

import re
from typing import Any

from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.tools.files import SafeFiles

COHERENCE_SYSTEM_PROMPT = (
    "You are the cross-section consistency expert. You compare the sections of a "
    "manuscript and flag inconsistencies between them: terminology drift (the same "
    "concept named differently across sections), contradictions (claims that "
    "conflict), undefined-term usage (a term used before it is defined), "
    "duplication (the same material repeated), and broken narrative flow.\n\n"
    "Respond with a brief THOUGHT, then the report as a fenced JSON block.\n\n"
    "THOUGHT:\n<your concise, manuscript-specific reasoning>\n\n"
    "REPORT JSON:\n```json\n"
    '{"issues": [{"kind": "terminology|contradiction|undefined|duplication|flow", '
    '"sections": ["<section title>", ...], "detail": "<what is wrong and where>"}], '
    '"summary": "<one-line overall assessment>"}\n'
    "```\n"
    "The JSON is parsed automatically, so keep the format precise."
)


class CoherenceExpert(BaseAgent):
    """Expert that flags cross-section consistency issues across a manuscript."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build a coherence expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles` (unused today; accepted for a uniform
                expert constructor shape).
        """
        self.files = files
        super().__init__(
            role="coherence",
            system_prompt=COHERENCE_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_sections(payload: dict[str, Any], task: Task) -> list[dict[str, str]]:
        """Resolve sections from ``payload["sections"]`` / ``["markdown"]`` / text.

        ``sections`` is compose's list of ``{title, draft}`` (or
        ``{title, section_path, draft}``); ``markdown`` is split on ``^## ``
        headings into ``{title, draft}`` pairs; otherwise a single
        ``payload["text"]`` / ``task.description`` becomes one untitled section.
        """
        raw = payload.get("sections")
        if isinstance(raw, list):
            sections: list[dict[str, str]] = []
            for entry in raw:
                if isinstance(entry, dict):
                    title = str(entry.get("title") or entry.get("section_path") or "Section")
                    draft = str(entry.get("draft") or "")
                    sections.append({"title": title, "draft": draft})
            if sections:
                return sections

        markdown = payload.get("markdown")
        if markdown:
            split = _split_markdown_sections(str(markdown))
            if split:
                return split

        text = payload.get("text") or task.description
        if text:
            return [{"title": "Section", "draft": str(text)}]
        return []

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Check cross-section coherence for the sections in ``task``. Never raises.

        Resolves sections (``payload["sections"]`` / ``["markdown"]`` /
        ``["text"]`` / ``task.description``), lays them out as ``### title`` blocks,
        calls the LLM, and parses a ```json``` issue report via the reuse of
        :func:`~clio_author.experts.reviewer._extract_json_object`.

        On success ``structured`` is the parsed report (``issues`` + ``summary``),
        ``metadata`` carries ``num_sections`` / ``num_issues``, and ``content`` is a
        human summary. On parse failure (echo / non-JSON) ``structured`` is ``None``
        and ``metadata`` carries ``parse_error``. With ``format="prose"`` the issues
        are rendered as a readable list in ``content`` and ``structured`` is ``None``.
        Missing sections produce an error-flagged output.
        """
        try:
            payload = task.payload
            sections = self._coerce_sections(payload, task)
            if not sections:
                return self._error(
                    session, "no sections to check ('sections'/'markdown'/'text' not provided)"
                )

            fmt = str(payload.get("format", "structured")).lower()
            laid_out = "\n\n".join(f"### {s['title']}\n{s['draft']}" for s in sections)
            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=(
                        "Check the following manuscript sections for cross-section "
                        f"inconsistencies and report them.\n\n{laid_out}"
                    ),
                ),
            ]
            raw = self.llm.complete(messages)

            parsed = _extract_json_object(raw)
            if parsed is None:
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=None,
                    metadata={
                        "num_sections": len(sections),
                        "parse_error": "no parseable JSON object in LLM response",
                    },
                )
                session.add(output)
                return output

            raw_issues = parsed.get("issues")
            issues: list[Any] = raw_issues if isinstance(raw_issues, list) else []
            summary = str(parsed.get("summary") or "")

            if fmt == "prose":
                output = AgentOutput(
                    agent=self.name,
                    content=_render_issues_prose(issues, summary),
                    structured=None,
                    metadata={
                        "num_sections": len(sections),
                        "num_issues": len(issues),
                        "format": "prose",
                    },
                )
                session.add(output)
                return output
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=_render_issues_prose(issues, summary),
            structured=parsed,
            metadata={"num_sections": len(sections), "num_issues": len(issues)},
        )
        session.add(output)
        return output


def _split_markdown_sections(markdown: str) -> list[dict[str, str]]:
    """Split ``markdown`` on ``^## `` headings into ``{title, draft}`` pairs.

    Content before the first ``## `` heading (e.g. a ``# Title`` block) is
    ignored; each ``## `` heading starts a new section whose body runs to the next
    ``## `` heading.
    """
    sections: list[dict[str, str]] = []
    title: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(?!#)(.*)$", line)
        if match:
            if title is not None:
                sections.append({"title": title, "draft": "\n".join(body).strip()})
            title = match.group(1).strip()
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append({"title": title, "draft": "\n".join(body).strip()})
    return sections


def _render_issues_prose(issues: list[Any], summary: str) -> str:
    """Render a parsed issue list as a human-readable summary string."""
    head = f"Found {len(issues)} coherence issue(s)."
    if summary:
        head = f"{head} {summary}"
    if not issues:
        return head
    lines = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        kind = str(issue.get("kind") or "issue")
        secs = issue.get("sections")
        where = ", ".join(str(s) for s in secs) if isinstance(secs, list) else ""
        detail = str(issue.get("detail") or "")
        prefix = f"[{kind}] " + (f"({where}) " if where else "")
        lines.append(f"- {prefix}{detail}".rstrip())
    return head + "\n" + "\n".join(lines)


__all__ = ["CoherenceExpert", "COHERENCE_SYSTEM_PROMPT"]
