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
