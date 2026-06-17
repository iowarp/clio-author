# Security

This project reads optional API credentials from environment variables. Keep credentials local and
out of git history, command history, issue comments, PRs, and chat transcripts.

## Local Env File

For CLI use, put credentials in `.env.local` at the repository root. The file is ignored by git and
loaded automatically by `uv run clio-parser ...`.

```bash
cp .env.local.example .env.local
chmod 600 .env.local
```

Then edit `.env.local`:

```bash
SEMANTIC_SCHOLAR_API_KEY=your-rotated-s2-key
GEMINI_API_KEY=your-rotated-gemini-key
```

You can also point to another local file:

```bash
CLIO_ENV_FILE=/secure/path/clio.env uv run clio-parser capabilities
```

Real environment variables override values from `.env.local`.

## Key Rotation

If a key is pasted into a chat, terminal transcript, issue, PR, or committed file, treat it as
compromised:

1. Revoke or rotate it at the provider.
2. Replace the local value in `.env.local`.
3. Do not reuse the exposed key in tests or examples.

## Semantic Scholar Rate Limit

Semantic Scholar API keys may be limited to 1 request per second across endpoints. The S2 client
enforces a process-wide 1 request/second delay before S2 HTTP calls. No-key citation fallbacks are
available through:

```bash
CLIO_SCHOLAR=auto      # Semantic Scholar + OpenAlex + Crossref + arXiv
CLIO_SCHOLAR=openalex  # no key required
CLIO_SCHOLAR=crossref  # no key required
CLIO_SCHOLAR=arxiv     # no key required
CLIO_SCHOLAR=off       # disable lookup
```
