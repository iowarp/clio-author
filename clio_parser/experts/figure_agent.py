"""The figure agent: describe/caption figures and generate matplotlib plot code.

:class:`FigureAgentExpert` has two modes, keyed on ``task.payload["mode"]``:

* **describe** -- fill the deferred :attr:`FigureInfo.description` slot. For each
  figure lacking a description, it prompts the LLM with the figure's caption and
  any surrounding context, then returns the updated :class:`MemoryBlocks` plus a
  per-figure :class:`FigureDescription`.
* **plot** -- generate **matplotlib code** (text) from a :class:`PlotSpec`. With
  ``session.data["critic_feedback"]`` present it revises the previous draft
  (threaded via ``session.data["draft"]``); otherwise it drafts. The generated
  code is extracted from a ```python``` fence and, when ``files`` +
  ``payload["out_path"]`` are given, written under the ``SafeFiles`` root. The
  agent's ``content`` carries the code so it can be a :class:`CriticRefine`
  producer (matching the writer's decision in M5).

The Retriever -> Planner -> Stylist -> Visualizer <-> Critic flow and the
"No changes needed." critic short-circuit are a behavior reference from PaperBanana
/ papervizagent (https://github.com/JoshuaChou2018/papervizagent, Apache-2.0); no
source code is copied and the existing :class:`CriticRefine` pattern is reused for
the visualizer/critic loop.

**Safety:** the default path NEVER executes LLM-generated code -- it only produces
and writes the code text. Actual rendering lives in the module-level, gated
:func:`render_plot_code` helper, which runs code in a subprocess with the ``Agg``
backend and a timeout, and is only ever called from gated/live tests. matplotlib is
an optional ``viz`` extra and is never imported at module load.

Like the other experts this one never raises: missing inputs, a file refusal, or
any failure produce an error-flagged :class:`AgentOutput` (appended once). The
default :class:`EchoLLMClient` keeps it offline.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from clio_parser.experts.figure_models import FigureArtifact, FigureDescription, PlotSpec
from clio_parser.harness.base import BaseAgent
from clio_parser.harness.patterns import CriticRefine
from clio_parser.harness.protocol import AgentProtocol
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.ingest.blocks import FigureInfo, MemoryBlocks
from clio_parser.llm.client import EchoLLMClient, LLMClient
from clio_parser.tools.files import FileToolError, SafeFiles

FIGURE_SYSTEM_PROMPT = (
    "You are the figure expert. You either describe scientific figures for "
    "selective context injection, or generate Python matplotlib code that draws a "
    "requested figure. When generating code: use matplotlib with the 'Agg' "
    "backend, save the figure to the given output file, make NO network calls, and "
    "NEVER call plt.show(). Return the code as a single ```python``` fenced block."
)


class PlotCodeRenderError(RuntimeError):
    """Raised by :func:`render_plot_code` when rendering cannot complete.

    Covers a missing matplotlib (``viz`` extra not installed), a subprocess that
    exits non-zero, a timeout, or a missing output file. Never raised from the
    default expert path -- only from the gated :func:`render_plot_code` helper.
    """


class FigureAgentExpert(BaseAgent):
    """Expert that describes figures and generates matplotlib plot code."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build a figure agent.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles`; when given together with
                ``payload["out_path"]`` the generated plot code is written under
                its root.
        """
        self.files = files
        super().__init__(
            role="figure",
            system_prompt=FIGURE_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Dispatch on ``payload["mode"]`` (``"describe"`` default) and run. Never raises.

        Returns exactly one :class:`AgentOutput`, appended once to the session.
        Missing inputs or a file refusal produce an error-flagged output.
        """
        try:
            mode = str(task.payload.get("mode", "describe")).strip().lower()
            if mode == "plot":
                return self._run_plot(task, session)
            return self._run_describe(task, session)
        except FileToolError as exc:
            return self._error(session, f"file tool error: {exc}")
        except Exception as exc:  # noqa: BLE001 - never raise; flag on the output
            return self._error(session, str(exc))

    # --- describe mode -------------------------------------------------------
    @staticmethod
    def _coerce_figures(payload: dict[str, Any]) -> tuple[MemoryBlocks | None, list[FigureInfo]]:
        """Resolve the figures to describe from ``payload``.

        Prefers ``payload["blocks"]`` (a :class:`MemoryBlocks` or its dump), whose
        ``figures`` are returned (and the container is returned for round-tripping
        the updated dump). Falls back to ``payload["figures"]`` -- a list of
        :class:`FigureInfo` or loose dicts -- with no container.

        A live :class:`MemoryBlocks` / :class:`FigureInfo` passed by the caller is
        deep-copied before being returned, so describing never mutates the caller's
        objects -- the updates land only on the returned copy / the emitted dump.
        """
        blocks_raw = payload.get("blocks")
        if blocks_raw is not None:
            blocks = (
                blocks_raw.model_copy(deep=True)
                if isinstance(blocks_raw, MemoryBlocks)
                else MemoryBlocks.model_validate(blocks_raw)
            )
            return blocks, blocks.figures

        figures_raw = payload.get("figures")
        if isinstance(figures_raw, (list, tuple)):
            figures = [
                fig.model_copy(deep=True)
                if isinstance(fig, FigureInfo)
                else FigureInfo.model_validate(fig)
                for fig in figures_raw
            ]
            return None, figures
        return None, []

    def _run_describe(self, task: Task, session: SessionContext) -> AgentOutput:
        blocks, figures = self._coerce_figures(task.payload)
        if not figures:
            return self._error(session, "no 'blocks'/'figures' provided")

        context = str(task.payload.get("context", ""))
        described: list[FigureDescription] = []
        num_described = 0
        for figure in figures:
            if figure.description:
                # Already described -- keep it untouched, but still report it.
                described.append(
                    FigureDescription(
                        figure_id=figure.figure_id,
                        description=figure.description,
                        caption=figure.caption,
                    )
                )
                continue
            messages = self._describe_messages(figure, context)
            description = self.llm.complete(messages).strip()
            figure.description = description
            num_described += 1
            described.append(
                FigureDescription(
                    figure_id=figure.figure_id,
                    description=description,
                    caption=figure.caption,
                )
            )

        structured: dict[str, Any] = {
            "descriptions": [desc.model_dump() for desc in described],
        }
        if blocks is not None:
            structured["blocks"] = blocks.model_dump()

        summary = f"Described {num_described} of {len(figures)} figure(s)."
        output = AgentOutput(
            agent=self.name,
            content=summary,
            structured=structured,
            metadata={"mode": "describe", "num_described": num_described},
        )
        session.add(output)
        return output

    def _describe_messages(self, figure: FigureInfo, context: str) -> list[Message]:
        parts = [f"Describe Figure {figure.figure_id} for a scientific reader."]
        if figure.caption:
            parts.append(f"Caption:\n{figure.caption}")
        if figure.classification:
            parts.append(f"Figure type: {figure.classification}")
        if context:
            parts.append(f"Surrounding context:\n{context}")
        parts.append(
            "Write a concise, factual description of what the figure shows. "
            "Do not invent details that are not supported by the caption or context."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]

    # --- plot mode -----------------------------------------------------------
    @staticmethod
    def _coerce_spec(payload: dict[str, Any]) -> PlotSpec | None:
        """Extract a :class:`PlotSpec` from ``payload["spec"]``."""
        raw = payload.get("spec")
        if raw is None:
            return None
        if isinstance(raw, PlotSpec):
            return raw
        if isinstance(raw, dict):
            return PlotSpec.from_loose_dict(raw)
        return None

    def _run_plot(self, task: Task, session: SessionContext) -> AgentOutput:
        payload = task.payload
        spec = self._coerce_spec(payload)
        if spec is None:
            return self._error(session, "no 'spec' provided")

        feedback = session.data.get("critic_feedback")
        out_path = payload.get("out_path")
        out_name = str(out_path) if out_path else "figure.png"

        if feedback:
            current = str(session.data.get("draft", ""))
            messages = self._revise_messages(spec, out_name, current, str(feedback))
            phase = "revise"
        else:
            messages = self._draft_messages(spec, out_name)
            phase = "draft"

        completion = self.llm.complete(messages)
        code = _extract_python_block(completion)
        session.data["draft"] = code

        wrote: list[str] = []
        if self.files is not None and out_path:
            path = self.files.write_new(str(out_path), code)
            wrote.append(str(path))

        artifact = FigureArtifact(kind="plot", code=code)
        output = AgentOutput(
            agent=self.name,
            content=code,
            structured={
                "artifact": artifact.model_dump(),
                "out_path": str(out_path) if out_path else None,
            },
            metadata={"mode": "plot", "phase": phase, "wrote": wrote},
        )
        session.add(output)
        return output

    def _draft_messages(self, spec: PlotSpec, out_name: str) -> list[Message]:
        parts = [f"Generate matplotlib code for a {spec.kind}."]
        parts.append(f"Intent:\n{spec.intent}")
        if spec.data_hint:
            parts.append(f"Data hint:\n{spec.data_hint}")
        if spec.aspect_ratio:
            parts.append(f"Aspect ratio: {spec.aspect_ratio}")
        parts.append(
            "Use matplotlib with the 'Agg' backend, make no network calls, do not "
            f"call plt.show(), and save the figure to {out_name!r}. "
            "Return only a single ```python``` fenced code block."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]

    def _revise_messages(
        self, spec: PlotSpec, out_name: str, current: str, feedback: str
    ) -> list[Message]:
        parts = [f"Revise the matplotlib code for a {spec.kind}."]
        parts.append(f"Intent:\n{spec.intent}")
        parts.append(f"Current code:\n```python\n{current}\n```")
        parts.append(f"Critic feedback to address:\n{feedback}")
        parts.append(
            "Revise the code to address every point of feedback. Keep using the "
            "'Agg' backend, make no network calls, do not call plt.show(), and save "
            f"the figure to {out_name!r}. Return only a single ```python``` block."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]


def _extract_python_block(text: str) -> str:
    """Extract a ```python``` fenced code block from ``text`` (stdlib, tolerant).

    Prefers a ```python``` (or bare ```` ``` ````) fenced block; on no usable
    fence falls back to the whole completion (stripped). Never raises.
    """
    for fence in ("```python", "```py", "```"):
        start = text.find(fence)
        if start == -1:
            continue
        body_start = start + len(fence)
        end = text.find("```", body_start)
        if end == -1:
            continue
        block = text[body_start:end]
        # A bare ``` fence may have a language tag on the first line; drop it.
        return block.strip("\n").strip()
    return text.strip()


def render_plot_code(code: str, out_path: Path, *, timeout: int = 20) -> Path:
    """Render ``code`` to an image at ``out_path`` in a subprocess (GATED).

    Runs ``code`` with ``sys.executable`` in a fresh subprocess, with
    ``MPLBACKEND=Agg`` and ``cwd`` set to ``out_path.parent``, under ``timeout``
    seconds. Returns ``out_path`` once it exists.

    This executes LLM-generated code and is therefore **only** for gated/live use;
    nothing in the default expert path calls it. matplotlib is lazily required: a
    missing dependency, a non-zero exit, a timeout, or a missing output file all
    raise :class:`PlotCodeRenderError`.
    """
    out_path = Path(out_path)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib  # noqa: F401  (lazy: only when explicitly rendering)
    except ImportError as exc:
        raise PlotCodeRenderError(
            "matplotlib is required to render plots; install the 'viz' extra "
            "(`uv sync --extra viz`)."
        ) from exc

    env = {**os.environ, "MPLBACKEND": "Agg"}
    try:
        completed = subprocess.run(  # noqa: S603 - gated; runs LLM code by design
            [sys.executable, "-c", code],
            cwd=str(out_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PlotCodeRenderError(f"plot rendering timed out after {timeout}s") from exc

    if completed.returncode != 0:
        raise PlotCodeRenderError(
            f"plot rendering failed (exit {completed.returncode}): {completed.stderr.strip()}"
        )
    if not out_path.exists():
        raise PlotCodeRenderError(f"plot code did not produce the expected file: {out_path}")
    return out_path


def run_figure_refine(
    task: Task,
    *,
    producer: AgentProtocol,
    critic: AgentProtocol,
    max_rounds: int = 3,
    session: SessionContext | None = None,
) -> list[AgentOutput]:
    """Run a visualizer/critic :class:`CriticRefine` loop and return its history.

    Analogous to ``run_write_review_loop``: ``producer`` (a figure agent in plot
    mode) drafts once, then for up to ``max_rounds`` rounds ``critic`` reviews the
    current draft and the producer revises in response, stopping on the
    :data:`~clio_parser.harness.patterns.NO_CHANGES_SENTINEL` or an error-flagged
    output. The caller's payload dict is never mutated.
    """
    from clio_parser.harness.engine import Engine

    loop_task = task.model_copy(update={"payload": {**task.payload, "max_rounds": max_rounds}})
    agents: list[AgentProtocol] = [producer, critic]
    return Engine().run(agents, CriticRefine(), loop_task, session)


__all__ = [
    "FigureAgentExpert",
    "FIGURE_SYSTEM_PROMPT",
    "PlotCodeRenderError",
    "render_plot_code",
    "run_figure_refine",
]
