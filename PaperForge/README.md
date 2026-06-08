# PaperForge

English | [中文](README.zh.md)

PaperForge is a CLI tool that converts academic PDF papers into structured knowledge bases for Obsidian. It parses PDFs, extracts metadata, generates AI-powered summaries, Q&A, glossaries, and builds citation graphs between papers.

## Features

- **PDF Parsing**: Primary parser (Docling) with fallback to PyMuPDF + pdfplumber
- **Metadata Extraction**: Title, authors, DOI, language detection
- **AI Generation**: Structured summaries, Q&A pairs, glossaries, translations (via DeepSeek LLM)
- **Citation Graph**: Automatic reference extraction, DOI/title matching, bidirectional citation links
- **Obsidian Integration**: Generates Obsidian-compatible Markdown with wikilinks, YAML frontmatter
- **CLI Interface**: Full command-line tool for ingestion, management, and export

## Installation

```bash
# Clone the repository
git clone https://github.com/corrie2/Tools.git
cd Tools/PaperForge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e .
# or with uv:
uv pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

## Quick Start

```bash
# Check your environment
paperforge doctor --vault ~/my-vault

# Ingest a PDF
paperforge ingest paper.pdf --vault ~/my-vault

# Ingest without LLM (faster)
paperforge ingest paper.pdf --vault ~/my-vault --no-llm

# List all papers
paperforge list --vault ~/my-vault

# View paper details
paperforge info paper-slug --vault ~/my-vault
```

## Configuration

PaperForge looks for a config file at `<vault>/paperforge/config.yaml`. If not found, defaults are used.

### LLM Configuration

PaperForge uses the **OpenAI-compatible API format**, which means it works with any provider that supports this standard. You just need to set the right environment variables and update `config.yaml`.

#### Step 1: Set Environment Variables

Set your API key as an environment variable. **Never put API keys in config.yaml** — it may be synced to Git.

```bash
# Linux / macOS
export YOUR_PROVIDER_API_KEY="sk-xxxxxxxx"

# Windows (PowerShell)
$env:YOUR_PROVIDER_API_KEY = "sk-xxxxxxxx"

# Windows (CMD)
set YOUR_PROVIDER_API_KEY=sk-xxxxxxxx
```

If your provider uses a custom base URL (not the default), also set:

```bash
export YOUR_PROVIDER_BASE_URL="https://your-provider.com/v1"
```

#### Step 2: Update config.yaml

Edit `<vault>/paperforge/config.yaml` and set the `llm` section:

```yaml
llm:
  provider: your-provider       # Provider name (for display)
  model: model-name             # Model to use
  api_key_env: YOUR_PROVIDER_API_KEY      # Env var name for API key
  base_url_env: YOUR_PROVIDER_BASE_URL    # Env var name for base URL (optional)
  timeout_seconds: 120
  max_retries: 3
```

#### Provider Examples

**DeepSeek**

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
```

```yaml
llm:
  provider: deepseek
  model: deepseek-v3
  api_key_env: DEEPSEEK_API_KEY
  base_url_env: DEEPSEEK_BASE_URL
```

**OpenAI**

```bash
export OPENAI_API_KEY="sk-xxxxxxxx"
```

```yaml
llm:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
  base_url_env: OPENAI_BASE_URL
```

**Moonshot (月之暗面)**

```bash
export MOONSHOT_API_KEY="sk-xxxxxxxx"
```

```yaml
llm:
  provider: moonshot
  model: moonshot-v1-128k
  api_key_env: MOONSHOT_API_KEY
  base_url_env: MOONSHOT_BASE_URL  # https://api.moonshot.cn/v1
```

**Zhipu (智谱)**

```bash
export ZHIPU_API_KEY="xxxxxxxx"
```

```yaml
llm:
  provider: zhipu
  model: glm-4
  api_key_env: ZHIPU_API_KEY
  base_url_env: ZHIPU_BASE_URL  # https://open.bigmodel.cn/api/paas/v4
```

**Qwen (通义千问)**

```bash
export DASHSCOPE_API_KEY="sk-xxxxxxxx"
```

```yaml
llm:
  provider: qwen
  model: qwen-plus
  api_key_env: DASHSCOPE_API_KEY
  base_url_env: DASHSCOPE_BASE_URL  # https://dashscope.aliyuncs.com/compatible-mode/v1
```

**Ollama (Local)**

No API key needed. Just set the base URL:

```bash
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```

```yaml
llm:
  provider: ollama
  model: qwen2.5:14b
  api_key_env: OLLAMA_API_KEY  # Not needed, but field is required
  base_url_env: OLLAMA_BASE_URL
```

Set a dummy key if required: `export OLLAMA_API_KEY="ollama"`

**OpenRouter**

```bash
export OPENROUTER_API_KEY="sk-xxxxxxxx"
```

```yaml
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4
  api_key_env: OPENROUTER_API_KEY
  base_url_env: OPENROUTER_BASE_URL  # https://openrouter.ai/api/v1
```

#### Full config.yaml Reference

```yaml
vault:
  papers_dir: papers        # Where paper files are stored
  data_dir: paperforge      # Where db and config live

llm:
  provider: deepseek        # Provider name
  model: deepseek-v3        # Model name
  api_key_env: DEEPSEEK_API_KEY    # Env var name for API key
  base_url_env: DEEPSEEK_BASE_URL  # Env var name for base URL (optional)
  timeout_seconds: 120      # Request timeout
  max_retries: 3            # Retry count on failure

parser:
  primary: docling          # Primary PDF parser
  fallback: pymupdf_pdfplumber  # Fallback parser
  save_figures: true
  save_tables: true

citation_matching:
  auto_confirm_doi: true
  auto_confirm_title_threshold: 95.0
  pending_title_threshold: 85.0
  require_year_match_for_title: true

translation:
  default_mode: off         # off / abstract / full
  preserve_terms: true
  chunk_size: 3000
```

#### Verify Configuration

Run `doctor` to check if everything is set up correctly:

```bash
paperforge doctor --vault ~/MyVault
```

This will check: config file, API key, model availability, and dependencies.

## CLI Commands

### Core Commands

| Command | Description |
|---------|-------------|
| `paperforge ingest <pdf> --vault <path>` | Ingest a PDF into the knowledge base |
| `paperforge list --vault <path>` | List all ingested papers |
| `paperforge info <slug> --vault <path>` | Show detailed information for a paper |
| `paperforge status <slug> --vault <path>` | Show task statuses for a paper |
| `paperforge doctor --vault <path>` | Check environment and dependencies |

### Management Commands

| Command | Description |
|---------|-------------|
| `paperforge remove <slug> --vault <path>` | Remove a paper and all its data |
| `paperforge rebuild-index --vault <path>` | Regenerate all index.md files |
| `paperforge open <slug> --vault <path>` | Open paper index.md in default app |
| `paperforge export --vault <path>` | Export knowledge base as zip |

### LLM Commands

| Command | Description |
|---------|-------------|
| `paperforge regenerate <slug> --vault <path> --type <type>` | Regenerate a specific LLM output |
| `paperforge retry <slug> --vault <path>` | Retry all failed LLM tasks |

### Citation Commands

| Command | Description |
|---------|-------------|
| `paperforge relink --vault <path>` | Re-scan all references and re-match |
| `paperforge confirm-ref <src> <tgt> --vault <path>` | Confirm a pending citation |
| `paperforge reject-ref <src> <tgt> --vault <path>` | Reject a pending citation |

### Options

- `--vault <path>`: Required for all commands. Path to Obsidian vault.
- `--no-llm`: Skip LLM generation (ingest only).
- `--translate <mode>`: Translation mode (`off`, `abstract`, `full`).
- `--year <year>`: Filter by year (list command).
- `--status <status>`: Filter by status (list command).
- `--yes` / `-y`: Skip confirmation prompts (remove command).

## Output Structure

```
<vault>/
├── paperforge/
│   ├── config.yaml          # Configuration
│   └── paperforge.db        # SQLite database
└── papers/
    ├── index.md             # Master paper index
    ├── 2024/
    │   └── paper-slug/
    │       ├── index.md     # Paper metadata + citation links
    │       ├── paper.md     # Parsed paper content
    │       ├── summary.md   # AI-generated summary
    │       ├── qa.md        # AI-generated Q&A
    │       ├── glossary.md  # AI-generated glossary
    │       ├── translated.md # Translated content (if enabled)
    │       └── figures/     # Extracted figures
    └── 2023/
        └── another-paper/
            └── ...
```

## Obsidian Integration

PaperForge generates Obsidian-compatible Markdown:

- **YAML Frontmatter**: Title, authors, year, venue, DOI, language, tags
- **Wikilinks**: `[[slug]]` links between papers in the citation graph
- **Graph View**: Citation relationships appear in Obsidian's graph view
- **Backlinks**: "Cited By" sections show which papers reference the current one
- **Search**: All content is searchable within Obsidian

### Recommended Obsidian Plugins

- **Dataview**: Query papers by year, venue, tags
- **Graph Analysis**: Explore citation networks
- **Tag Wrangler**: Manage paper tags

## Development

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -q

# Run with coverage
python -m pytest tests/ --cov=paperforge --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_parse.py -q
```

### Project Structure

```
PaperForge/
├── src/
│   └── paperforge/
│       ├── cli.py           # CLI commands
│       ├── config.py        # Configuration
│       ├── pipeline.py      # Ingestion pipeline
│       ├── models/
│       │   └── paper.py     # Paper data model
│       ├── parse/
│       │   ├── docling_parser.py  # Primary parser
│       │   ├── fallback_parser.py # Fallback parser
│       │   └── metadata.py        # Metadata extraction
│       ├── generate/
│       │   ├── summarizer.py   # Summary generation
│       │   ├── qa_generator.py # Q&A generation
│       │   ├── glossary.py     # Glossary generation
│       │   └── translator.py   # Translation
│       ├── link/
│       │   ├── references.py  # Reference extraction
│       │   ├── matcher.py     # DOI/title matching
│       │   ├── linker.py      # Citation graph building
│       │   └── semantic_scholar.py # S2 API integration
│       ├── llm/
│       │   ├── client.py      # LLM API client
│       │   ├── prompts.py     # Prompt templates
│       │   └── schemas.py     # Pydantic response models
│       ├── store/
│       │   ├── db.py          # SQLite CRUD
│       │   └── writer.py      # File writer + templates
│       └── templates/         # Jinja2 templates
├── tests/
│   ├── test_parse.py          # Parser + model tests
│   ├── test_generate.py       # LLM schema + prompt tests
│   ├── test_link.py           # Citation matching tests
│   ├── test_store.py          # Database + writer tests
│   └── test_pipeline.py       # Pipeline + CLI tests
└── pyproject.toml
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Run the test suite
5. Submit a pull request

## License

MIT License
