"""Role-agents: fixed policies over the tools, sequenced by host / orchestrate.

A role owns a sub-domain and delegates *down* to tools; roles are peers and never
call each other (they hand off through ``ProjectMemory``). :func:`build_roles`
wires every role with the agent's tool dispatch.
"""

from __future__ import annotations

from clio_author.roles.base import Dispatch, RoleAgent
from clio_author.roles.verifier import VerifierRole

# Registered role classes (extended as roles land).
ROLE_CLASSES: tuple[type[RoleAgent], ...] = (VerifierRole,)


def build_roles(dispatch: Dispatch) -> dict[str, RoleAgent]:
    """Instantiate every role, wired to the tool ``dispatch``; keyed by name."""
    return {cls.name: cls(dispatch) for cls in ROLE_CLASSES}


__all__ = ["RoleAgent", "Dispatch", "build_roles", "ROLE_CLASSES", "VerifierRole"]
