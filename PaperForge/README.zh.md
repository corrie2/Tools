# PaperForge

[English](README.md) | 中文

将学术 PDF 论文转换为 Obsidian 结构化知识库。解析 PDF、提取元数据、生成 AI 摘要/问答/术语表，并构建论文间的引用图谱。

## 功能特性

- **PDF 解析** — Docling（主解析器）+ PyMuPDF + pdfplumber（备用）
- **元数据提取** — 标题、作者、DOI、单位、语言检测
- **AI 生成** — 摘要、问答、术语表、翻译（支持任意 OpenAI 兼容 LLM）
- **引用图谱** — 参考文献提取、DOI/标题匹配（CrossRef + Semantic Scholar）、双向引用链接
- **Obsidian 输出** — YAML frontmatter、`[[wikilinks]]`、图谱视图兼容
- **CLI** — 14 个命令，覆盖导入、管理、引用校正、导出

## 安装

```bash
git clone https://github.com/corrie2/Tools.git
cd Tools/PaperForge
```

**Linux / macOS：**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Windows (PowerShell)：**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

**Windows (CMD)：**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
```

> 需要 Python 3.10+。如果有 [uv](https://github.com/astral-sh/uv)，可用 `uv pip install -e .`。

## 快速开始

### 1. 设置 API Key

PaperForge 支持所有 OpenAI 兼容的 LLM。设置环境变量：

```bash
# Mimo（国内推荐）
export MIMO_API_KEY="your-key"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"

# DeepSeek
export DEEPSEEK_API_KEY="your-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"

# OpenAI
export OPENAI_API_KEY="your-key"

# Ollama（本地，不需要 key）
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

### 2. 配置

```bash
paperforge config --vault /path/to/obsidian-vault
```

自动检测环境中的 API key，列出可用 provider，选择模型，保存到 `config.yaml`。

### 3. 导入论文

```bash
paperforge ingest paper.pdf --vault /path/to/obsidian-vault
```

流水线执行 11 步：PDF 解析 → 元数据 → 图片 → AI 摘要/问答/术语表 → 翻译 → 参考文献提取 → 引用匹配 → 索引生成。

跳过 AI 生成（仅解析，更快）：

```bash
paperforge ingest paper.pdf --vault /path/to/obsidian-vault --no-llm
```

### 4. 浏览

```bash
# 列出所有论文
paperforge list --vault /path/to/obsidian-vault

# 查看论文详情
paperforge info paper-slug --vault /path/to/obsidian-vault

# 在 Obsidian 中打开 — 论文存储在 papers/<year>/<slug>/
```

## CLI 命令

### 核心命令

| 命令 | 说明 |
|------|------|
| `paperforge ingest <pdf>` | 导入 PDF 到知识库 |
| `paperforge config` | 自动检测 API key 并配置 LLM |
| `paperforge list` | 列出所有已导入论文 |
| `paperforge info <slug>` | 查看论文详情 |
| `paperforge status <slug>` | 查看流水线任务状态 |
| `paperforge doctor` | 检查环境和依赖 |

### 管理命令

| 命令 | 说明 |
|------|------|
| `paperforge remove <slug>` | 删除论文及其所有数据 |
| `paperforge rebuild-index` | 重新生成所有 index.md |
| `paperforge open <slug>` | 用默认应用打开论文 index.md |
| `paperforge export` | 导出知识库为 zip |

### LLM 命令

| 命令 | 说明 |
|------|------|
| `paperforge regenerate <slug> --type <type>` | 重新生成 summary / qa / glossary / translation |
| `paperforge retry <slug>` | 重试所有失败的 LLM 任务 |

### 引用命令

| 命令 | 说明 |
|------|------|
| `paperforge relink` | 重新扫描所有参考文献并匹配 |
| `paperforge confirm-ref <src> <tgt>` | 确认待定引用 |
| `paperforge reject-ref <src> <tgt>` | 拒绝待定引用 |

### 通用选项

- `--vault <path>` — Obsidian vault 路径（所有命令必需）
- `--no-llm` — 跳过 AI 生成（仅导入）
- `--translate <mode>` — 翻译模式：`off` / `abstract` / `full`
- `--year <year>` — 按年份筛选（list）
- `--status <status>` — 按状态筛选（list）
- `--yes` / `-y` — 跳过确认（remove）

## 配置

配置文件：`<vault>/paperforge/config.yaml`

```yaml
vault:
  papers_dir: papers        # vault 下的论文存储目录
  data_dir: paperforge      # 数据库和配置位置

llm:
  provider: deepseek
  model: deepseek-v4-pro
  api_key_env: DEEPSEEK_API_KEY       # 环境变量名（不是 key 本身）
  base_url_env: DEEPSEEK_BASE_URL     # 可选
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

> **不要在 config.yaml 中放 API key** — 可能会被同步到 Git。使用环境变量。

### 支持的 LLM Provider

| Provider | 环境变量 | Base URL 环境变量 | 示例模型 |
|----------|----------|-------------------|----------|
| Mimo | `MIMO_API_KEY` | `MIMO_BASE_URL` | `mimo-v2.5-pro` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | `deepseek-v4-pro` |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `gpt-4o` |
| Moonshot | `MOONSHOT_API_KEY` | `MOONSHOT_BASE_URL` | `moonshot-v1-128k` |
| Zhipu（智谱） | `ZHIPU_API_KEY` | `ZHIPU_BASE_URL` | `glm-4` |
| Qwen（通义千问） | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL` | `qwen-plus` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` | `qwen2.5:14b` |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_BASE_URL` | `anthropic/claude-sonnet-4` |

任何支持 OpenAI 兼容 `/v1/chat/completions` 接口的 provider 都可以使用。

### Semantic Scholar API Key（可选）

PaperForge 使用 Semantic Scholar 丰富引用元数据。默认使用公共 API（每次请求间隔 3 秒）。如需更快的引用匹配，可设置 API key：

```bash
export S2_API_KEY="your-key"
```

申请地址：https://www.semanticscholar.org/product/api#api-key

有 key：1 请求/秒；无 key：3 秒/请求。

## 输出结构

```
<vault>/
├── paperforge/
│   ├── config.yaml
│   └── paperforge.db
└── papers/
    ├── index.md                  # 论文总索引
    └── 2024/
        └── paper-slug/
            ├── index.md          # 元数据 + 引用链接
            ├── paper.md          # 解析内容
            ├── summary.md        # AI 摘要
            ├── qa.md             # AI 问答
            ├── glossary.md       # AI 术语表
            ├── paper.zh.md       # 中文翻译（如启用）
            └── figures/          # 提取的图片
```

## Obsidian 集成

PaperForge 生成 Obsidian 兼容的 Markdown：

- **YAML frontmatter** — 标题、作者、年份、会议/期刊、DOI、语言、标签
- **Wikilinks** — 论文间 `[[slug]]` 互链
- **图谱视图** — 引用关系在 Obsidian 图谱中可视化
- **反向链接** — 每篇论文显示"被引 / 引用"
- **全文搜索** — 所有内容可被 Obsidian 搜索

推荐插件：**Dataview**（按元数据查询）、**Graph Analysis**（引用网络分析）。

## Obsidian 插件

`obsidian-plugin/` 目录包含可选的 Obsidian 插件，在 Obsidian 内添加 PaperForge 面板，支持直接从 vault 导入 PDF。

```bash
cd obsidian-plugin
npm install
npm run build
```

将 `main.js` 和 `manifest.json` 复制到 vault 的 `.obsidian/plugins/paperforge/` 目录。

## 项目结构

```
PaperForge/
├── src/paperforge/
│   ├── cli.py              # 14 个 CLI 命令（click）
│   ├── config.py           # YAML 配置加载
│   ├── pipeline.py         # 11 步导入流水线
│   ├── models/
│   │   └── paper.py        # Paper 数据类
│   ├── parse/
│   │   ├── docling_parser.py   # 主 PDF 解析器
│   │   ├── fallback_parser.py  # PyMuPDF + pdfplumber
│   │   └── metadata.py         # 标题/作者/DOI 提取
│   ├── generate/
│   │   ├── summarizer.py   # 摘要生成
│   │   ├── qa_generator.py # 问答生成
│   │   ├── glossary.py     # 术语表生成
│   │   └── translator.py   # 翻译（摘要/全文）
│   ├── link/
│   │   ├── references.py   # 参考文献提取
│   │   ├── matcher.py      # DOI / 标题匹配
│   │   ├── linker.py       # 引用图谱构建
│   │   ├── crossref.py     # CrossRef API
│   │   └── semantic_scholar.py  # Semantic Scholar API
│   ├── llm/
│   │   ├── client.py       # OpenAI 兼容 API 客户端
│   │   ├── prompts.py      # Prompt 模板
│   │   └── schemas.py      # Pydantic 响应模型
│   ├── store/
│   │   ├── db.py           # SQLite CRUD
│   │   └── writer.py       # Markdown 文件写入 + Jinja2 模板
│   └── templates/          # Jinja2 输出模板
├── tests/                  # 165 个测试
├── obsidian-plugin/        # Obsidian 插件（TypeScript）
└── pyproject.toml
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行所有测试
python -m pytest tests/ -q

# 带覆盖率
python -m pytest tests/ --cov=paperforge --cov-report=term-missing

# 运行指定测试文件
python -m pytest tests/test_link.py -v
```

## 许可证

MIT
