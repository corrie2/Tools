# PaperForge

English | [中文](README.zh.md)

Convert academic PDF papers into a structured Obsidian knowledge base. Parses PDFs, extracts metadata, generates AI summaries / Q&A / glossaries, and builds citation graphs between papers.

## Features

- **PDF Parsing** — Docling (primary) with PyMuPDF + pdfplumber fallback
- **Metadata Extraction** — Title, authors, DOI, affiliations, language detection
- **AI Generation** — Summaries, Q&A pairs, glossaries, translations (any OpenAI-compatible LLM)
- **Citation Graph** — Reference extraction, DOI/title matching via CrossRef + Semantic Scholar, bidirectional citation links
- **Obsidian Output** — Markdown with YAML frontmatter, `[[wikilinks]]`, graph-view compatible
- **CLI** — 14 commands for ingestion, management, citation curation, and export

## Installation

```bash
git clone https://github.com/corrie2/Tools.git
cd Tools/PaperForge
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

**Windows (CMD):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
```

> Requires Python 3.10+. Use `uv pip install -e .` if you have [uv](https://github.com/astral-sh/uv).

## Quick Start

### 1. Set API Key

PaperForge works with any OpenAI-compatible provider. Set the environment variable for your provider:

```bash
# Mimo (recommended for Chinese users)
export MIMO_API_KEY="your-key"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"

# DeepSeek
export DEEPSEEK_API_KEY="your-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"

# OpenAI
export OPENAI_API_KEY="your-key"

# Ollama (local, no key needed)
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```

<details>
<summary>Windows (PowerShell)</summary>

```powershell
$env:MIMO_API_KEY = "your-key"
$env:MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
```
</details>

<details>
<summary>Windows (CMD)</summary>

```cmd
set MIMO_API_KEY=your-key
set MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
```
</details>

### 2. Configure

```bash
paperforge config --vault /path/to/obsidian-vault
```

This auto-detects API keys in your environment, lists available providers, lets you pick a model, and saves to `config.yaml`.

### 3. Ingest a Paper

```bash
paperforge ingest paper.pdf --vault /path/to/obsidian-vault
```

The pipeline runs 11 steps: PDF parse → metadata → figures → LLM summary/Q&A/glossary → translation → reference extraction → citation matching → index generation.

Use `--no-llm` to skip AI generation (parse only, much faster):

```bash
paperforge ingest paper.pdf --vault /path/to/obsidian-vault --no-llm
```

### 4. Browse

```bash
# List all papers
paperforge list --vault /path/to/obsidian-vault

# Show paper details
paperforge info paper-slug --vault /path/to/obsidian-vault

# Open in Obsidian — papers are under papers/<year>/<slug>/
```

## CLI Commands

### Core

| Command | Description |
|---------|-------------|
| `paperforge ingest <pdf>` | Ingest a PDF into the knowledge base |
| `paperforge config` | Auto-detect API keys and configure LLM |
| `paperforge list` | List all ingested papers |
| `paperforge info <slug>` | Show paper details |
| `paperforge status <slug>` | Show pipeline task statuses |
| `paperforge doctor` | Check environment and dependencies |

### Management

| Command | Description |
|---------|-------------|
| `paperforge remove <slug>` | Remove a paper and all its data |
| `paperforge rebuild-index` | Regenerate all index.md files |
| `paperforge open <slug>` | Open paper's index.md in default app |
| `paperforge export` | Export knowledge base as zip |

### LLM

| Command | Description |
|---------|-------------|
| `paperforge regenerate <slug> --type <type>` | Regenerate summary / qa / glossary / translation |
| `paperforge retry <slug>` | Retry all failed LLM tasks |

### Citations

| Command | Description |
|---------|-------------|
| `paperforge relink` | Re-scan all references and re-match |
| `paperforge confirm-ref <src> <tgt>` | Confirm a pending citation |
| `paperforge reject-ref <src> <tgt>` | Reject a pending citation |

### Options

- `--vault <path>` — Path to Obsidian vault (required for all commands)
- `--no-llm` — Skip LLM generation (ingest only)
- `--translate <mode>` — Translation mode: `off` / `abstract` / `full`
- `--year <year>` — Filter by year (list)
- `--status <status>` — Filter by task status (list)
- `--yes` / `-y` — Skip confirmation (remove)

## Configuration

Config file: `<vault>/paperforge/config.yaml`

```yaml
vault:
  papers_dir: papers        # Paper storage under vault
  data_dir: paperforge      # DB and config location

llm:
  provider: deepseek
  model: deepseek-v4-pro
  api_key_env: DEEPSEEK_API_KEY       # env var name (NOT the key itself)
  base_url_env: DEEPSEEK_BASE_URL     # optional
  timeout_seconds: 120
  max_retries: 3

parser:
  primary: docling
  fallback: pymupdf_pdfplumber
  save_figures: true
  save_tables: true

citation_matching:
  auto_confirm_doi: true
  auto_confirm_title_threshold: 95.0
  pending_title_threshold: 85.0
  require_year_match_for_title: true

translation:
  default_mode: off          # off / abstract / full
  preserve_terms: true
  chunk_size: 3000
```

> **Never put API keys in config.yaml** — they may be synced to Git. Use environment variables.

### Supported Providers

| Provider | Env Var | Base URL Env | Example Model |
|----------|---------|--------------|---------------|
| Mimo | `MIMO_API_KEY` | `MIMO_BASE_URL` | `mimo-v2.5-pro` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | `deepseek-v4-pro` |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `gpt-4o` |
| Moonshot | `MOONSHOT_API_KEY` | `MOONSHOT_BASE_URL` | `moonshot-v1-128k` |
| Zhipu | `ZHIPU_API_KEY` | `ZHIPU_BASE_URL` | `glm-4` |
| Qwen | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL` | `qwen-plus` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` | `qwen2.5:14b` |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_BASE_URL` | `anthropic/claude-sonnet-4` |

Any provider with an OpenAI-compatible `/v1/chat/completions` endpoint works.

## Output Structure

```
<vault>/
├── paperforge/
│   ├── config.yaml
│   └── paperforge.db
└── papers/
    ├── index.md                  # Master paper index
    └── 2024/
        └── paper-slug/
            ├── index.md          # Metadata + citation links
            ├── paper.md          # Parsed content
            ├── summary.md        # AI summary
            ├── qa.md             # AI Q&A
            ├── glossary.md       # AI glossary
            ├── paper.zh.md       # Translation (if enabled)
            └── figures/          # Extracted images
```

## Obsidian Integration

PaperForge generates Obsidian-compatible Markdown:

- **YAML frontmatter** — title, authors, year, venue, DOI, language, tags
- **Wikilinks** — `[[slug]]` links between papers in the citation graph
- **Graph View** — citation relationships appear in Obsidian's graph
- **Backlinks** — "Cited By / Cites" sections for each paper
- **Searchable** — all content indexed by Obsidian's search

Recommended plugins: **Dataview** (query by metadata), **Graph Analysis** (citation networks).

## Obsidian Plugin

An optional Obsidian plugin is included in `obsidian-plugin/`. It adds a PaperForge panel inside Obsidian for ingesting PDFs directly from the vault.

```bash
cd obsidian-plugin
npm install
npm run build
```

Copy `main.js` and `manifest.json` to your vault's `.obsidian/plugins/paperforge/`.

## Project Structure

```
PaperForge/
├── src/paperforge/
│   ├── cli.py              # 14 CLI commands (click)
│   ├── config.py           # YAML config loading
│   ├── pipeline.py         # 11-step ingestion pipeline
│   ├── models/
│   │   └── paper.py        # Paper dataclass
│   ├── parse/
│   │   ├── docling_parser.py   # Primary PDF parser
│   │   ├── fallback_parser.py  # PyMuPDF + pdfplumber
│   │   └── metadata.py         # Title/author/DOI extraction
│   ├── generate/
│   │   ├── summarizer.py   # Summary generation
│   │   ├── qa_generator.py # Q&A generation
│   │   ├── glossary.py     # Glossary generation
│   │   └── translator.py   # Translation (abstract/full)
│   ├── link/
│   │   ├── references.py   # Reference extraction from text
│   │   ├── matcher.py      # DOI / title matching
│   │   ├── linker.py       # Citation graph builder
│   │   ├── crossref.py     # CrossRef API
│   │   └── semantic_scholar.py  # Semantic Scholar API
│   ├── llm/
│   │   ├── client.py       # OpenAI-compatible API client
│   │   ├── prompts.py      # Prompt templates
│   │   └── schemas.py      # Pydantic response models
│   ├── store/
│   │   ├── db.py           # SQLite CRUD (papers, citations, tasks)
│   │   └── writer.py       # Markdown file writer + Jinja2 templates
│   └── templates/          # Jinja2 templates for output
├── tests/                  # 165 tests
├── obsidian-plugin/        # Obsidian plugin (TypeScript)
└── pyproject.toml
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -q

# Run with coverage
python -m pytest tests/ --cov=paperforge --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_link.py -v
```

## License

MIT
