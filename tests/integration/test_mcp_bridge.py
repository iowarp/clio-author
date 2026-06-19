"""Hermetic tests for the optional MCP bridge (no fastmcp / no network required)."""

from __future__ import annotations

import importlib

import pytest


def test_bridge_imports_without_fastmcp() -> None:
    # Importing the module must not require fastmcp (lazy inside build_server).
    mod = importlib.import_module("clio_author.integration.mcp_bridge")
    assert hasattr(mod, "build_server") and hasattr(mod, "main")


def test_build_server_requires_fastmcp_or_builds() -> None:
    from clio_author.integration import mcp_bridge

    try:
        import fastmcp  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="fastmcp is required"):
            mcp_bridge.build_server()
    else:
        srv = mcp_bridge.build_server()  # builds + registers tools
        assert srv is not None
