from typing import Any

from .protocol import Paper


def _build_batch_id(config, generated_at: str) -> str:
    date_part = generated_at[:10]
    sources = "-".join(config.executor.source)
    return f"{date_part}-{sources}-top{config.executor.max_paper_num}"


def _paper_to_payload(paper: Paper, include_full_text: bool) -> dict[str, Any]:
    return {
        "source": paper.source,
        "title": paper.title,
        "authors": list(paper.authors),
        "abstract": paper.abstract,
        "url": paper.url,
        "pdf_url": paper.pdf_url,
        "score": paper.score,
        "full_text": paper.full_text if include_full_text else None,
    }


def build_batch_payload(config, papers: list[Paper], *, generated_at: str) -> dict[str, Any]:
    include_full_text = bool(config.nanoclaw.include_full_text)
    return {
        "schema_version": "1",
        "batch_id": _build_batch_id(config, generated_at),
        "generated_at": generated_at,
        "sources": list(config.executor.source),
        "paper_count": len(papers),
        "papers": [_paper_to_payload(paper, include_full_text) for paper in papers],
    }
