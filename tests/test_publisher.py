import io
import json
from urllib.error import HTTPError, URLError

import pytest
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.publisher import build_batch_payload, publish_batch
from zotero_arxiv_daily import publisher


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


def test_publish_batch_accepts_202_response(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.endpoint = "https://nanoclaw.example/api/paper-digests"
        config.nanoclaw.token = "secret-token"
        config.nanoclaw.timeout = 17
        config.executor.source = ["arxiv"]
        config.executor.max_paper_num = 10

    paper = make_sample_paper(title="Publishable Paper")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))

        class FakeResponse:
            status = 202

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {"status": "accepted", "batch_id": "2026-04-15-arxiv-top10"}
                ).encode("utf-8")

        captured["status"] = 202
        return FakeResponse()

    monkeypatch.setattr(publisher, "urlopen", fake_urlopen)

    response = publish_batch(config, [paper], generated_at="2026-04-15T09:30:00+08:00")

    assert response["status"] == "accepted"
    assert captured["status"] == 202
    assert captured["url"] == "https://nanoclaw.example/api/paper-digests"
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 17
    assert captured["body"]["batch_id"] == "2026-04-15-arxiv-top10"
    assert captured["body"]["paper_count"] == 1


def test_publish_batch_retries_once_on_500_then_succeeds(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.endpoint = "https://nanoclaw.example/api/paper-digests"
        config.nanoclaw.token = "secret-token"
        config.nanoclaw.timeout = 17
        config.nanoclaw.max_retries = 2

    paper = make_sample_paper(title="Retryable Paper")
    attempts = 0

    def fake_sleep(seconds):
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
        return io.BytesIO(json.dumps({"status": "duplicate", "batch_id": "2026-04-15-arxiv-top10"}).encode("utf-8"))

    monkeypatch.setattr(publisher, "urlopen", fake_urlopen)
    monkeypatch.setattr(publisher, "sleep", fake_sleep)

    response = publish_batch(config, [paper], generated_at="2026-04-15T09:30:00+08:00")

    assert response["status"] == "duplicate"
    assert attempts == 2


def test_publish_batch_fails_fast_on_401(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.endpoint = "https://nanoclaw.example/api/paper-digests"
        config.nanoclaw.token = "secret-token"

    paper = make_sample_paper(title="Unauthorized Paper")

    def fake_urlopen(request, timeout=None):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b"unauthorized"),
        )

    monkeypatch.setattr(publisher, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="401"):
        publish_batch(config, [paper], generated_at="2026-04-15T09:30:00+08:00")


def test_publish_batch_raises_after_network_retries(config, monkeypatch):
    with open_dict(config):
        config.nanoclaw.enabled = True
        config.nanoclaw.endpoint = "https://nanoclaw.example/api/paper-digests"
        config.nanoclaw.token = "secret-token"
        config.nanoclaw.max_retries = 2

    paper = make_sample_paper(title="Unreachable Paper")
    attempts = 0

    def fake_sleep(seconds):
        return None

    def fake_urlopen(request, timeout=None):
        nonlocal attempts
        attempts += 1
        raise URLError("connection lost")

    monkeypatch.setattr(publisher, "urlopen", fake_urlopen)
    monkeypatch.setattr(publisher, "sleep", fake_sleep)

    with pytest.raises(RuntimeError):
        publish_batch(config, [paper], generated_at="2026-04-15T09:30:00+08:00")

    assert attempts == 3
