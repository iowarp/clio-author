"""The verify-work expert: goal-backward check of prose against its plan.

:class:`VerifyWorkExpert` re-expresses the goal-backward verification step of
the JS writing toolkit wtf-p as a Python expert:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (take the claims a section was supposed to make and check the
written prose: was each claim actually made, and is it supported?) is
reproduced; no source code is copied. The intended claims come from a
:class:`~clio_author.experts.write_models.SectionPlan` (reused, not re-modelled)
or an explicit ``claims`` list. The LLM answers per-claim as JSON, parsed with
the reviewer's :func:`~clio_author.experts.reviewer._extract_json_object`, and
the overall VERIFIED/GAPS verdict is derived deterministically.

Like the other experts this one never raises: missing inputs or any failure
produce an error-flagged :class:`AgentOutput` (appended once). The default
:class:`EchoLLMClient` yields no parseable JSON, so the echo path degrades to a
``parse_error`` with ``status="GAPS"`` and no claims -- it never fabricates a
VERIFIED verdict.
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.reviewer import _extract_json_object
from clio_author.experts.verify_models import VerifyResult
from clio_author.experts.write_models import SectionPlan
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

VERIFY_WORK_SYSTEM_PROMPT = (
    "You are the verification expert. You are given the claims a paper section "
    "was supposed to make and the prose that was actually written. For each "
    "intended claim, decide whether the prose actually states it ('made') and "
    "whether the prose supports it with evidence/argument ('supported'). Be "
    "strict and grounded: judge only from the provided prose; do not assume a "
    "claim is supported because it sounds plausible.\n\n"
    "Report the verification as a fenced JSON block:\n"
    "```json\n"
    '{"claims": [{"claim": "<the intended claim>", "made": true, '
    '"supported": false, "evidence": "<quote/where in the prose>", '
    '"gap": "<what is missing if not supported>"}], '
    '"gaps": ["<overall missing piece>"]}\n'
    "```\n"
    "Keep the format precise; the JSON is parsed automatically."
)


class VerifyWorkExpert(BaseAgent):
    """Expert that verifies written prose against the claims it should make."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        """Build a verify-work expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
        """
        super().__init__(
            role="verify_work",
            system_prompt=VERIFY_WORK_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _resolve_claims(payload: dict[str, Any]) -> list[str]:
        """Resolve the intended claims from ``section_plan`` or ``claims``.

        Prefers an explicit ``claims`` list; otherwise pulls the claims out of a
        :class:`SectionPlan` (or its loose-dict form) under ``section_plan``.
        """
        raw_claims = payload.get("claims")
        if isinstance(raw_claims, (list, tuple)):
            claims = [str(c).strip() for c in raw_claims if str(c).strip()]
            if claims:
                return claims

        plan_raw = payload.get("section_plan")
        if plan_raw is not None:
            plan = (
                plan_raw
                if isinstance(plan_raw, SectionPlan)
                else SectionPlan.from_loose_dict(plan_raw)
                if isinstance(plan_raw, dict)
                else None
            )
            if plan is not None:
                return [c for c in plan.claims if c.strip()]
        return []

    @staticmethod
    def _resolve_text(payload: dict[str, Any]) -> str:
        """Resolve the written prose from ``text`` / ``markdown`` / ``draft``."""
        for key in ("text", "markdown", "draft"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw
        return ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Verify the prose in ``task`` against its intended claims. Never raises.

        Reads the intended claims (``section_plan`` or ``claims``) and the written
        prose (``text`` / ``markdown`` / ``draft`` / ``task.description``), asks
        the LLM for a per-claim made/supported judgement as JSON, and parses it via
        :meth:`VerifyResult.from_loose_dict`. The overall ``status``
        (``VERIFIED`` / ``GAPS``) is derived deterministically from the per-claim
        results.

        ``structured`` is the result's ``model_dump()``, ``content`` a one-line
        summary, ``metadata`` carries ``num_claims`` / ``num_gaps`` / ``status``.
        With no parseable JSON (e.g. the echo client) the output is
        ``parse_error``-flagged with ``status="GAPS"`` and empty claims -- it never
        fabricates a VERIFIED verdict. Missing claims or prose yields an
        error-flagged output.
        """
        try:
            payload = task.payload
            claims = self._resolve_claims(payload)
            if not claims:
                return self._error(session, "no 'claims'/'section_plan' claims provided")
            text = self._resolve_text(payload)
            if not text.strip():
                return self._error(session, "no 'text'/'markdown'/'draft' prose provided")

            messages = self._build_messages(claims, text)
            raw = self.llm.complete(messages)

            parsed = _extract_json_object(raw)
            if parsed is None:
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=VerifyResult(status="GAPS").model_dump(),
                    metadata={
                        "num_claims": 0,
                        "num_gaps": 0,
                        "status": "GAPS",
                        "parse_error": "no parseable JSON object in LLM response",
                    },
                )
                session.add(output)
                return output

            result = VerifyResult.from_loose_dict(parsed)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        content = _render_summary(result)
        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=result.model_dump(),
            metadata={
                "num_claims": len(result.claims),
                "num_gaps": len(result.gaps),
                "status": result.status,
            },
        )
        session.add(output)
        return output

    def _build_messages(self, claims: list[str], text: str) -> list[Message]:
        claims_block = "\n".join(f"{i}. {claim}" for i, claim in enumerate(claims, start=1))
        user = (
            "Intended claims this section was supposed to make:\n"
            f"{claims_block}\n\n"
            "The prose that was actually written:\n"
            f"```\n{text}\n```\n\n"
            "Report the per-claim verification now in the required JSON format."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=user),
        ]


def _render_summary(result: VerifyResult) -> str:
    """Render a one-line human summary of a verification result."""
    made = sum(1 for c in result.claims if c.made)
    supported = sum(1 for c in result.claims if c.made and c.supported)
    head = (
        f"Verification: {result.status}. "
        f"{supported}/{len(result.claims)} claim(s) made and supported "
        f"({made} made), {len(result.gaps)} gap(s)."
    )
    return head


__all__ = ["VerifyWorkExpert", "VERIFY_WORK_SYSTEM_PROMPT"]
