# Feishu-First Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Feishu card delivery the default path, improve card rendering, and keep NanoClaw/email as optional backends.

**Architecture:** Keep the current executor branching model, wire Feishu settings into config defaults, and upgrade the existing Feishu publisher to emit richer `lark_md` blocks. Validate behavior with focused unit tests around payload generation and executor routing.

**Tech Stack:** Python, Hydra/OmegaConf, pytest, Feishu webhook interactive cards

---

### Task 1: Add failing tests for Feishu publishing

**Files:**
- Create: `tests/test_feishu_publisher.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_feishu_card_contains_summary_and_links():
    ...

def test_publish_to_feishu_accepts_success_response():
    ...

def test_run_feishu_mode_publishes_ranked_batch():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_feishu_publisher.py tests/test_executor.py -q`
Expected: FAIL because the current payload/content/default config does not match the new Feishu-first behavior.

- [ ] **Step 3: Add only the minimal fixtures needed**

```python
"feishu.enabled=true"
"feishu.webhook_url=https://example.invalid/hook"
"feishu.bot_name=Test Bot"
"feishu.timeout=30"
"feishu.max_retries=3"
```

- [ ] **Step 4: Re-run tests to confirm the same intended failures**

Run: `pytest tests/test_feishu_publisher.py tests/test_executor.py -q`
Expected: Still FAIL, but now on behavior rather than missing config.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_executor.py tests/test_feishu_publisher.py
git commit -m "test: add feishu delivery coverage"
```

### Task 2: Implement Feishu-first runtime behavior

**Files:**
- Modify: `src/zotero_arxiv_daily/feishu_publisher.py`
- Modify: `src/zotero_arxiv_daily/executor.py`
- Modify: `config/custom.yaml`

- [ ] **Step 1: Implement richer Feishu card rendering**

```python
def _build_paper_markdown(...): ...
def _build_feishu_card(...): ...
```

- [ ] **Step 2: Keep executor routing explicit**

```python
if delivery_mode == "feishu":
    ...
elif delivery_mode == "nanoclaw":
    ...
elif delivery_mode == "email":
    ...
```

- [ ] **Step 3: Set Feishu as the default delivery mode and map Feishu env vars**

```yaml
delivery:
  mode: ${oc.env:DELIVERY_MODE,feishu}

feishu:
  enabled: ${oc.decode:${oc.env:FEISHU_ENABLED,true}}
  webhook_url: ${oc.env:FEISHU_WEBHOOK_URL,null}
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_feishu_publisher.py tests/test_executor.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_arxiv_daily/feishu_publisher.py src/zotero_arxiv_daily/executor.py config/custom.yaml
git commit -m "feat: make feishu the default delivery backend"
```

### Task 3: Update examples and docs

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Update env examples to Feishu-first**

```dotenv
DELIVERY_MODE=feishu
FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=
```

- [ ] **Step 2: Update Docker env passthrough**

```yaml
- FEISHU_ENABLED=${FEISHU_ENABLED:-true}
- FEISHU_WEBHOOK_URL=${FEISHU_WEBHOOK_URL:-}
```

- [ ] **Step 3: Update README quick start and delivery docs**

```markdown
### Feishu Delivery
...
### Optional NanoClaw Delivery
...
```

- [ ] **Step 4: Run a wider regression slice**

Run: `pytest tests/test_feishu_publisher.py tests/test_executor.py tests/test_main.py tests/test_publisher.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .env.example docker-compose.yml README.md
git commit -m "docs: switch examples to feishu-first delivery"
```
