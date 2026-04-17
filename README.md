<p align="center">
  <a href="" rel="noopener">
 <img width=200px height=200px src="assets/logo.svg" alt="logo"></a>
</p>

<h3 align="center">Zotero-arXiv-Daily</h3>

<div align="center">

  [![Status](https://img.shields.io/badge/status-active-success.svg)]()
  ![Stars](https://img.shields.io/github/stars/TideDra/zotero-arxiv-daily?style=flat)
  [![GitHub Issues](https://img.shields.io/github/issues/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/issues)
  [![GitHub Pull Requests](https://img.shields.io/github/issues-pr/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/pulls)
  [![License](https://img.shields.io/github/license/TideDra/zotero-arxiv-daily)](/LICENSE)
  [<img src="https://api.gitsponsors.com/api/badge/img?id=893025857" height="20">](https://api.gitsponsors.com/api/badge/link?p=PKMtRut1dWWuC1oFdJweyDSvJg454/GkdIx4IinvBblaX2AY4rQ7FYKAK1ZjApoiNhYEeduIEhfeZVIwoIVlvcwdJXVFD2nV2EE5j6lYXaT/RHrcsQbFl3aKe1F3hliP26OMayXOoZVDidl05wj+yg==)

</div>

---

<p align="center"> Recommend new arxiv papers of your interest daily according to your Zotero library.
    <br> 
</p>

> [!IMPORTANT]
> Please keep an eye on this repo, and merge your forked repo in time when there is any update of this upstream, in order to enjoy new features and fix found bugs.

## 🧐 About <a name = "about"></a>

> Track new scientific researches of your interest by just forking (and staring) this repo!😊

*Zotero-arXiv-Daily* finds arxiv papers that may attract you based on the context of your Zotero library, and then sends the result to Feishu cards by default. It can be deployed as Github Action Workflow with **zero cost**, **no installation**, and **few configuration** of Github Action environment variables for daily **automatic** delivery.

## ✨ Features
- Totally free! All the calculation can be done in the Github Action runner locally within its quota (for public repo).
- AI-generated TL;DR for you to quickly pick up target papers.
- Affiliations of the paper are resolved and presented.
- Links of abstract and PDF presented in Feishu cards.
- List of papers sorted by relevance with your recent research interest.
- Fast deployment via fork this repo and set environment variables in the Github Action Page.
- Support LLM API for generating TL;DR of papers.
- Ignore unwanted Zotero papers using a list of glob patterns.
- Support multiple sources of papers to retrieve:
  - arxiv
  - biorxiv
  - medrxiv

## 📷 Screenshot
![screenshot](./assets/screenshot.png)

## 🚀 Usage
### Quick Start
1. Fork (and star😘) this repo.
![fork](./assets/fork.png)

2. Set Github Action environment variables.
![secrets](./assets/secrets.png)

Below are the core secrets you need for the default Feishu flow. They are invisible to anyone including you once they are set, for security.

| Key |Description | Example |
| :---  | :---  | :--- |
| ZOTERO_ID  | User ID of your Zotero account. **User ID is not your username, but a sequence of numbers**Get your ID from [here](https://www.zotero.org/settings/security). You can find it at the position shown in this [screenshot](https://github.com/TideDra/zotero-arxiv-daily/blob/main/assets/userid.png). | 12345678  |
| ZOTERO_KEY | An Zotero API key with read access. Get a key from [here](https://www.zotero.org/settings/security).  | AB5tZ877P2j7Sm2Mragq041H   |
| FEISHU_WEBHOOK_URL | Webhook URL of your Feishu bot for interactive card delivery. | https://open.feishu.cn/open-apis/bot/v2/hook/xxx |
| OPENAI_API_KEY | API Key when using the API to access LLMs. You can get FREE API for using advanced open source LLMs in [SiliconFlow](https://cloud.siliconflow.cn/i/b3XhBRAm). | sk-xxx |
| OPENAI_API_BASE | API URL when using the API to access LLMs. | https://api.siliconflow.cn/v1 |

Then you should also set a public variable `CUSTOM_CONFIG` for your custom configuration.
![vars](./assets/repo_var.png)
![custom_config](./assets/config_var.png)
Paste the following content into the value of `CUSTOM_CONFIG` variable:
```yaml
zotero:
  user_id: ${oc.env:ZOTERO_ID}
  api_key: ${oc.env:ZOTERO_KEY}
  include_path: null # Or e.g. ["2026/survey/**", "2026/reading-group/**"]

delivery:
  mode: ${oc.env:DELIVERY_MODE,feishu}

feishu:
  enabled: ${oc.decode:${oc.env:FEISHU_ENABLED,true}}
  webhook_url: ${oc.env:FEISHU_WEBHOOK_URL}
  bot_name: ${oc.env:FEISHU_BOT_NAME,arXiv Daily Bot}
  timeout: ${oc.decode:${oc.env:FEISHU_TIMEOUT,30}}
  max_retries: ${oc.decode:${oc.env:FEISHU_MAX_RETRIES,3}}

llm:
  api:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: ${oc.env:OPENAI_API_BASE}
  generation_kwargs:
    model: gpt-4o-mini

source:
  arxiv:
    category: ["cs.AI","cs.CV","cs.LG","cs.CL"]
    include_cross_list: false # Set to true to include arXiv cross-list papers in these categories.

executor:
  debug: ${oc.decode:${oc.env:DEBUG,false}}
  source: ['arxiv']
```
Set `source.arxiv.include_cross_list: true` if you want cross-listed papers included.

### Feishu Card Delivery

This fork now delivers reranked papers to Feishu cards by default.

Supported env vars:
- `DELIVERY_MODE=feishu` (default)
- `FEISHU_ENABLED=true` (default)
- `FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...`
- `FEISHU_BOT_NAME=arXiv Daily Bot`
- `FEISHU_TIMEOUT=30`
- `FEISHU_MAX_RETRIES=3`

Cards are sent as webhook-based interactive cards. The card body uses Feishu `lark_md` rich text, including:
- ranked title
- source tag
- score
- authors
- summary
- abstract/PDF links

The number of papers sent to Feishu is still controlled by `executor.max_paper_num`.

### Optional NanoClaw Delivery

NanoClaw remains supported as an optional backend.

Supported env vars:
- `DELIVERY_MODE=nanoclaw`
- `NANOCLAW_ENABLED=true`
- `NANOCLAW_ENDPOINT=http://localhost:3000/api/paper-digests`
- `NANOCLAW_TIMEOUT=30`
- `NANOCLAW_INCLUDE_FULL_TEXT=true`
- `NANOCLAW_MAX_RETRIES=3`
- `NANOCLAW_TOKEN=...`

> [!NOTE]
> When running inside Docker, use `host.docker.internal` instead of `localhost` if NanoClaw is running on the host machine.
> [!NOTE]
> `${oc.env:XXX,yyy}` means the value of the environment variable `XXX`. If the variable is not set, the default value `yyy` will be used.

Here is the full configuration, `???` means the value must be filled in:
```yaml
zotero:
  user_id: ??? # User ID of your Zotero account.
  api_key: ??? # An Zotero API key with read access.
  include_path: null # A list of glob patterns marking the Zotero collections that should be included. Example: ["2026/survey/**", "2026/reading-group/**"]

source:
  arxiv:
    category: null # The categories of target arxiv papers. Find the abbr of your research area from [here](https://arxiv.org/category_taxonomy). Example: ["cs.AI","cs.CV","cs.LG","cs.CL"]
    include_cross_list: false # Whether to include arXiv cross-list papers in subscribed categories. Example: true
  biorxiv:
    category: null # The categories of target biorxiv papers. Find categories from [here](https://www.biorxiv.org/). Example: ["biochemistry","animal behavior and cognition"]
  medrxiv:
    category: null # The categories of target medrxiv papers. Find categories from [here](https://www.medrxiv.org/) Example: ["psychiatry and clinical psychology", "neurology"]

email:
  sender: ??? # The email account of the SMTP server that sends you email. Example: abc@qq.com
  receiver: ??? # The email account that receives the paper list. Example: abc@outlook.com
  smtp_server: ??? # The SMTP server that sends the email. Ask your email provider (Gmail, QQ, Outlook, ...) for its SMTP server. Example: smtp.qq.com
  smtp_port: ??? # The port of SMTP server. Example: 465
  sender_password: ??? # The password of the sender account. Note that it's not necessarily the password for logging in the e-mail client, but the authentication code for SMTP service. Ask your email provider for this. Example: abcdefghijklmn

delivery:
  mode: feishu # Delivery backend. Example: feishu, nanoclaw, or email

feishu:
  enabled: true # Whether Feishu publishing is enabled. Example: true
  webhook_url: ??? # Feishu webhook URL for sending cards. Example: https://open.feishu.cn/open-apis/bot/v2/hook/xxx
  bot_name: arXiv Daily Bot # Name of the bot displayed in Feishu. Example: arXiv Daily Bot
  timeout: 30 # Request timeout in seconds. Example: 30
  max_retries: 3 # Number of retries for network failures. Example: 3

nanoclaw:
  enabled: false # Whether NanoClaw handoff is enabled. Example: true
  endpoint: null # NanoClaw batch endpoint. Example: http://host.docker.internal:3000/api/paper-digests
  token: null # NanoClaw bearer token. Example: secret-token
  timeout: 30 # Request timeout in seconds. Example: 30
  include_full_text: true # Whether to include extracted full text in the payload. Example: true
  max_retries: 3 # Number of retries for 5xx and network failures. Example: 3

llm:
  api:
    key: ??? # API Key of your LLM API. Example: sk-xxx
    base_url: ??? # API URL of your LLM API. Example: https://api.openai.com/v1
  generation_kwargs:
  # Arguments for the LLM API. See [here](https://platform.openai.com/docs/api-reference/chat/create) for more details.
    max_tokens: 16384
    model: ???
  language: English # Preferred language for the TL;DR. Example: English

reranker:
  local:
    model: jinaai/jina-embeddings-v5-text-nano # The Hugging Face model name of the local embedding model. Example: jinaai/jina-embeddings-v5-text-nano
    encode_kwargs:
    # The kwargs for the encode method of the local embedding model. Details see [here](https://www.sbert.net/docs/package_reference/SentenceTransformer.html#sentence_transformers.SentenceTransformer.encode)
      task: retrieval
      prompt_name: document
  api:
    key: null # API Key of your embedding model API. Example: sk-xxx
    base_url: null # API URL of your embedding model API. Example: https://api.openai.com/v1
    model: null # The model name of the embedding model. Example: text-embedding-3-large
    batch_size: null # The batch size for embedding API requests. Adjust to match your provider's limit. Example: 64

executor:
  debug: false # Whether to use debug mode. Example: true
  send_empty: false # Whether to send an empty email even if no new papers today. Example: true
  max_paper_num: 100 # The maximum number of the papers presented in the email. Example: 100
  source: ??? # The sources of papers to retrieve. Example: ['arxiv','biorxiv','medrxiv']
  reranker: local # The reranker to use. Example: 'local' or 'api'
```

That's all! Now you can test the workflow by manually triggering it:
![test](./assets/test.png)

> [!NOTE]
> The Test-Workflow Action is the debug version of the main workflow (Send-emails-daily), which always retrieve 5 arxiv papers regardless of the date. While the main workflow will be automatically triggered everyday and retrieve new papers released yesterday. There is no new arxiv paper at weekends and holiday, in which case you may see "No new papers found" in the log of main workflow.

Then check the log and the target Feishu group after it finishes.

By default, the main workflow runs on 22:00 UTC everyday. You can change this time by editting the workflow config `.github/workflows/main.yml`.

### Local Running
Supported by [uv](https://github.com/astral-sh/uv), this workflow can easily run on your local device if uv is installed:
```bash
# set all the environment variables
# export ZOTERO_ID=xxxx
# ...
cd zotero-arxiv-daily
uv run main.py
```

### Docker Deployment

You can also run this application in Docker, which is useful for self-hosting or running on a server.

#### Prerequisites

- Docker and Docker Compose installed
- A Feishu webhook URL (for Feishu card delivery)

#### Setup

1. Copy the environment template and configure your settings:
```bash
cp .env.example .env
# Edit .env with your configuration
```

2. Configure `config/custom.yaml` for your needs, or use environment variables directly.

3. Build and run:
```bash
docker-compose up -d
```

#### Feishu Card Delivery

To receive paper recommendations as Feishu cards:

1. Create a Feishu bot in your Feishu group or chat
2. Get the webhook URL from the bot settings
3. Set in your `.env`:
```
DELIVERY_MODE=feishu
FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
FEISHU_BOT_NAME=arXiv Daily Bot
```

#### Scheduling with Cron

Add to your crontab to run daily:
```bash
0 6 * * * cd /path/to/zotero-arxiv-daily && docker-compose run --rm zotero-arxiv-daily
```

Or use Docker's `--schedule` flag with a healthcheck for reliability.

## 🚀 Sync with the latest version
This project is in active development. You can subscribe this repo via `Watch` so that you can be notified once we publish new release.

![Watch](./assets/subscribe_release.png)


## 📖 How it works
*Zotero-arXiv-Daily* firstly retrieves all the papers in your Zotero library and all the papers released in the previous day, via corresponding API. Then it calculates the embedding of each paper's abstract via an embedding model. The score of a paper is its weighted average similarity over all your Zotero papers (newer paper added to the library has higher weight). The TLDR of each paper is generated by LLM, given the text extracted by pymupdf4llm.

## 📌 Limitations
- The recommendation algorithm is very simple, it may not accurately reflect your interest. Welcome better ideas for improving the algorithm!
- High `MAX_PAPER_NUM` can lead the execution time exceed the limitation of Github Action runner (6h per execution for public repo, and 2000 mins per month for private repo). Commonly, the quota given to public repo is definitely enough for individual use. If you have special requirements, you can deploy the workflow in your own server, or use a self-hosted Github Action runner, or pay for the exceeded execution time.

## 👯‍♂️ Contribution
Any issue and PR are welcomed! But remember that **each PR should merge to the `dev` branch**.

## 📃 License
Distributed under the AGPLv3 License. See `LICENSE` for detail.

## ❤️ Acknowledgement
- [pyzotero](https://github.com/urschrei/pyzotero)
- [arxiv](https://github.com/lukasschwab/arxiv.py)
- [sentence_transformers](https://github.com/UKPLab/sentence-transformers)

## ☕ Buy Me A Coffee
If you find this project helpful, welcome to sponsor me via WeChat or via [ko-fi](https://ko-fi.com/tidedra).
![wechat_qr](assets/wechat_sponsor.JPG)


## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=TideDra/zotero-arxiv-daily&type=Date)](https://star-history.com/#TideDra/zotero-arxiv-daily&Date)
