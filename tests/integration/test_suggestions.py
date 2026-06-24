"""Tests for the 'what to run next' suggestion hints.

The manifest owns an ``action -> next actions`` map (lock-step guarded at import);
the agent attaches ``metadata.suggested_next`` to every successful result so a
host or the CLI can guide the user through the pipeline.
"""

from __future__ import annotations

from clio_author.integration import ClioAuthorSubagent
from clio_author.integration.manifest import ACTIONS, NEXT_STEPS, suggested_next


def test_suggested_next_shape_and_validity() -> None:
    nxt = suggested_next("plan")
    assert nxt and all({"action", "why"} <= set(item) for item in nxt)
    assert nxt[0]["action"] == "plan_check"  # validate before writing


def test_every_action_has_an_entry_and_targets_are_real() -> None:
    names = {e["action"] for e in ACTIONS}
    assert set(NEXT_STEPS) == names  # lock-step: no action without a hint
    for src, nexts in NEXT_STEPS.items():
        for action, _why in nexts:
            assert action in names, f"{src} suggests unknown action {action}"


def test_agent_attaches_suggestions_to_results() -> None:
    sub = ClioAuthorSubagent()
    # cite_support degrades to a real result under echo; it should carry hints.
    result = sub.run(
        "cite_support",
        {
            "text": "A claim \\cite{k}.",
            "citations": [{"citation_key": "k", "record": {"abstract": "some abstract"}}],
        },
    )
    nxt = result["metadata"].get("suggested_next")
    assert isinstance(nxt, list) and any(i["action"] == "ground" for i in nxt)


def test_errors_get_no_suggestions() -> None:
    sub = ClioAuthorSubagent()
    result = sub.run("cite_support", {})  # missing inputs -> error
    assert "suggested_next" not in result["metadata"]
