"""The polish expert: standalone prose-polishing of an existing passage.

:class:`PolishExpert` takes a piece of existing academic prose and asks the LLM
to improve its clarity, flow, and academic voice *without changing meaning* and
*without removing any citation placeholder* (``\\cite{key}``) or figure
reference. An optional ``voice`` directive (e.g. "concise" / "formal") is woven
into the prompt. The full polished text is returned.

Like :class:`~clio_parser.experts.editor.EditorExpert`, this is a one-shot step,
not a producer in a refine loop. When a harness file ``target`` and a
:class:`SafeFiles` are given, the polished text is applied to that file via
``apply_edit`` (whole-body replace); otherwise it is returned in ``structured``.
It never raises: missing input or any failure produces an error-flagged
:class:`AgentOutput` (appended once). The default :class:`EchoLLMClient` keeps it
offline.
"""

from __future__ import annotations

from typing import Any

from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.llm.client import EchoLLMClient, LLMClient
from clio_parser.tools.files import FileToolError, SafeFiles

POLISH_SYSTEM_PROMPT = (
    "You are the prose-polishing expert. You improve the clarity, flow, and "
    "academic voice of existing scientific prose. Tighten wording, fix awkward "
    "phrasing, and strengthen the academic register, but DO NOT change the "
    "meaning, remove or weaken any claim, or invent new facts. Preserve every "
    "citation placeholder (\\cite{key}) and every figure reference exactly as "
    "written. Return the full polished text and nothing else."
)


class PolishExpert(BaseAgent):
    """Expert that polishes existing prose without changing its meaning."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build a polish expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles`; when given with ``payload["target"]``
                the polished text is applied to that file (whole-body replace).
        """
        self.files = files
        super().__init__(
            role="polish",
            system_prompt=POLISH_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    def _resolve_prose(self, payload: dict[str, Any], task: Task, session: SessionContext) -> str:
        """Read the prose to polish from payload / session / task description."""
        prose = (
            payload.get("text")
            or payload.get("draft")
            or session.data.get("draft")
            or task.description
        )
        return str(prose) if prose else ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Polish the prose in ``task`` and return the polished text. Never raises.

        Reads prose from ``payload["text"]`` / ``payload["draft"]`` /
        ``session.data["draft"]`` / ``task.description`` and an optional
        ``payload["voice"]`` directive. Calls the LLM for a polished revision,
        applies it via ``apply_edit`` when a file ``target`` is given, and returns
        one output whose ``structured`` carries the polished text. Missing prose
        produces an error-flagged output.
        """
        try:
            payload = task.payload
            prose = self._resolve_prose(payload, task, session)
            if not prose:
                return self._error(session, "no prose to polish ('text'/'draft' not provided)")

            voice = payload.get("voice")
            voice_str = str(voice) if voice else None
            voice_clause = (
                f"\n\nAim for a {voice_str} voice in the polished text." if voice_str else ""
            )

            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=(
                        f"Polish the following passage. Preserve all citation and figure "
                        f"placeholders and every claim; do not change the meaning."
                        f"{voice_clause}\n\nPassage:\n{prose}\n\nReturn the full polished text."
                    ),
                ),
            ]
            polished = self.llm.complete(messages)

            target = payload.get("target")
            wrote: list[str] = []
            if self.files is not None and target:
                # Whole-body replace assumes ``prose`` matches the file on disk;
                # an out-of-band write surfaces EditNotApplicableError (flagged).
                path = self.files.apply_edit(str(target), prose, polished, count=1)
                wrote.append(str(path))
        except FileToolError as exc:
            return self._error(session, f"file tool error: {exc}")
        except Exception as exc:  # noqa: BLE001 - never raise; flag on the output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=polished,
            structured={"polished": polished, "voice": voice_str},
            metadata={"wrote": wrote},
        )
        session.add(output)
        return output


__all__ = ["PolishExpert", "POLISH_SYSTEM_PROMPT"]
