"""Hermetic tests for :class:`VerifyWorkExpert`."""

from __future__ import annotations

import json

from clio_author.experts.verify_work import VerifyWorkExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task

_VERIFIED_JSON = {
    "claims": [
        {"claim": "X improves Y", "made": True, "supported": True, "evidence": "Table 1"},
        {"claim": "X is fast", "made": True, "supported": True, "evidence": "Fig 2"},
    ],
    "gaps": [],
}

_GAPS_JSON = {
    "claims": [
        {"claim": "X improves Y", "made": True, "supported": False, "gap": "no baseline"},
    ],
    "gaps": ["no baseline comparison"],
}


class CannedJSONLLMClient:
    """Fake client returning a fixed fenced JSON verification result."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return "```json\n" + json.dumps(self.payload) + "\n```"


def _run(expert: VerifyWorkExpert, **payload: object) -> object:
    return expert.run(Task(id="t", description="verify", payload=payload), SessionContext(id="s"))


def test_verify_work_all_supported_is_verified() -> None:
    out = _run(
        VerifyWorkExpert(CannedJSONLLMClient(_VERIFIED_JSON)),
        claims=["X improves Y", "X is fast"],
        text="We show X improves Y (Table 1) and X is fast (Fig 2).",
    )
    assert out.agent == "verify_work"
    assert out.metadata["status"] == "VERIFIED"
    assert out.metadata["num_claims"] == 2
    assert out.structured is not None
    assert out.structured["status"] == "VERIFIED"


def test_verify_work_unsupported_is_gaps() -> None:
    out = _run(
        VerifyWorkExpert(CannedJSONLLMClient(_GAPS_JSON)),
        claims=["X improves Y"],
        text="We claim X improves Y.",
    )
    assert out.metadata["status"] == "GAPS"
    assert out.structured is not None
    assert out.structured["gaps"]


def test_verify_work_uses_section_plan_claims() -> None:
    plan = {"outline": {"title": "Intro"}, "claims": ["X improves Y"]}
    out = _run(
        VerifyWorkExpert(CannedJSONLLMClient(_GAPS_JSON)),
        section_plan=plan,
        text="We claim X improves Y.",
    )
    assert "error" not in out.metadata
    assert out.metadata["status"] == "GAPS"


def test_verify_work_echo_degrades_to_gaps() -> None:
    out = _run(VerifyWorkExpert(), claims=["X improves Y"], text="prose")
    assert "parse_error" in out.metadata
    assert out.metadata["status"] == "GAPS"  # never fabricates VERIFIED
    assert out.structured is not None
    assert out.structured["claims"] == []


def test_verify_work_missing_claims_errors() -> None:
    out = _run(VerifyWorkExpert(CannedJSONLLMClient(_VERIFIED_JSON)), text="prose")
    assert "error" in out.metadata


def test_verify_work_missing_text_errors() -> None:
    out = _run(VerifyWorkExpert(CannedJSONLLMClient(_VERIFIED_JSON)), claims=["c"])
    assert "error" in out.metadata
