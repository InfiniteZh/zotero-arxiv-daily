# Feishu-First Delivery Design

## Goal

Change the project's default delivery path from NanoClaw/email-oriented configuration to direct Feishu card delivery, while keeping NanoClaw and email as supported but non-default backends.

## Scope

- Default `delivery.mode` becomes `feishu`
- Environment-driven Feishu config is added to runtime config
- Feishu card rendering is improved to use richer `lark_md` content
- Docker and example env files become Feishu-first
- README guidance becomes Feishu-first
- Existing NanoClaw and email code paths remain available

## Non-Goals

- Introducing Feishu CardKit templates or template variables
- Adding user mentions, uploaded images, or table components
- Reworking the reranker or retrieval pipeline
- Removing NanoClaw support

## Design

### Delivery defaults

`config/custom.yaml` will default `delivery.mode` to `feishu`. Feishu settings will be read from environment variables:

- `FEISHU_ENABLED`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_BOT_NAME`
- `FEISHU_TIMEOUT`
- `FEISHU_MAX_RETRIES`

NanoClaw remains configurable, but no longer appears as the primary path in defaults and examples.

### Feishu card structure

The project will keep webhook-based interactive card delivery. The card body will be composed from `lark_md` blocks so it can take advantage of Feishu rich text syntax without requiring template assets.

Card layout:

1. Header with date and batch summary
2. Intro block showing source list and number of selected papers
3. One section per paper, separated by horizontal rules
4. Footer note showing bot name and generation metadata

Each paper block will include:

- Ranked title in bold
- Source label rendered with `<text_tag>`
- Score
- Authors
- A short summary from `paper.tldr`, falling back to abstract
- Clickable links for abstract/PDF

The renderer will avoid syntax that requires extra permissions or assets, such as `@all`, uploaded images, or CardKit variables.

### Testing

Add tests for:

- Feishu card payload construction
- Feishu webhook publish success/retry behavior
- Executor Feishu mode routing

Existing tests for NanoClaw and email stay unchanged.

### Documentation

`.env.example`, `docker-compose.yml`, and README will be updated so a user can configure Feishu delivery first, while NanoClaw remains listed as an optional backend.
