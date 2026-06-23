"""Tests for the unified `revise` action and its edit/polish back-compat aliases.

`revise` routes by `mode`: ``feedback`` -> the EditorExpert, ``style`` -> the
PolishExpert. The legacy `edit` and `polish` actions are retained as aliases that
must keep working even though they no longer appear in the capability manifest.
"""

from __future__ import annotations

from clio_author.agent import ClioAuthorAgent
from clio_author.harness.types import Message
from clio_author.integration import ClioAuthorSubagent


class MarkerLLM:
    """Echoes which system prompt it saw, so we can tell editor from polish."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        system = messages[0].content if messages else ""
        return f"[edit]{system[:0]}revised" if "polish" not in system.lower() else "[polish]revised"


def test_revise_feedback_mode_routes_to_editor() -> None:
    agent = ClioAuthorAgent(MarkerLLM())
    out = agent.revise("Our system is fast.", mode="feedback", critic_notes="add a baseline")
    assert out.agent == "editor"


def test_revise_style_mode_routes_to_polish() -> None:
    agent = ClioAuthorAgent(MarkerLLM())
    out = agent.revise("Our system is fast.", mode="style", voice="concise")
    assert out.agent == "polish"


def test_revise_defaults_to_feedback() -> None:
    agent = ClioAuthorAgent(MarkerLLM())
    out = agent._invoke("revise", {"draft": "text"})
    assert out.agent == "editor"


def test_revise_text_key_is_accepted() -> None:
    # The prose may be supplied as `text` (polish style) instead of `draft`.
    agent = ClioAuthorAgent(MarkerLLM())
    out = agent._invoke("revise", {"text": "some prose", "mode": "style"})
    assert out.agent == "polish"
    assert "error" not in out.metadata


def test_edit_and_polish_aliases_still_route() -> None:
    agent = ClioAuthorAgent(MarkerLLM())
    assert agent._invoke("edit", {"draft": "t", "review": {"weaknesses": ["x"]}}).agent == "editor"
    assert agent._invoke("polish", {"text": "t"}).agent == "polish"


def test_aliases_absent_from_manifest_but_revise_present() -> None:
    actions = {a["action"] for a in ClioAuthorSubagent().capabilities()["actions"]}
    assert "revise" in actions
    assert "edit" not in actions and "polish" not in actions
