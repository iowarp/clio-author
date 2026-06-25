"""Hermetic tests for ProjectMemory + ResultCache (pure, no LLM)."""

from __future__ import annotations

from clio_author.memory import ProjectMemory, ResultCache


def test_project_memory_roundtrip_and_defaults(tmp_path) -> None:
    m = ProjectMemory(tmp_path / "mem")
    assert m.get("plan") is None
    assert m.get("plan", "x") == "x"
    assert not m.has("plan")

    m.put("plan", {"sections": 3})
    assert m.has("plan")
    assert m.get("plan") == {"sections": 3}
    assert "plan" in m.slots()


def test_project_memory_update_merges(tmp_path) -> None:
    m = ProjectMemory(tmp_path / "mem")
    m.update("decisions", locked=["call it AUTHOR"])
    merged = m.update("decisions", deferred=["slides"])
    assert merged == {"locked": ["call it AUTHOR"], "deferred": ["slides"]}
    assert m.get("decisions") == merged


def test_project_memory_corrupt_slot_returns_default(tmp_path) -> None:
    m = ProjectMemory(tmp_path / "mem")
    (m.root / "bib.json").write_text("{not json", encoding="utf-8")
    assert m.get("bib", "fallback") == "fallback"  # never raises


def test_project_memory_rejects_unsafe_slot(tmp_path) -> None:
    m = ProjectMemory(tmp_path / "mem")
    # an unsafe name is refused on get (default) and never escapes the dir
    assert m.get("../escape", "d") == "d"
    assert m.has("../escape") is False


def test_result_cache_hit_is_order_independent(tmp_path) -> None:
    c = ResultCache(tmp_path / "cache")
    payload_a = {"text": "hi", "k": 3}
    payload_b = {"k": 3, "text": "hi"}  # same content, different order
    assert c.get("verify_work", payload_a, "echo") is None  # miss

    c.put("verify_work", payload_a, {"status": "VERIFIED"}, "echo")
    assert c.get("verify_work", payload_b, "echo") == {"status": "VERIFIED"}  # hit


def test_result_cache_misses_on_model_or_payload_change(tmp_path) -> None:
    c = ResultCache(tmp_path / "cache")
    c.put("write", {"outline": "Intro"}, {"draft": "..."}, "codex")
    assert c.get("write", {"outline": "Intro"}, "claude") is None  # model differs
    assert c.get("write", {"outline": "Method"}, "codex") is None  # payload differs
