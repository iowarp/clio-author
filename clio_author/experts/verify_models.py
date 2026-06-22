"""Pydantic v2 schemas for goal-backward verification of written prose.

The notion of checking written prose *against the plan that produced it* --
"was each intended claim actually made, and is it supported?" -- mirrors the
goal-backward verification step of the JS writing toolkit wtf-p:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (a per-claim made/supported check rolled up into a
VERIFIED/GAPS verdict) is re-typed here as Pydantic models; no source code is
copied. :meth:`ClaimCheck.from_loose_dict` and :meth:`VerifyResult.from_loose_dict`
map a loose / partial LLM dict onto these fields. The coercion idioms follow
``write_models.py`` / ``review_models.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["VERIFIED", "GAPS"]
"""Overall verification verdict: every claim made + supported, or gaps remain."""


def _coerce_bool(raw: Any) -> bool:
    """Coerce common truthy/falsey scalar encodings into a ``bool``."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "yes", "1", "supported", "made"}
    return bool(raw)


def _coerce_list(raw: Any) -> list[str]:
    """Coerce ``raw`` into a list of strings (wrapping a lone scalar)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if str(item).strip()]
    return [str(raw)]


def _norm_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Lower-case / underscore-normalise the keys of a loose dict."""
    return {str(key).strip().lower().replace(" ", "_"): value for key, value in raw.items()}


class ClaimCheck(BaseModel):
    """The verification result for a single intended claim."""

    claim: str
    made: bool = False
    supported: bool = False
    evidence: str = ""
    gap: str = ""

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> ClaimCheck:
        """Build a :class:`ClaimCheck` from a loose / partial dict. Never raises."""
        norm = _norm_keys(raw)

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        return cls(
            claim=str(pick("claim", "statement") or "").strip(),
            made=_coerce_bool(pick("made", "stated", "present")),
            supported=_coerce_bool(pick("supported", "evidenced")),
            evidence=str(pick("evidence", "support") or "").strip(),
            gap=str(pick("gap", "missing", "issue") or "").strip(),
        )


class VerifyResult(BaseModel):
    """A rolled-up verification result over a set of intended claims."""

    status: Status = "GAPS"
    claims: list[ClaimCheck] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> VerifyResult:
        """Build a :class:`VerifyResult` from a loose / partial dict. Never raises.

        Coerces each claim entry via :meth:`ClaimCheck.from_loose_dict`, derives
        ``gaps`` (preferring the model's own list, else the per-claim ``gap``
        notes), and computes ``status`` deterministically: ``VERIFIED`` only when
        there is at least one claim and every claim was both made and supported,
        otherwise ``GAPS``.
        """
        norm = _norm_keys(raw)

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        raw_claims = pick("claims", "checks")
        claims: list[ClaimCheck] = []
        if isinstance(raw_claims, (list, tuple)):
            for item in raw_claims:
                if isinstance(item, ClaimCheck):
                    claims.append(item)
                elif isinstance(item, dict):
                    claims.append(ClaimCheck.from_loose_dict(item))
                elif isinstance(item, str) and item.strip():
                    claims.append(ClaimCheck(claim=item.strip()))

        gaps = _coerce_list(pick("gaps"))
        if not gaps:
            gaps = [c.gap for c in claims if c.gap]

        status = cls.derive_status(claims)
        return cls(status=status, claims=claims, gaps=gaps)

    @staticmethod
    def derive_status(claims: list[ClaimCheck]) -> Status:
        """Return ``VERIFIED`` iff there is >=1 claim and all are made + supported."""
        if claims and all(c.made and c.supported for c in claims):
            return "VERIFIED"
        return "GAPS"


__all__ = ["Status", "ClaimCheck", "VerifyResult"]
