import json
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
        "arxiv": ("arXiv", "blue"),
        "biorxiv": ("bioRxiv", "turquoise"),
        "medrxiv": ("medRxiv", "orange"),
    }
    label, color = label_map.get(source.lower(), (source.upper(), "neutral"))
    return f"<text_tag color='{color}'>{label}</text_tag>"


def _format_score(score: float | None) -> str:
    if score is None:
        return "`Score: N/A`"
    return f"`Score: {score:.1f}`"


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


def _build_paper_markdown(paper: Paper, index: int) -> str:
    links = []
    if paper.url:
        links.append(f"[Abstract]({paper.url})")
    if paper.pdf_url:
        links.append(f"[PDF]({paper.pdf_url})")

    return (
        f"**{index}. {paper.title or 'Untitled'}**\n"
        f"{_format_source_label(paper.source)} {_format_score(paper.score)}\n"
        f"**Authors:** {_format_authors(paper.authors)}\n"
        f"> {_truncate_summary(paper.tldr or paper.abstract)}\n"
        f"{' | '.join(links) if links else 'No external links'}"
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

    header = {
        "title": {
            "tag": "plain_text",
            "content": f"Paper Digest | {today}",
        },
        "template": "blue",
    }

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"Found **{paper_count}** ranked papers for today.\n"
                    f"**Sources:** {source_tags}\n"
                    f"**Generated:** `{generated_at}`"
                ),
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
                        "content": _build_paper_markdown(paper, i),
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
                    "content": "No ranked papers were selected for this run.",
                },
            }
        )

    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": f"Powered by {bot_name}"},
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
