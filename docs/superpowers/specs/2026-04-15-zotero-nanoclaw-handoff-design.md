# Zotero to NanoClaw Handoff Design

Date: 2026-04-15
Status: Draft for review

## Overview

This design changes `zotero-arxiv-daily` from an end-to-end notification pipeline into an upstream paper-selection pipeline.

After the change, this repository will still:

- fetch the Zotero corpus
- retrieve new papers from configured sources
- rerank papers against the Zotero corpus
- keep only the top `N` papers using existing configuration

This repository will no longer be responsible for:

- generating AI TL;DRs
- extracting affiliations for notification output
- rendering HTML email as the primary delivery path
- sending daily notifications directly

Instead, `zotero-arxiv-daily` will publish one batch of reranked papers to a dedicated NanoClaw HTTP endpoint. NanoClaw will own downstream analysis, summarization, and Feishu card delivery.

## Goals

- Preserve the current retrieval and reranking behavior.
- Publish the final top `N` paper batch to NanoClaw in one request.
- Keep the integration surface small so upstream project updates remain easy to merge.
- Make the payload stable and independent from internal Python classes.
- Keep rollback possible during migration.

## Non-Goals

- Designing NanoClaw skills for paper analysis or summarization.
- Designing the final Feishu card layout.
- Replacing the reranker or changing recommendation behavior.
- Building a durable queue, job broker, or callback system in this repository.

## Current Project Shape

The current execution flow in `src/zotero_arxiv_daily/executor.py` is:

1. Fetch Zotero corpus.
2. Filter corpus by include and ignore path patterns.
3. Retrieve new papers from configured sources.
4. Rerank by similarity to the corpus.
5. Generate TL;DR and affiliations with an OpenAI-compatible LLM API.
6. Render HTML email and send it over SMTP.

The recommendation logic is the core value of this repository. The notification and summary generation steps are downstream concerns and can be delegated cleanly.

## Proposed Architecture

### Responsibility split

`zotero-arxiv-daily` owns:

- data retrieval
- corpus filtering
- ranking
- batch shaping
- HTTP delivery to NanoClaw

NanoClaw owns:

- batch acceptance
- AI analysis and summary generation
- orchestration through future skills
- Feishu card generation and delivery

### New flow

1. Fetch Zotero corpus.
2. Filter corpus.
3. Retrieve candidate papers.
4. Rerank papers.
5. Truncate to `config.executor.max_paper_num`.
6. Serialize one paper batch payload.
7. POST the batch to NanoClaw.
8. Treat `2xx` as success and stop.

### Delivery mode strategy

To reduce migration risk, delivery should become configurable instead of deleting the existing email path immediately.

Recommended initial mode values:

- `email`: keep current legacy behavior
- `nanoclaw`: publish the top `N` batch to NanoClaw

Default for the customized fork can be `nanoclaw`, while preserving `email` in code keeps future upstream merges simpler and gives an operational fallback.

## NanoClaw API Contract

### Endpoint

- Method: `POST`
- Path: `/api/paper-digests`
- Auth: `Authorization: Bearer <token>`
- Content type: `application/json`

### Request schema

```json
{
  "schema_version": "1",
  "batch_id": "2026-04-15-arxiv-top20",
  "generated_at": "2026-04-15T09:30:00+08:00",
  "sources": ["arxiv"],
  "paper_count": 20,
  "papers": [
    {
      "source": "arxiv",
      "title": "Paper title",
      "authors": ["Author A", "Author B"],
      "abstract": "Paper abstract",
      "url": "https://arxiv.org/abs/xxxx.xxxxx",
      "pdf_url": "https://arxiv.org/pdf/xxxx.xxxxx",
      "score": 8.7,
      "full_text": "optional extracted text"
    }
  ]
}
```

### Field semantics

- `schema_version`: contract version for forward compatibility.
- `batch_id`: unique batch key used for idempotency in NanoClaw.
- `generated_at`: time when the final ranked batch was produced.
- `sources`: configured sources that contributed to this batch.
- `paper_count`: number of papers included in the final payload.
- `papers`: final ranked and truncated paper list.

Each paper object contains only transport-safe, domain-level fields. NanoClaw must not depend on Python dataclass structure or repository-specific module names.

### Response semantics

Recommended NanoClaw behavior is asynchronous acceptance:

- `202 Accepted`

```json
{
  "ok": true,
  "batch_id": "2026-04-15-arxiv-top20",
  "status": "accepted"
}
```

Duplicate batch handling should be idempotent and easy for the caller:

- `200 OK`

```json
{
  "ok": true,
  "batch_id": "2026-04-15-arxiv-top20",
  "status": "duplicate"
}
```

Validation and auth errors:

- `400 Bad Request`
- `401 Unauthorized`

Temporary server-side failures:

- `5xx`

`zotero-arxiv-daily` will not wait for summaries or delivery results from NanoClaw.

## Payload Construction Rules

### Ranking and top `N`

The number of papers sent downstream remains controlled by the existing setting:

- `config.executor.max_paper_num`

No separate "top N for NanoClaw" setting will be introduced in the first version. The handoff payload uses the already-truncated ranked list.

### Full text inclusion

`full_text` should be configurable because it may be large and expensive to transmit.

Recommended setting:

- `config.nanoclaw.include_full_text: true | false`

Behavior:

- `true`: include extracted `full_text` when available
- `false`: send `null` or omit `full_text`

### Batch ID construction

`batch_id` should be deterministic enough for retries on the same run while still being human-readable.

Recommended shape:

- `<date>-<sources>-top<max_paper_num>`

If stronger uniqueness is needed later, a short hash of titles can be appended without changing the rest of the contract.

## Zotero Repository Changes

### New configuration block

Add a NanoClaw delivery block:

```yaml
delivery:
  mode: nanoclaw

nanoclaw:
  enabled: true
  endpoint: ${oc.env:NANOCLAW_ENDPOINT,null}
  token: ${oc.env:NANOCLAW_TOKEN,null}
  timeout: 30
  include_full_text: true
  max_retries: 3
```

Notes:

- `delivery.mode` selects between legacy email and NanoClaw handoff.
- `nanoclaw.enabled` is optional but useful for explicit validation.
- `endpoint` and `token` come from environment variables.
- `timeout` is request timeout in seconds.
- `max_retries` covers transient `5xx` or network failures.

### New module

Add a dedicated delivery or publisher module, for example:

- `src/zotero_arxiv_daily/publisher.py`

Responsibilities:

- build the batch payload from `list[Paper]`
- send the HTTP request
- implement retry policy
- raise clear exceptions for invalid config or failed delivery

This keeps transport logic out of `executor.py` and avoids modifying retriever, reranker, or protocol internals.

### Executor changes

`Executor.run()` should branch by delivery mode after ranking and truncation.

For `delivery.mode == "nanoclaw"`:

- skip `generate_tldr`
- skip `generate_affiliations`
- skip HTML rendering
- skip SMTP sending
- call the NanoClaw publisher with the final ranked list

For `delivery.mode == "email"`:

- keep the current legacy path unchanged

This is the lowest-risk migration path and preserves rollback.

## Error Handling

### Caller-side policy

`zotero-arxiv-daily` should treat responses as follows:

- `2xx`: success
- `400` or `401`: fail immediately with clear logs
- `5xx` or network timeout: retry up to `max_retries`

No callback polling, dead-letter queue, or local persistence layer will be added in this repository.

### Logging expectations

Logs should include:

- endpoint URL without leaking token
- batch id
- paper count
- retry attempt number
- final success or failure reason

## Testing Strategy

Add tests around the new handoff path without disturbing existing ranking tests.

Required coverage:

- payload serialization from ranked papers
- `max_paper_num` truncation respected in published payload
- `full_text` included or omitted based on config
- success on `202 Accepted`
- success on duplicate `200 OK`
- fail-fast on `400` and `401`
- retry on `5xx` and network errors
- executor routing by `delivery.mode`

Legacy email tests can remain while the fallback path still exists.

## Migration Strategy

### Phase 1

- Add NanoClaw publisher path.
- Keep email path in code.
- Configure this fork to use `delivery.mode: nanoclaw`.

### Phase 2

- Add NanoClaw endpoint implementation in the NanoClaw repository.
- Validate end-to-end batch acceptance.

### Phase 3

- Build NanoClaw skills for analysis and summarization.
- Add Feishu card generation on the NanoClaw side.

### Phase 4

If the NanoClaw pipeline becomes stable and the email fallback is no longer needed, the legacy path may be removed later. That cleanup is intentionally deferred because preserving the old branch minimizes merge pain with future upstream updates.

## File Impact

Expected first-round changes in this repository:

- `src/zotero_arxiv_daily/executor.py`
- `src/zotero_arxiv_daily/publisher.py` or similar new module
- config files under `config/`
- tests for the publisher and executor branching

Files intentionally avoided in the first round unless required:

- `retriever/*`
- `reranker/*`
- `protocol.py`

## Open Decisions Deferred to NanoClaw

These are intentionally outside the scope of this repository:

- exact NanoClaw endpoint implementation
- how NanoClaw stores or deduplicates accepted batches
- which skills analyze papers
- whether summaries are per-paper or per-batch first
- exact Feishu interactive card schema

## Recommendation

Implement the first version with:

- existing reranking preserved
- `delivery.mode` switch added
- a small dedicated NanoClaw publisher module
- asynchronous batch POST to NanoClaw
- legacy email path retained as fallback

This gives the cleanest system boundary and the best chance of keeping the fork easy to rebase onto future upstream releases.
