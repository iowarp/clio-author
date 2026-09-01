

def test_resolve_arxiv_url_accepts_arxiv_scheme_prefix() -> None:
    """``arxiv:<id>`` resolves like a bare id instead of falling through to search."""
    from clio_author.ingest.docling_extract import resolve_arxiv_url

    assert (
        resolve_arxiv_url("arxiv:1706.03762")
        == "https://arxiv.org/pdf/1706.03762.pdf"
    )
    assert (
        resolve_arxiv_url("arXiv:1706.03762v5")
        == "https://arxiv.org/pdf/1706.03762v5.pdf"
    )
