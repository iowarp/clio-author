"""Shared memory for clio-author: project blackboard + result cache.

:class:`ProjectMemory` is the file-backed blackboard role-agents hand off
through (outline, plan, decisions, drafts, reports, …). :class:`ResultCache` is a
content-addressed cache of action results so re-running an unchanged step in a
refine loop is free. Both are pure, dependency-light, and never raise.
"""

from __future__ import annotations

from clio_author.memory.cache import ResultCache
from clio_author.memory.project_memory import CANONICAL_SLOTS, ProjectMemory

__all__ = ["ProjectMemory", "ResultCache", "CANONICAL_SLOTS"]
