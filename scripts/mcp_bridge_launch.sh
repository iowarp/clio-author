#!/usr/bin/env bash
cd /home/shazzadul/Illinois_Tech/Summer26/RA/clio-author || exit 1
exec uv run --no-sync --with fastmcp python -m clio_author.integration.mcp_bridge
