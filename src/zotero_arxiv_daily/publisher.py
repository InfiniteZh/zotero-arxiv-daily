import json
from time import sleep
from typing import Any

from loguru import logger
from omegaconf import DictConfig
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def _validate_nanoclaw_config(config: DictConfig):
    if not bool(config.nanoclaw.enabled):
        raise RuntimeError("nanoclaw publishing is disabled")
    if not config.nanoclaw.endpoint:
        raise RuntimeError("nanoclaw endpoint is missing")
    if not config.nanoclaw.token:
        raise RuntimeError("nanoclaw token is missing")


def _make_request(config: DictConfig, payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.nanoclaw.token}",
    }
    return Request(config.nanoclaw.endpoint, data=body, headers=headers, method="POST")


def _parse_response_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {"ok": True}
    return json.loads(raw_body.decode("utf-8"))


def publish_batch(config: DictConfig, papers: list[Paper], *, generated_at: str) -> dict[str, Any]:
    _validate_nanoclaw_config(config)
    payload = build_batch_payload(config, papers, generated_at=generated_at)
    endpoint = str(config.nanoclaw.endpoint)
    batch_id = payload["batch_id"]
    max_retries = int(config.nanoclaw.max_retries)
    timeout = int(config.nanoclaw.timeout)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        request = _make_request(config, payload)
        try:
            with urlopen(request, timeout=timeout) as response:
                response_body = _parse_response_body(response.read())
            logger.info(
                "Accepted nanoclaw batch {} at {} with {} papers",
                batch_id,
                endpoint,
                payload["paper_count"],
            )
            return response_body
        except HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace") if hasattr(error, "read") else ""
            if error.code in (400, 401):
                logger.error(
                    "nanoclaw publish failed for batch {} at {} with HTTP {}",
                    batch_id,
                    endpoint,
                    error.code,
                )
                raise RuntimeError(f"nanoclaw publish failed with HTTP {error.code}: {body_text}")
            if error.code >= 500 and attempt < max_retries:
                last_error = error
                logger.warning(
                    "nanoclaw publish failed for batch {} at {} with HTTP {} on attempt {}/{}; retrying",
                    batch_id,
                    endpoint,
                    error.code,
                    attempt + 1,
                    max_retries + 1,
                )
                sleep(1)
                continue
            logger.error(
                "nanoclaw publish failed for batch {} at {} with HTTP {} after {}/{} attempts",
                batch_id,
                endpoint,
                error.code,
                attempt + 1,
                max_retries + 1,
            )
            raise RuntimeError(f"nanoclaw publish failed with HTTP {error.code}: {body_text}")
        except URLError as error:
            if attempt < max_retries:
                last_error = error
                logger.warning(
                    "nanoclaw publish failed for batch {} at {} with network error on attempt {}/{}; retrying",
                    batch_id,
                    endpoint,
                    attempt + 1,
                    max_retries + 1,
                )
                sleep(1)
                continue
            logger.error(
                "nanoclaw publish failed for batch {} at {} with network error after {}/{} attempts",
                batch_id,
                endpoint,
                attempt + 1,
                max_retries + 1,
            )
            raise RuntimeError(f"nanoclaw publish failed after network retries: {error}") from error

    if last_error is not None:
        logger.error("nanoclaw publish failed for batch {} at {}", batch_id, endpoint)
        raise RuntimeError(f"nanoclaw publish failed: {last_error}")
    raise RuntimeError("nanoclaw publish failed")
