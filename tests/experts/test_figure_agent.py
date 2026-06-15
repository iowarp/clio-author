"""Hermetic tests for :class:`FigureAgentExpert` (canned client + tmp root).

No matplotlib import, no network, no code execution: the plot path only generates
and writes code TEXT, and the tests assert no image file is produced.
"""

from __future__ import annotations

from pathlib import Path

from clio_parser.experts.figure_agent import FigureAgentExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Message, Task
from clio_parser.ingest.blocks import FigureInfo, MemoryBlocks
from clio_parser.tools.files import SafeFiles

_PLOT_CODE = (
    "Here is the figure code:\n"
    "```python\n"
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "plt.plot([0, 1], [0, 1])\n"
    "plt.savefig('figure.png')\n"
    "```\n"
    "Done."
)


class RecordingLLM:
    """Fake client that records the prompt and returns a fixed completion."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


# --- describe mode -----------------------------------------------------------
def test_describe_fills_descriptions_on_figures_lacking_them() -> None:
    llm = RecordingLLM(response="A bar chart of accuracy by model.")
    expert = FigureAgentExpert(llm=llm)
    blocks = MemoryBlocks(
        figures=[
            FigureInfo(figure_id=1, caption="Accuracy by model"),
            FigureInfo(figure_id=2, caption="Loss curve", description="already described"),
        ]
    )
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="describe",
        payload={"mode": "describe", "blocks": blocks.model_dump(), "context": "Section 4"},
    )

    output = expert.run(task, session)

    assert output.metadata["mode"] == "describe"
    assert output.metadata["num_described"] == 1
    assert output.structured is not None
    updated = MemoryBlocks.model_validate(output.structured["blocks"])
    fig1 = next(f for f in updated.figures if f.figure_id == 1)
    fig2 = next(f for f in updated.figures if f.figure_id == 2)
    assert fig1.description == "A bar chart of accuracy by model."
    assert fig2.description == "already described"  # untouched
    assert "Section 4" in llm.user_prompt


def test_describe_does_not_mutate_live_blocks() -> None:
    llm = RecordingLLM(response="A bar chart of accuracy by model.")
    expert = FigureAgentExpert(llm=llm)
    blocks = MemoryBlocks(figures=[FigureInfo(figure_id=1, caption="Accuracy by model")])
    session = SessionContext(id="s")
    # Pass the LIVE MemoryBlocks instance (not a dump).
    task = Task(
        id="t",
        description="describe",
        payload={"mode": "describe", "blocks": blocks},
    )

    output = expert.run(task, session)

    # The caller's original figure is untouched...
    assert blocks.figures[0].description is None
    # ...while the returned/structured blocks carry the new description.
    assert output.structured is not None
    updated = MemoryBlocks.model_validate(output.structured["blocks"])
    assert updated.figures[0].description == "A bar chart of accuracy by model."


def test_describe_does_not_mutate_live_figure_in_list() -> None:
    llm = RecordingLLM(response="desc")
    expert = FigureAgentExpert(llm=llm)
    fig = FigureInfo(figure_id=7, caption="c")
    session = SessionContext(id="s")
    # Pass a LIVE FigureInfo instance inside the figures list.
    task = Task(id="t", description="describe", payload={"mode": "describe", "figures": [fig]})

    output = expert.run(task, session)

    assert fig.description is None  # caller's object untouched
    assert output.structured is not None
    assert output.structured["descriptions"][0]["description"] == "desc"


def test_describe_via_figures_list() -> None:
    llm = RecordingLLM(response="desc")
    expert = FigureAgentExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="describe",
        payload={"mode": "describe", "figures": [{"figure_id": 7, "caption": "c"}]},
    )

    output = expert.run(task, session)

    assert output.metadata["num_described"] == 1
    assert output.structured is not None
    assert "blocks" not in output.structured  # no container supplied
    descriptions = output.structured["descriptions"]
    assert descriptions[0]["figure_id"] == 7
    assert descriptions[0]["description"] == "desc"


def test_describe_missing_figures_errors() -> None:
    expert = FigureAgentExpert(llm=RecordingLLM(response="x"))
    session = SessionContext(id="s")
    task = Task(id="t", description="d", payload={"mode": "describe"})

    output = expert.run(task, session)
    assert "error" in output.metadata
    assert session.history[-1] is output


# --- plot mode ---------------------------------------------------------------
def test_plot_extracts_python_block() -> None:
    llm = RecordingLLM(response=_PLOT_CODE)
    expert = FigureAgentExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="plot",
        payload={"mode": "plot", "spec": {"intent": "line plot", "data_hint": "two points"}},
    )

    output = expert.run(task, session)

    assert output.metadata["mode"] == "plot"
    assert output.metadata["phase"] == "draft"
    assert "import matplotlib" in output.content
    assert "Here is the figure code" not in output.content  # fence stripped
    assert output.structured is not None
    assert output.structured["artifact"]["code"] == output.content
    assert session.data["draft"] == output.content


def test_plot_fallback_when_no_fence() -> None:
    llm = RecordingLLM(response="import matplotlib  # bare")
    expert = FigureAgentExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(id="t", description="plot", payload={"mode": "plot", "spec": {"intent": "x"}})

    output = expert.run(task, session)
    assert output.content == "import matplotlib  # bare"


def test_plot_writes_code_not_image(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    llm = RecordingLLM(response=_PLOT_CODE)
    expert = FigureAgentExpert(llm=llm, files=files)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="plot",
        payload={"mode": "plot", "spec": {"intent": "line plot"}, "out_path": "fig.py"},
    )

    output = expert.run(task, session)

    written = tmp_path / "fig.py"
    assert written.read_text(encoding="utf-8") == output.content
    assert output.metadata["wrote"] == [str(written)]
    # Code is NOT executed -> no image artifact appears.
    assert not (tmp_path / "figure.png").exists()
    assert list(tmp_path.glob("*.png")) == []


def test_plot_revise_consumes_critic_feedback() -> None:
    llm = RecordingLLM(response=_PLOT_CODE)
    expert = FigureAgentExpert(llm=llm)
    session = SessionContext(id="s")
    session.data["draft"] = "import matplotlib  # old"
    session.data["critic_feedback"] = "Add axis labels."
    task = Task(id="t", description="plot", payload={"mode": "plot", "spec": {"intent": "x"}})

    output = expert.run(task, session)

    assert output.metadata["phase"] == "revise"
    prompt = llm.user_prompt
    assert "import matplotlib  # old" in prompt
    assert "Add axis labels." in prompt


def test_plot_missing_spec_errors() -> None:
    expert = FigureAgentExpert(llm=RecordingLLM(response="x"))
    session = SessionContext(id="s")
    task = Task(id="t", description="plot", payload={"mode": "plot"})

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_plot_file_refusal_flags_error_not_raise(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    (tmp_path / "fig.py").write_text("existing", encoding="utf-8")
    expert = FigureAgentExpert(llm=RecordingLLM(response=_PLOT_CODE), files=files)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="plot",
        payload={"mode": "plot", "spec": {"intent": "x"}, "out_path": "fig.py"},
    )

    output = expert.run(task, session)
    assert "error" in output.metadata
    assert (tmp_path / "fig.py").read_text(encoding="utf-8") == "existing"


# --- integration -------------------------------------------------------------
def test_emits_one_output_via_engine_sequential() -> None:
    expert = FigureAgentExpert(llm=RecordingLLM(response=_PLOT_CODE))
    task = Task(id="t", description="plot", payload={"mode": "plot", "spec": {"intent": "x"}})
    session = SessionContext(id="s")

    outputs = Engine().run([expert], Sequential(), task, session)
    assert len(outputs) == 1
    assert len(session.history) == 1
    assert outputs[0].agent == "figure"
