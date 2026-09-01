"""Loading ``KEY=VALUE`` configuration from a local env file.

Secrets live in a git-ignored env file rather than on a command line: ``.env.local``
by default, or the path named by ``CLIO_ENV_FILE``. Real environment variables always
win, so an explicit ``CLIO_LLM=... clio-author ...`` overrides the file.

This lives outside :mod:`clio_author.cli` because every entry point needs it, not just
the CLI: the A2A server and the MCP bridge are separate processes with their own
environments, and a host that starts them never gets the operator's shell.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def strip_env_quotes(value: str) -> str:
    """Strip one matching shell-style quote pair from an env-file value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    """Load simple ``KEY=VALUE`` lines from ``path`` without overriding real env vars.

    A missing file is not an error: the env file is optional everywhere. Blank lines,
    ``#`` comments, a leading ``export``, and lines without ``=`` are skipped, and a
    key that is not a valid shell identifier is ignored rather than trusted.
    """
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read env file {path!s}: {exc}") from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not _KEY_RE.fullmatch(key):
            continue
        os.environ.setdefault(key, strip_env_quotes(value.strip()))


def load_env() -> None:
    """Load env configuration for a clio-author process.

    ``CLIO_ENV_FILE=/path/to/file`` is explicit and is the only file read when set.
    Otherwise ``.env.local`` in the current working directory is read when present,
    then ``.env`` for users who prefer that conventional name.
    """
    explicit = os.environ.get("CLIO_ENV_FILE")
    if explicit:
        load_env_file(Path(explicit))
        return
    load_env_file(Path(".env.local"))
    load_env_file(Path(".env"))


__all__ = ["load_env", "load_env_file", "strip_env_quotes"]
