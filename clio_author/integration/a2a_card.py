"""Build an A2A Agent Card for clio-author from the capability manifest.

The card is the discovery document an A2A host fetches to learn what this agent
can do. Each clio-author **tool** (the 24 actions in
:data:`~clio_author.integration.manifest.ACTIONS`) and each **role** (the 7
role-agents) becomes one A2A *skill*, so a host can discover and invoke the real
capability surface — not a single opaque "run" tool.

- A2A protocol — https://github.com/a2aproject/A2A (Apache-2.0).

Pure and dependency-light: building the card constructs no agent and makes no
network call; it reads the manifest + the role registry directly.
"""

from __future__ import annotations

from typing import Any

from clio_author.integration.manifest import ACTIONS
from clio_author.roles import ROLE_CLASSES, RoleAgent

_DESCRIPTION = (
    "A standalone multi-agent harness for processing, reviewing, and writing "
    "scientific papers: 24 tools (one job each) and 7 roles (fixed policies that "
    "run several tools for you)."
)


def _tool_skill(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": action["action"],
        "name": action["action"].replace("_", " "),
        "description": action["description"],
        "tags": ["tool", *action.get("phase", [])],
        "inputModes": ["application/json", "text/plain"],
        "outputModes": ["application/json", "text/plain"],
    }


def _role_skill(role_cls: type[RoleAgent]) -> dict[str, Any]:
    return {
        "id": f"role:{role_cls.name}",
        "name": f"{role_cls.name} role",
        "description": role_cls.description,
        "tags": ["role"],
        "inputModes": ["application/json", "text/plain"],
        "outputModes": ["application/json", "text/plain"],
    }


def build_agent_card(*, url: str = "http://localhost:8080/", version: str = "0") -> dict[str, Any]:
    """Return the A2A Agent Card describing clio-author's skills.

    One skill per tool (24) + one per role (7) = 31 skills, generated from the
    manifest and the role registry so the card never drifts from the code.
    """
    skills = [_tool_skill(a) for a in ACTIONS] + [_role_skill(r) for r in ROLE_CLASSES]
    return {
        "name": "clio-author",
        "description": _DESCRIPTION,
        "version": version,
        "url": url,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": skills,
    }


__all__ = ["build_agent_card"]
