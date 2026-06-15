"""Integration adapters so a host can invoke clio-parser as a subagent.

This package is intentionally thin and host-agnostic: it imports **nothing** from
the ``clio-agent`` repo. A host (e.g. the CLIO agent) calls
:class:`~clio_parser.integration.clio_adapter.ClioParserSubagent` directly (in
process) or via the ``clio-parser`` CLI (subprocess); both surfaces are
JSON-serializable and never raise.
"""

from clio_parser.integration.clio_adapter import ClioParserSubagent

__all__ = ["ClioParserSubagent"]
