"""Core data models for the clio-parser harness.

All models are Pydantic v2 ``BaseModel`` subclasses with full type hints. These
types form the wire format passed between agents, patterns, and the engine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "expert"]
"""The originating role of a :class:`Message`."""


class Message(BaseModel):
    """A single message in an LLM conversation."""

    role: Role
    content: str
    name: str | None = None
    metadata: dict = Field(default_factory=dict)


class Task(BaseModel):
    """A unit of work handed to an agent or pattern."""

    id: str
    description: str
    payload: dict = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """The result produced by an agent for a given task."""

    agent: str
    content: str
    structured: dict | None = None
    metadata: dict = Field(default_factory=dict)
