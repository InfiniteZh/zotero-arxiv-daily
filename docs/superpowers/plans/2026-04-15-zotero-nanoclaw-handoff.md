# Zotero to NanoClaw Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default "generate TLDR + send email" path with a configurable NanoClaw batch handoff while preserving the existing retrieval, filtering, reranking, and top `N` selection behavior.

**Architecture:** Keep the existing retrieval and ranking pipeline intact in `Executor`, add a small `publisher` module that serializes the final ranked paper list into a stable JSON payload and POSTs it to NanoClaw, and gate the final delivery path behind `delivery.mode`. Preserve the legacy email path in code as a rollback option, but make `nanoclaw` the intended mode for this fork.

**Tech Stack:** Python 3.13, Hydra/OmegaConf, Loguru, pytest, standard-library HTTP (`urllib.request`) for outbound POST, existing dataclasses in `protocol.py`.

---

## File Structure

### Files to modify

- `config/base.yaml`
  Purpose: define the new `delivery` and `nanoclaw` config blocks in the canonical config schema.
- `config/custom.yaml`
  Purpose: set fork-level defaults for `delivery.mode` and NanoClaw endpoint/token environment variable wiring.
- `src/zotero_arxiv_daily/executor.py`
  Purpose: branch the post-rerank flow by delivery mode while leaving retrieval and ranking behavior untouched.
- `tests/conftest.py`
  Purpose: add default config overrides so tests can compose the new config tree without missing fields.
- `tests/test_executor.py`
  Purpose: assert `Executor.run()` publishes to NanoClaw in `nanoclaw` mode and preserves the legacy email path in `email` mode.

### Files to create

- `src/zotero_arxiv_daily/publisher.py`
  Purpose: build a stable NanoClaw batch payload and publish it with retries and explicit error handling.
- `tests/test_publisher.py`
  Purpose: test payload construction, `full_text` toggling, auth/client/server error handling, and retry behavior.

### Files intentionally not touched in the first implementation

- `src/zotero_arxiv_daily/retriever/*`
- `src/zotero_arxiv_daily/reranker/*`
- `src/zotero_arxiv_daily/protocol.py`
- `src/zotero_arxiv_daily/construct_email.py`
- `src/zotero_arxiv_daily/utils.py`

The goal is to keep the integration boundary narrow so future upstream rebases remain low-conflict.

### Delivery mode contract

- `delivery.mode == "email"` keeps the current behavior.
- `delivery.mode == "nanoclaw"` skips TLDR generation, affiliation extraction, HTML rendering, and SMTP sending, then publishes the ranked batch to NanoClaw.

## Task 1: Add Config Schema and Test Defaults

**Files:**
- Modify: `config/base.yaml`
- Modify: `config/custom.yaml`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Extend the shared pytest config fixture with NanoClaw defaults**

Add these overrides inside `tests/conftest.py` so every test can compose the config tree without missing keys:

```python
        cfg = compose(
            config_name="default",
            overrides=[
                "zotero.user_id=000000",
                "zotero.api_key=fake-zotero-key",
                "zotero.include_path=null",
                "zotero.ignore_path=null",
                "email.sender=test@example.com",
                "email.receiver=test@example.com",
                "email.smtp_server=localhost",
                "email.smtp_port=1025",
                "email.sender_password=test",
                "llm.api.key=sk-fake",
                "llm.api.base_url=http://localhost:30000/v1",
                "llm.generation_kwargs.model=gpt-4o-mini",
                "reranker.api.key=sk-fake",
                "reranker.api.base_url=http://localhost:30000/v1",
                "reranker.api.model=text-embedding-3-large",
                "source.arxiv.category=[cs.AI,cs.CV]",
                "executor.source=[arxiv]",
                "executor.reranker=api",
                "executor.debug=false",
                "executor.send_empty=false",
                "delivery.mode=email",
                "nanoclaw.enabled=false",
                "nanoclaw.endpoint=http://localhost:3000/api/paper-digests",
                "nanoclaw.token=test-nanoclaw-token",
                "nanoclaw.timeout=30",
                "nanoclaw.include_full_text=true",
                "nanoclaw.max_retries=3",
            ],
        )
```

- [ ] **Step 2: Update base config schema with delivery and NanoClaw blocks**

Append this section to `config/base.yaml` after `email` and before `llm`:

```yaml
delivery:
  mode: email # Delivery backend. Example: email or nanoclaw

nanoclaw:
  enabled: false # Whether NanoClaw handoff is enabled. Example: true
  endpoint: null # NanoClaw batch endpoint. Example: http://localhost:3000/api/paper-digests
  token: null # NanoClaw bearer token. Example: secret-token
  timeout: 30 # Request timeout in seconds. Example: 30
  include_full_text: true # Whether to include extracted full text in the payload. Example: true
  max_retries: 3 # Number of retries for 5xx and network failures. Example: 3
```

- [ ] **Step 3: Update fork-level custom config defaults**

Add this section to `config/custom.yaml` so this fork is wired for NanoClaw by default while still allowing overrides through env vars:

```yaml
delivery:
  mode: ${oc.env:DELIVERY_MODE,nanoclaw}

nanoclaw:
  enabled: ${oc.env:NANOCLAW_ENABLED,true}
  endpoint: ${oc.env:NANOCLAW_ENDPOINT,http://localhost:3000/api/paper-digests}
  token: ${oc.env:NANOCLAW_TOKEN,null}
  timeout: ${oc.env:NANOCLAW_TIMEOUT,30}
  include_full_text: ${oc.env:NANOCLAW_INCLUDE_FULL_TEXT,true}
  max_retries: ${oc.env:NANOCLAW_MAX_RETRIES,3}
```

- [ ] **Step 4: Run config-sensitive tests to verify Hydra still composes successfully**

Run:

```bash
uv run pytest tests/test_main.py tests/test_executor.py::test_normalize_path_patterns_accepts_none -v
```

Expected:

- `PASS` for both tests
- no Hydra composition errors about missing `delivery` or `nanoclaw`

- [ ] **Step 5: Commit**

```bash
git add config/base.yaml config/custom.yaml tests/conftest.py
git commit -m "config: add nanoclaw delivery settings"
```

## Task 2: Add Publisher Payload Builder with TDD

**Files:**
- Create: `tests/test_publisher.py`
- Create: `src/zotero_arxiv_daily/publisher.py`

- [ ] **Step 1: Write the failing payload-construction tests**

Create `tests/test_publisher.py` with these tests first:

```python
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.publisher import build_batch_payload


def test_build_batch_payload_serializes_ranked_papers(config):
    with open_dict(config):
        config.executor.source = ["arxiv", "biorxiv"]
        config.executor.max_paper_num = 20
        config.nanoclaw.include_full_text = True

    papers = [
        make_sample_paper(
            source="arxiv",
            title="Paper One",
            authors=["Alice", "Bob"],
            abstract="First abstract",
            url="https://arxiv.org/abs/1111.1111",
            pdf_url="https://arxiv.org/pdf/1111.1111",
            full_text="Full text one",
            score=9.1,
        ),
        make_sample_paper(
            source="biorxiv",
            title="Paper Two",
            authors=["Carol"],
            abstract="Second abstract",
            url="https://www.biorxiv.org/content/10.1101/123456v1",
            pdf_url="https://www.biorxiv.org/content/10.1101/123456v1.full.pdf",
            full_text=None,
            score=8.4,
        ),
    ]

    payload = build_batch_payload(config, papers, generated_at="2026-04-15T09:30:00+08:00")

    assert payload["schema_version"] == "1"
    assert payload["batch_id"] == "2026-04-15-arxiv-biorxiv-top20"
    assert payload["generated_at"] == "2026-04-15T09:30:00+08:00"
    assert payload["sources"] == ["arxiv", "biorxiv"]
    assert payload["paper_count"] == 2
    assert payload["papers"][0]["title"] == "Paper One"
    assert payload["papers"][0]["score"] == 9.1
    assert payload["papers"][0]["full_text"] == "Full text one"
    assert payload["papers"][1]["full_text"] is None


def test_build_batch_payload_omits_full_text_when_disabled(config):
    with open_dict(config):
        config.executor.source = ["arxiv"]
        config.executor.max_paper_num = 10
        config.nanoclaw.include_full_text = False

    payload = build_batch_payload(
        config,
        [make_sample_paper(full_text="Very long text")],
        generated_at="2026-04-15T09:30:00+08:00",
    )

    assert payload["batch_id"] == "2026-04-15-arxiv-top10"
    assert payload["papers"][0]["full_text"] is None
```

- [ ] **Step 2: Run the new tests to verify they fail for the expected reason**

Run:

```bash
uv run pytest tests/test_publisher.py -v
```

Expected:

- `FAIL`
- import error or missing symbol for `zotero_arxiv_daily.publisher.build_batch_payload`

- [ ] **Step 3: Write the minimal payload builder**

Create `src/zotero_arxiv_daily/publisher.py` with this initial implementation:

```python
from __future__ import annotations

from typing import Any

from omegaconf import DictConfig

from .protocol import Paper


def _build_batch_id(config: DictConfig, generated_at: str) -> str:
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


def build_batch_payload(
    config: DictConfig,
    papers: list[Paper],
    *,
    generated_at: str,
) -> dict[str, Any]:
    include_full_text = bool(config.nanoclaw.include_full_text)
    return {
        "schema_version": "1",
        "batch_id": _build_batch_id(config, generated_at),
        "generated_at": generated_at,
        "sources": list(config.executor.source),
        "paper_count": len(papers),
        "papers": [
            _paper_to_payload(paper, include_full_text)
            for paper in papers
        ],
    }
```

- [ ] **Step 4: Run the payload tests and verify they pass**

Run:

```bash
uv run pytest tests/test_publisher.py::test_build_batch_payload_serializes_ranked_papers tests/test_publisher.py::test_build_batch_payload_omits_full_text_when_disabled -v
```

Expected:

- both tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/zotero_arxiv_daily/publisher.py tests/test_publisher.py
git commit -m "feat: add nanoclaw payload builder"
```

## Task 3: Add HTTP Publish and Retry Behavior with TDD

**Files:**
- Modify: `tests/test_publisher.py`
- Modify: `src/zotero_arxiv_daily/publisher.py`

- [ ] **Step 1: Write the failing publish-path tests**

Append these tests to `tests/test_publisher.py`:

```python
import io
import json
from urllib.error import HTTPError, URLError

import pytest
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.publisher import publish_batch


def test_publish_batch_accepts_202_response(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.endpoint = "http://localhost:3000/api/paper-digests"
        config.nanoclaw.token = "secret-token"
        config.nanoclaw.max_retries = 3

    captured = {}

    class FakeResponse:
        status = 202

        def read(self):
            return b'{"ok": true, "status": "accepted"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request_obj, timeout):
        captured["url"] = request_obj.full_url
        captured["authorization"] = request_obj.headers["Authorization"]
        captured["timeout"] = timeout
        captured["body"] = json.loads(request_obj.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("zotero_arxiv_daily.publisher.urlopen", fake_urlopen)

    result = publish_batch(
        config,
        [make_sample_paper(title="Publish Me")],
        generated_at="2026-04-15T09:30:00+08:00",
    )

    assert result["status"] == "accepted"
    assert captured["url"] == "http://localhost:3000/api/paper-digests"
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 30
    assert captured["body"]["papers"][0]["title"] == "Publish Me"


def test_publish_batch_retries_once_on_500_then_succeeds(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.max_retries = 2

    attempts = {"count": 0}

    class FakeResponse:
        status = 200

        def read(self):
            return b'{"ok": true, "status": "duplicate"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request_obj, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                request_obj.full_url,
                500,
                "server error",
                hdrs=None,
                fp=io.BytesIO(b'{"ok": false, "error": "boom"}'),
            )
        return FakeResponse()

    monkeypatch.setattr("zotero_arxiv_daily.publisher.urlopen", fake_urlopen)
    monkeypatch.setattr("zotero_arxiv_daily.publisher.sleep", lambda _: None)

    result = publish_batch(
        config,
        [make_sample_paper()],
        generated_at="2026-04-15T09:30:00+08:00",
    )

    assert attempts["count"] == 2
    assert result["status"] == "duplicate"


def test_publish_batch_fails_fast_on_401(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.max_retries = 3

    def fake_urlopen(request_obj, timeout):
        raise HTTPError(
            request_obj.full_url,
            401,
            "unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"ok": false, "error": "bad token"}'),
        )

    monkeypatch.setattr("zotero_arxiv_daily.publisher.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="401"):
        publish_batch(
            config,
            [make_sample_paper()],
            generated_at="2026-04-15T09:30:00+08:00",
        )


def test_publish_batch_raises_after_network_retries(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.max_retries = 2

    attempts = {"count": 0}

    def fake_urlopen(request_obj, timeout):
        attempts["count"] += 1
        raise URLError("connection refused")

    monkeypatch.setattr("zotero_arxiv_daily.publisher.urlopen", fake_urlopen)
    monkeypatch.setattr("zotero_arxiv_daily.publisher.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="connection refused"):
        publish_batch(
            config,
            [make_sample_paper()],
            generated_at="2026-04-15T09:30:00+08:00",
        )

    assert attempts["count"] == 3
```

- [ ] **Step 2: Run the publish-path tests to verify the correct red state**

Run:

```bash
uv run pytest tests/test_publisher.py -v
```

Expected:

- payload tests still `PASS`
- publish tests `FAIL` because `publish_batch` is not implemented

- [ ] **Step 3: Implement the minimal HTTP publish path**

Extend `src/zotero_arxiv_daily/publisher.py` to:

```python
from __future__ import annotations

import json
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from omegaconf import DictConfig

from .protocol import Paper


def _validate_nanoclaw_config(config: DictConfig) -> None:
    if not config.nanoclaw.enabled:
        raise RuntimeError("NanoClaw delivery is disabled")
    if not config.nanoclaw.endpoint:
        raise RuntimeError("config.nanoclaw.endpoint is required")
    if not config.nanoclaw.token:
        raise RuntimeError("config.nanoclaw.token is required")


def _make_request(config: DictConfig, payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode("utf-8")
    return Request(
        config.nanoclaw.endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.nanoclaw.token}",
        },
    )


def _parse_response_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {"ok": True}
    return json.loads(raw_body.decode("utf-8"))


def publish_batch(
    config: DictConfig,
    papers: list[Paper],
    *,
    generated_at: str,
) -> dict[str, Any]:
    _validate_nanoclaw_config(config)
    payload = build_batch_payload(config, papers, generated_at=generated_at)
    max_retries = int(config.nanoclaw.max_retries)
    timeout = int(config.nanoclaw.timeout)

    for attempt in range(max_retries + 1):
        request_obj = _make_request(config, payload)
        try:
            with urlopen(request_obj, timeout=timeout) as response:
                body = _parse_response_body(response.read())
                logger.info(
                    "NanoClaw batch accepted: batch_id={} paper_count={}",
                    payload["batch_id"],
                    payload["paper_count"],
                )
                return body
        except HTTPError as exc:
            body = exc.read()
            message = body.decode("utf-8") if body else str(exc)
            if exc.code in (400, 401):
                raise RuntimeError(f"NanoClaw publish failed with {exc.code}: {message}") from exc
            if exc.code >= 500 and attempt < max_retries:
                logger.warning(
                    "NanoClaw publish retrying after {}: attempt={} batch_id={}",
                    exc.code,
                    attempt + 1,
                    payload["batch_id"],
                )
                sleep(1)
                continue
            raise RuntimeError(f"NanoClaw publish failed with {exc.code}: {message}") from exc
        except URLError as exc:
            if attempt < max_retries:
                logger.warning(
                    "NanoClaw publish network retry: attempt={} batch_id={} error={}",
                    attempt + 1,
                    payload["batch_id"],
                    exc,
                )
                sleep(1)
                continue
            raise RuntimeError(f"NanoClaw publish failed: {exc}") from exc

    raise RuntimeError("NanoClaw publish failed after retries")
```

- [ ] **Step 4: Run the publisher test file and verify green**

Run:

```bash
uv run pytest tests/test_publisher.py -v
```

Expected:

- all publisher tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/zotero_arxiv_daily/publisher.py tests/test_publisher.py
git commit -m "feat: add nanoclaw publisher transport"
```

## Task 4: Route Executor by Delivery Mode with TDD

**Files:**
- Modify: `tests/test_executor.py`
- Modify: `src/zotero_arxiv_daily/executor.py`

- [ ] **Step 1: Add failing executor-branching tests**

Append these tests to `tests/test_executor.py`:

```python
def test_run_nanoclaw_mode_publishes_ranked_batch(config, monkeypatch):
    from omegaconf import open_dict

    from tests.canned_responses import make_sample_paper, make_stub_openai_client, make_stub_zotero_client

    with open_dict(config):
        config.delivery.mode = "nanoclaw"
        config.nanoclaw.enabled = True
        config.executor.source = ["arxiv"]
        config.executor.reranker = "api"
        config.executor.max_paper_num = 1

    stub_zot = make_stub_zotero_client()
    monkeypatch.setattr("zotero_arxiv_daily.executor.zotero.Zotero", lambda *a, **kw: stub_zot)

    stub_client = make_stub_openai_client()
    monkeypatch.setattr("zotero_arxiv_daily.executor.OpenAI", lambda **kw: stub_client)
    monkeypatch.setattr("zotero_arxiv_daily.reranker.api.OpenAI", lambda **kw: stub_client)

    import zotero_arxiv_daily.retriever.arxiv_retriever  # noqa: F401
    from zotero_arxiv_daily.retriever.base import registered_retrievers

    retrieved = [
        make_sample_paper(title="Keep Me", score=None),
        make_sample_paper(title="Drop Me", score=None),
    ]
    monkeypatch.setattr(registered_retrievers["arxiv"], "retrieve_papers", lambda self: retrieved)
    monkeypatch.setattr("zotero_arxiv_daily.retriever.base.sleep", lambda _: None)

    published = {}

    def fake_publish(config_obj, papers, *, generated_at):
        published["titles"] = [paper.title for paper in papers]
        published["generated_at"] = generated_at
        return {"ok": True, "status": "accepted"}

    monkeypatch.setattr("zotero_arxiv_daily.executor.publish_batch", fake_publish)
    monkeypatch.setattr("zotero_arxiv_daily.executor.render_email", lambda papers: (_ for _ in ()).throw(AssertionError("render_email should not be called")))
    monkeypatch.setattr("zotero_arxiv_daily.executor.send_email", lambda cfg, html: (_ for _ in ()).throw(AssertionError("send_email should not be called")))

    executor = Executor(config)
    executor.run()

    assert published["titles"] == ["Keep Me"]
    assert published["generated_at"]


def test_run_email_mode_keeps_legacy_email_flow(config, monkeypatch):
    import smtplib

    from omegaconf import open_dict
    from tests.canned_responses import make_sample_paper, make_stub_openai_client, make_stub_smtp, make_stub_zotero_client

    with open_dict(config):
        config.delivery.mode = "email"
        config.executor.source = ["arxiv"]
        config.executor.reranker = "api"
        config.executor.send_empty = False

    stub_zot = make_stub_zotero_client()
    monkeypatch.setattr("zotero_arxiv_daily.executor.zotero.Zotero", lambda *a, **kw: stub_zot)

    stub_client = make_stub_openai_client()
    monkeypatch.setattr("zotero_arxiv_daily.executor.OpenAI", lambda **kw: stub_client)
    monkeypatch.setattr("zotero_arxiv_daily.reranker.api.OpenAI", lambda **kw: stub_client)

    import zotero_arxiv_daily.retriever.arxiv_retriever  # noqa: F401
    from zotero_arxiv_daily.retriever.base import registered_retrievers

    monkeypatch.setattr(registered_retrievers["arxiv"], "retrieve_papers", lambda self: [make_sample_paper()])
    monkeypatch.setattr("zotero_arxiv_daily.retriever.base.sleep", lambda _: None)
    monkeypatch.setattr("zotero_arxiv_daily.executor.publish_batch", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("publish_batch should not be called")))

    sent = []
    monkeypatch.setattr(smtplib, "SMTP", make_stub_smtp(sent))

    executor = Executor(config)
    executor.run()

    assert len(sent) == 1
```

- [ ] **Step 2: Run the new executor tests and verify they fail before implementation**

Run:

```bash
uv run pytest tests/test_executor.py::test_run_nanoclaw_mode_publishes_ranked_batch tests/test_executor.py::test_run_email_mode_keeps_legacy_email_flow -v
```

Expected:

- `test_run_email_mode_keeps_legacy_email_flow` may still pass
- `test_run_nanoclaw_mode_publishes_ranked_batch` should fail because `publish_batch` is not imported or used yet

- [ ] **Step 3: Import and call the NanoClaw publisher from the executor**

Update the imports at the top of `src/zotero_arxiv_daily/executor.py`:

```python
from datetime import datetime

from loguru import logger
from omegaconf import DictConfig, ListConfig
from openai import OpenAI
from pyzotero import zotero
from tqdm import tqdm

from .construct_email import render_email
from .protocol import CorpusPaper
from .publisher import publish_batch
from .reranker import get_reranker_cls
from .retriever import get_retriever_cls
from .utils import glob_match, send_email
```

Then replace the post-rerank branch inside `Executor.run()` with:

```python
        reranked_papers = []
        if len(all_papers) > 0:
            logger.info("Reranking papers...")
            reranked_papers = self.reranker.rerank(all_papers, corpus)
            reranked_papers = reranked_papers[:self.config.executor.max_paper_num]
        elif not self.config.executor.send_empty:
            logger.info("No new papers found. No delivery will be sent.")
            return

        delivery_mode = self.config.delivery.mode
        if delivery_mode == "nanoclaw":
            if len(reranked_papers) == 0:
                logger.info("No ranked papers available for NanoClaw handoff.")
                return
            generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
            logger.info("Publishing ranked papers to NanoClaw...")
            publish_batch(self.config, reranked_papers, generated_at=generated_at)
            logger.info("NanoClaw publish succeeded")
            return

        logger.info("Generating TLDR and affiliations...")
        for p in tqdm(reranked_papers):
            p.generate_tldr(self.openai_client, self.config.llm)
            p.generate_affiliations(self.openai_client, self.config.llm)
        logger.info("Sending email...")
        email_content = render_email(reranked_papers)
        send_email(self.config, email_content)
        logger.info("Email sent successfully")
```

- [ ] **Step 4: Run the focused executor tests and then the full executor suite**

Run:

```bash
uv run pytest tests/test_executor.py::test_run_nanoclaw_mode_publishes_ranked_batch tests/test_executor.py::test_run_email_mode_keeps_legacy_email_flow -v
uv run pytest tests/test_executor.py -v
```

Expected:

- both focused tests `PASS`
- full executor suite `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/zotero_arxiv_daily/executor.py tests/test_executor.py
git commit -m "feat: route delivery through nanoclaw publisher"
```

## Task 5: Run Full Verification and Document Runtime Inputs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short NanoClaw delivery section to the README**

Update the usage/configuration documentation in `README.md` with a small fork-specific section like:

```md
## NanoClaw Delivery

This fork can hand off reranked papers to NanoClaw instead of generating email directly.

Required variables:

- `DELIVERY_MODE=nanoclaw`
- `NANOCLAW_ENDPOINT=http://localhost:3000/api/paper-digests`
- `NANOCLAW_TOKEN=...`

Optional variables:

- `NANOCLAW_TIMEOUT=30`
- `NANOCLAW_INCLUDE_FULL_TEXT=true`
- `NANOCLAW_MAX_RETRIES=3`

The number of papers sent to NanoClaw is still controlled by `executor.max_paper_num`.
```

- [ ] **Step 2: Run the publisher, executor, and entry-point tests together**

Run:

```bash
uv run pytest tests/test_publisher.py tests/test_executor.py tests/test_main.py -v
```

Expected:

- all listed tests `PASS`
- no failures related to missing config keys or broken legacy email mode

- [ ] **Step 3: Run the default test suite**

Run:

```bash
uv run pytest
```

Expected:

- full non-slow suite `PASS`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document nanoclaw delivery mode"
```

## Self-Review

### Spec coverage

- Preserve retrieval and reranking behavior:
  Covered by leaving retriever/reranker code unchanged and only branching after truncation in Task 4.
- Publish one top `N` batch to NanoClaw:
  Covered by payload builder and publish transport in Tasks 2 and 3.
- Stable, class-independent payload:
  Covered by explicit JSON serialization in Task 2.
- Keep rollback possible:
  Covered by `delivery.mode` and legacy email path preservation in Tasks 1 and 4.
- Configurable `Top N`:
  Covered by continuing to use `config.executor.max_paper_num` in Task 2 and Task 4.
- Minimal upstream merge surface:
  Covered by isolating transport logic in `publisher.py` and avoiding retriever/reranker/protocol edits across all tasks.

### Placeholder scan

Checked for banned placeholders such as `TODO`, `TBD`, "appropriate error handling", and "write tests for the above". None remain.

### Type consistency

- `build_batch_payload(config, papers, generated_at=...)` is introduced in Task 2 and reused consistently in Task 3.
- `publish_batch(config, papers, generated_at=...)` is introduced in Task 3 and used with the same signature in Task 4.
- `delivery.mode` and `nanoclaw.*` config fields are defined in Task 1 and used consistently in later tasks.

