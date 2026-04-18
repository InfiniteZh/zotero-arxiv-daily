import json
import re
import socket
from datetime import datetime
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from omegaconf import DictConfig

from .protocol import Paper


def _format_source_label(source: str) -> str:
    label_map = {
        "arxiv": "arXiv",
        "biorxiv": "bioRxiv",
        "medrxiv": "medRxiv",
    }
    return label_map.get(source.lower(), source.upper())


def _format_score(score: float | None) -> str:
    if score is None:
        return "评分 N/A"
    return f"评分 {score:.1f}"


def _format_authors(authors: list[str]) -> str:
    if not authors:
        return "Unknown authors"
    names = ", ".join(authors[:5])
    if len(authors) > 5:
        names += " et al."
    return names


def _truncate_summary(text: str | None, limit: int = 360) -> str:
    if not text:
        return "No summary available."
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _is_chinese_ui(config: DictConfig) -> bool:
    language = str(getattr(config.llm, "language", "English")).lower()
    return "chinese" in language or language.startswith("zh") or "中文" in language


def _summary_label(config: DictConfig) -> str:
    if _is_chinese_ui(config):
        return "LLM总结"
    return "TL;DR:"


def _normalize_summary_text(text: str | None) -> str:
    summary = _truncate_summary(text)
    summary = re.sub(r"^\*\*\s*(TL;?DR|TLDR|摘要|总结)\s*[：:]\s*\*\*\s*", "", summary, flags=re.IGNORECASE)
    summary = re.sub(r"^(TL;?DR|TLDR|摘要|总结)\s*[：:]\s*", "", summary, flags=re.IGNORECASE)
    return summary.strip()


def _paper_badges(paper: Paper, index: int, *, chinese_ui: bool) -> str:
    rank_label = f"TOP {index}" if chinese_ui else f"Rank {index}"
    return " ".join(
        [
            f"<text_tag color='blue'>{_format_source_label(paper.source)}</text_tag>",
            f"<text_tag color='indigo'>{rank_label}</text_tag>",
            f"<text_tag color='green'>{_format_score(paper.score)}</text_tag>",
        ]
    )


def _paper_links(paper: Paper, *, chinese_ui: bool) -> str:
    links = []
    if paper.url:
        links.append(
            f"[查看摘要]({paper.url})" if chinese_ui else f"[Abstract]({paper.url})"
        )
    if paper.pdf_url:
        links.append(
            f"[打开 PDF]({paper.pdf_url})" if chinese_ui else f"[PDF]({paper.pdf_url})"
        )
    return " | ".join(links) if links else "No external links"


def _build_paper_markdown(config: DictConfig, paper: Paper, index: int) -> str:
    chinese_ui = _is_chinese_ui(config)
    authors_line = (
        f"<font color='grey'>作者：{_format_authors(paper.authors)}</font>"
        if chinese_ui
        else f"<font color='grey'>Authors: {_format_authors(paper.authors)}</font>"
    )
    meta_line = f"{_paper_badges(paper, index, chinese_ui=chinese_ui)}<br/>{authors_line}"
    summary_label = _summary_label(config)
    summary_text = _normalize_summary_text(paper.tldr or paper.abstract)
    summary_block = (
        f"<text_tag color='carmine'>{summary_label}</text_tag> {summary_text}"
    )
    return (
        f"**{index}. {paper.title or 'Untitled'}**<br/>"
        f"{meta_line}<br/>"
        f"{summary_block}<br/>"
        f"{_paper_links(paper, chinese_ui=chinese_ui)}"
    )


def _build_feishu_card(
    config: DictConfig,
    papers: list[Paper],
    *,
    generated_at: str,
) -> dict[str, Any]:
    generated_dt = datetime.fromisoformat(generated_at)
    today = generated_dt.strftime("%Y/%m/%d")
    bot_name = getattr(config.feishu, "bot_name", "arXiv Daily Bot")
    paper_count = len(papers)
    source_tags = " ".join(_format_source_label(source) for source in config.executor.source)
    chinese_ui = _is_chinese_ui(config)
    header_title = "论文速递" if chinese_ui else "Paper Digest"
    summary_title = f"**今日精选 {paper_count} 篇论文**" if chinese_ui else f"**Found {paper_count} ranked papers for today.**"
    meta_line = (
        f"<font color='grey'>来源：{source_tags} · 生成时间：{generated_dt.strftime('%Y-%m-%d %H:%M')}</font>"
        if chinese_ui
        else f"<font color='grey'>Sources: {source_tags} · Generated: {generated_dt.strftime('%Y-%m-%d %H:%M')}</font>"
    )
    empty_state = "本次运行没有筛选出论文。" if chinese_ui else "No ranked papers were selected for this run."

    header = {
        "title": {
            "tag": "plain_text",
            "content": f"{header_title} | {today}",
        },
        "template": "blue",
    }

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{summary_title}\n{meta_line}",
            },
        },
        {"tag": "hr"},
    ]

    if papers:
        for i, paper in enumerate(papers, 1):
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": _build_paper_markdown(config, paper, i),
                    },
                }
            )
            if i < len(papers):
                elements.append({"tag": "hr"})
    else:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": empty_state,
                },
            }
        )

    elements.extend(
        [
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": (
                            f"由 {bot_name} 生成"
                            if chinese_ui
                            else f"Powered by {bot_name}"
                        ),
                    },
                ],
            },
        ]
    )

    return {
        "msg_type": "interactive",
        "card": {
            "header": header,
            "elements": elements,
        },
    }


def _validate_feishu_config(config: DictConfig):
    """Validate Feishu configuration."""
    if not bool(config.feishu.enabled):
        raise RuntimeError("Feishu publishing is disabled")

    if not config.feishu.webhook_url:
        raise RuntimeError("Feishu webhook_url is missing")

    if not config.feishu.webhook_url.startswith(("http://", "https://")):
        raise RuntimeError("Feishu webhook_url must be a valid HTTP/HTTPS URL")


def _make_feishu_request(config: DictConfig, payload: dict[str, Any]) -> Request:
    """Make an HTTP request to Feishu webhook."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    return Request(
        config.feishu.webhook_url,
        data=body,
        headers=headers,
        method="POST",
    )


def _parse_feishu_response(raw_body: bytes) -> dict[str, Any]:
    """Parse Feishu API response."""
    if not raw_body:
        return {"ok": True}
    return json.loads(raw_body.decode("utf-8"))


def publish_to_feishu(
    config: DictConfig, papers: list[Paper], *, generated_at: str
) -> dict[str, Any]:
    """
    Publish paper recommendations to Feishu via webhook.

    Args:
        config: Application configuration
        papers: List of recommended papers
        generated_at: ISO timestamp of generation

    Returns:
        Response from Feishu API
    """
    _validate_feishu_config(config)

    payload = _build_feishu_card(config, papers, generated_at=generated_at)

    max_retries = int(getattr(config.feishu, "max_retries", 3))
    timeout = int(getattr(config.feishu, "timeout", 30))
    webhook_url = str(config.feishu.webhook_url)

    for attempt in range(max_retries + 1):
        request = _make_feishu_request(config, payload)
        try:
            with urlopen(request, timeout=timeout) as response:
                response_body = _parse_feishu_response(response.read())

            # Feishu returns code=0 for success
            if response_body.get("code") == 0 or response_body.get("StatusCode") == 0:
                logger.info(
                    "Feishu card published successfully with {} papers at {}",
                    len(papers),
                    webhook_url,
                )
                return response_body
            else:
                error_msg = response_body.get("msg", "Unknown error")
                logger.error(
                    "Feishu publish failed with code {}: {}",
                    response_body.get("code"),
                    error_msg,
                )
                raise RuntimeError(f"Feishu API error: {error_msg}")

        except HTTPError as error:
            body_text = (
                error.read().decode("utf-8", errors="replace")
                if hasattr(error, "read")
                else ""
            )
            if error.code in (400, 401, 403):
                logger.error(
                    "Feishu publish failed with HTTP {}: {}",
                    error.code,
                    body_text,
                )
                raise RuntimeError(
                    f"Feishu publish failed with HTTP {error.code}: {body_text}"
                )
            if error.code >= 500 and attempt < max_retries:
                logger.warning(
                    "Feishu publish failed with HTTP {} on attempt {}/{}; retrying...",
                    error.code,
                    attempt + 1,
                    max_retries + 1,
                )
                sleep(1)
                continue
            raise RuntimeError(f"Feishu publish failed with HTTP {error.code}: {body_text}")

        except socket.timeout as error:
            if attempt < max_retries:
                logger.warning(
                    "Feishu publish timed out on attempt {}/{}; retrying...",
                    attempt + 1,
                    max_retries + 1,
                )
                sleep(1)
                continue
            raise RuntimeError(f"Feishu publish timed out after {max_retries + 1} attempts") from error

        except URLError as error:
            if attempt < max_retries:
                logger.warning(
                    "Feishu publish network error on attempt {}/{}; retrying...",
                    attempt + 1,
                    max_retries + 1,
                )
                sleep(1)
                continue
            raise RuntimeError(f"Feishu publish failed after network retries: {error}") from error
