import io
import json
import socket
from urllib.error import HTTPError, URLError

import pytest
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily import feishu_publisher
from zotero_arxiv_daily.feishu_publisher import _build_feishu_card, publish_to_feishu


def test_build_feishu_card_contains_summary_tags_and_links(config):
    with open_dict(config):
        config.feishu.bot_name = "Paper Bot"

    papers = [
        make_sample_paper(
            source="arxiv",
            title="Graph Reasoning for Agents",
            authors=["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
            abstract="An abstract about graph reasoning.",
            url="https://arxiv.org/abs/2604.00001",
            pdf_url="https://arxiv.org/pdf/2604.00001",
            tldr="A short ranked summary.",
            score=9.34,
        )
    ]

    payload = _build_feishu_card(config, papers, generated_at="2026-04-17T15:30:00+08:00")

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"].startswith("Paper Digest")

    elements = payload["card"]["elements"]
    joined = "\n".join(
        element["text"]["content"]
        for element in elements
        if element.get("tag") == "div" and "text" in element
    )

    assert "Found **1** ranked papers" in joined
    assert "<text_tag color='blue'>arXiv</text_tag>" in joined
    assert "**1. Graph Reasoning for Agents**" in joined
    assert "[Abstract](https://arxiv.org/abs/2604.00001)" in joined
    assert "[PDF](https://arxiv.org/pdf/2604.00001)" in joined
    assert "Alice, Bob, Carol, Dave, Eve et al." in joined


def test_publish_to_feishu_accepts_success_response(config, monkeypatch):
    with open_dict(config):
        config.feishu.enabled = True
        config.feishu.webhook_url = "https://feishu.example/hook"
        config.feishu.timeout = 15

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"code": 0, "msg": "ok"}).encode("utf-8")

        return FakeResponse()

    monkeypatch.setattr(feishu_publisher, "urlopen", fake_urlopen)

    response = publish_to_feishu(
        config,
        [make_sample_paper(title="Publishable Feishu Paper")],
        generated_at="2026-04-17T15:30:00+08:00",
    )

    assert response["code"] == 0
    assert captured["url"] == "https://feishu.example/hook"
    assert captured["timeout"] == 15
    assert captured["body"]["msg_type"] == "interactive"


def test_publish_to_feishu_retries_on_server_error(config, monkeypatch):
    with open_dict(config):
        config.feishu.enabled = True
        config.feishu.webhook_url = "https://feishu.example/hook"
        config.feishu.max_retries = 2

    attempts = 0

    def fake_sleep(_seconds):
        return None

    def fake_urlopen(request, timeout=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError(
                request.full_url,
                500,
                "Internal Server Error",
                hdrs=None,
                fp=io.BytesIO(b"server failed"),
            )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"code": 0, "msg": "ok"}).encode("utf-8")

        return FakeResponse()

    monkeypatch.setattr(feishu_publisher, "urlopen", fake_urlopen)
    monkeypatch.setattr(feishu_publisher, "sleep", fake_sleep)

    response = publish_to_feishu(
        config,
        [make_sample_paper(title="Retryable Feishu Paper")],
        generated_at="2026-04-17T15:30:00+08:00",
    )

    assert response["code"] == 0
    assert attempts == 2


def test_publish_to_feishu_raises_after_network_retries(config, monkeypatch):
    with open_dict(config):
        config.feishu.enabled = True
        config.feishu.webhook_url = "https://feishu.example/hook"
        config.feishu.max_retries = 2

    attempts = 0

    def fake_sleep(_seconds):
        return None

    def fake_urlopen(request, timeout=None):
        nonlocal attempts
        attempts += 1
        raise URLError("connection lost")

    monkeypatch.setattr(feishu_publisher, "urlopen", fake_urlopen)
    monkeypatch.setattr(feishu_publisher, "sleep", fake_sleep)

    with pytest.raises(RuntimeError):
        publish_to_feishu(
            config,
            [make_sample_paper(title="Broken Feishu Paper")],
            generated_at="2026-04-17T15:30:00+08:00",
        )

    assert attempts == 3


def test_publish_to_feishu_retries_read_timeout(config, monkeypatch):
    with open_dict(config):
        config.feishu.enabled = True
        config.feishu.webhook_url = "https://feishu.example/hook"
        config.feishu.max_retries = 2
        config.feishu.timeout = 15

    attempts = 0

    def fake_sleep(_seconds):
        return None

    def fake_urlopen(request, timeout=None):
        nonlocal attempts
        attempts += 1

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                if attempts < 3:
                    raise socket.timeout("timed out while reading response")
                return json.dumps({"code": 0, "msg": "ok"}).encode("utf-8")

        return FakeResponse()

    monkeypatch.setattr(feishu_publisher, "urlopen", fake_urlopen)
    monkeypatch.setattr(feishu_publisher, "sleep", fake_sleep)

    response = publish_to_feishu(
        config,
        [make_sample_paper(title="Slow Feishu Paper")],
        generated_at="2026-04-17T15:30:00+08:00",
    )

    assert response["code"] == 0
    assert attempts == 3
