"""Integration adapters so a host can invoke clio-author as a subagent.

This package is intentionally thin and host-agnostic: it imports **nothing** from
the ``clio-agent`` repo. A host (e.g. the CLIO agent) calls
:class:`~clio_author.integration.clio_adapter.ClioAuthorSubagent` directly (in
process) or via the ``clio-author`` CLI (subprocess); both surfaces are
JSON-serializable and never raise.
"""

from clio_author.integration.clio_adapter import ClioAuthorSubagent

__all__ = ["ClioAuthorSubagent"]
