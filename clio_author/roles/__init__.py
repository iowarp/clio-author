"""Role-agents: fixed policies over the tools, sequenced by host / orchestrate.

A role owns a sub-domain and delegates *down* to tools; roles are peers and never
call each other (they hand off through ``ProjectMemory``). :func:`build_roles`
wires every role with the agent's tool dispatch.
"""

from __future__ import annotations

from clio_author.roles.base import Dispatch, RoleAgent
from clio_author.roles.reader import ReaderRole
from clio_author.roles.refiner import RefinerRole
from clio_author.roles.reviewer import ReviewerRole
from clio_author.roles.scholar import ScholarRole
from clio_author.roles.verifier import VerifierRole
from clio_author.roles.viz import VizRole
from clio_author.roles.writer import WriterRole

# Registered role classes, in pipeline order.
ROLE_CLASSES: tuple[type[RoleAgent], ...] = (
    ReaderRole,
    ScholarRole,
    WriterRole,
    VerifierRole,
    ReviewerRole,
    RefinerRole,
    VizRole,
)


def build_roles(dispatch: Dispatch) -> dict[str, RoleAgent]:
    """Instantiate every role, wired to the tool ``dispatch``; keyed by name."""
    return {cls.name: cls(dispatch) for cls in ROLE_CLASSES}


__all__ = [
    "RoleAgent",
    "Dispatch",
    "build_roles",
    "ROLE_CLASSES",
    "ReaderRole",
    "ScholarRole",
    "WriterRole",
    "VerifierRole",
    "ReviewerRole",
    "RefinerRole",
    "VizRole",
]
