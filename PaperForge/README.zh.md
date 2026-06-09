# PaperForge

[English](README.md) | 中文

PaperForge 是一个 CLI 工具，用于将学术论文 PDF 转换为 Obsidian 结构化知识库。它能解析 PDF、提取元数据、生成 AI 摘要、问答、术语表，并构建论文间的引用图谱。

## 功能特性

- **PDF 解析**：主解析器（Docling）+ 备用解析器（PyMuPDF + pdfplumber）
- **元数据提取**：标题、作者、DOI、语言检测，支持 Semantic Scholar + Crossref API 补全
- **AI 生成**：结构化摘要、问答对、术语表、翻译（兼容所有 OpenAI 格式 API）
- **引用图谱**：自动提取参考文献、DOI/标题匹配、双向引用链接
- **Obsidian 集成**：生成 Obsidian 兼容的 Markdown，支持 wikilink、YAML frontmatter
- **CLI 工具**：完整的命令行接口，支持导入、管理、导出

## 安装

### Linux / macOS

```bash
# 克隆仓库
git clone https://github.com/corrie2/Tools.git
cd Tools/PaperForge

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"
```

### Windows (PowerShell)

```powershell
# 克隆仓库
git clone https://github.com/corrie2/Tools.git
cd Tools\PaperForge

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 安装
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"
```

### Windows (CMD)

```cmd
:: 克隆仓库
git clone https://github.com/corrie2/Tools.git
cd Tools\PaperForge

:: 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate.bat

:: 安装
pip install -e .

:: 安装开发依赖
pip install -e ".[dev]"
```

## 快速开始

### 完整流程（以 Mimo 为例）

**第一步：设置环境变量**

```powershell
# Windows PowerShell
$env:MIMO_API_KEY = "你的API Key"
$env:MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
```

```bash
# Linux / macOS
export MIMO_API_KEY="你的API Key"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
```

**第二步：配置 provider（交互式）**

```bash
paperforge config --vault D:\data\notespace
```

会自动检测到 Mimo，让你选模型，然后问你是否设为默认。

**第三步：导入论文**

```bash
paperforge ingest paper.pdf --vault D:\data\notespace
```

**第四步：查看结果**

```bash
# 列出所有论文
paperforge list --vault D:\data\notespace

# 查看论文详情
paperforge info paper-slug --vault D:\data\notespace

# 用 Obsidian 打开 vault 目录，papers/ 下就是生成的文件
```

### 其他常用命令

```bash
# 检查环境是否配置正确
paperforge doctor --vault D:\data\notespace

# 跳过 LLM，只做 PDF 解析（更快）
paperforge ingest paper.pdf --vault D:\data\notespace --no-llm

# 重新生成摘要
paperforge regenerate paper-slug --vault D:\data\notespace --type summary

# 重新匹配引用关系
paperforge relink --vault D:\data\notespace

# 删除论文
paperforge remove paper-slug --vault D:\data\notespace

# 导出为 zip
paperforge export --vault D:\data\notespace
```

### 使用其他 provider

只需更换环境变量和 config 中的 provider 名称：

```powershell
# DeepSeek
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxx"
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# OpenAI
$env:OPENAI_API_KEY = "sk-xxxxxxxx"

# 智谱
$env:ZHIPU_API_KEY = "xxxxxxxx"
$env:ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 通义千问
$env:DASHSCOPE_API_KEY = "sk-xxxxxxxx"
$env:DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Ollama（本地）
$env:OLLAMA_BASE_URL = "http://localhost:11434/v1"
$env:OLLAMA_API_KEY = "ollama"
```

然后运行 `paperforge config --vault <vault路径>` 选择即可。

## 配置

PaperForge 会在 `<vault>/paperforge/config.yaml` 查找配置文件。如果不存在，使用默认配置。

### LLM 配置（完整流程）

PaperForge 使用 **OpenAI 兼容的 API 格式**，支持所有兼容此标准的模型服务商。

下面以 **Mimo（小米）** 为例，展示完整配置流程。其他服务商只需更换环境变量名和 URL。

#### 第一步：设置环境变量

将 API Key 设置为环境变量。**不要将 API Key 写入 config.yaml**，该文件可能会被 Git 同步。

**Linux / macOS：**

```bash
export MIMO_API_KEY="你的API Key"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
```

**Windows (PowerShell)：**

```powershell
$env:MIMO_API_KEY = "你的API Key"
$env:MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
```

**Windows (CMD)：**

```cmd
set MIMO_API_KEY=你的API Key
set MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
```

> 注意：环境变量只在当前终端会话有效。如需永久生效，请将其添加到 shell 配置文件（如 `~/.bashrc`）或系统环境变量。

#### 第二步：运行 paperforge config（推荐）

`paperforge config` 会自动检测环境变量中的 API Key，拉取模型列表，引导你完成配置：

```bash
paperforge config --vault D:\data\notespace
```

运行过程：

```
Scanning environment for API keys...

  Detected providers:
    [1] mimo            model=mimo-v2.5-pro                   key=tp-cfq9q...h3u5

  Select provider number: 1

  Selected: mimo
  Fetching models from https://token-plan-cn.xiaomimimo.com/v1...
  Found 3 models:

    [1] mimo-v2-pro
    [2] mimo-v2.5-pro
    [3] mimo-v2-flash

  Default (from config): mimo-v2.5-pro
  Press Enter to use default, or enter model number

  Model selection:          ← 直接回车用默认，或输入编号选择

  Model: mimo-v2.5-pro

  [1] Only use this time (don't save)
  [2] Set as default (save to config.yaml)

  Your choice: 2            ← 输入 2 设为默认

  Saved to D:\data\notespace\paperforge\config.yaml
  Provider: mimo
  Model:    mimo-v2.5-pro
  Key env:  MIMO_API_KEY
  URL env:  MIMO_BASE_URL
```

完成后，config.yaml 会自动写入：

```yaml
llm:
  provider: mimo
  model: mimo-v2.5-pro
  api_key_env: MIMO_API_KEY
  base_url_env: MIMO_BASE_URL
  timeout_seconds: 120
  max_retries: 3
```

#### 第三步：验证配置

```bash
paperforge doctor --vault D:\data\notespace
```

输出中应该看到：

```
  [OK] ENV MIMO_API_KEY            (mimo) mimo-v2.5-pro
  [OK] Config LLM provider         mimo / mimo-v2.5-pro
```

#### 第四步：开始使用

```bash
paperforge ingest paper.pdf --vault D:\data\notespace
```

#### 手动配置（不用 paperforge config）

如果不想用交互式配置，也可以直接编辑 config.yaml：

```yaml
# D:\data\notespace\paperforge\config.yaml
vault:
  papers_dir: papers
  data_dir: paperforge

llm:
  provider: mimo
  model: mimo-v2.5-pro
  api_key_env: MIMO_API_KEY
  base_url_env: MIMO_BASE_URL
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
  default_mode: off
  preserve_terms: true
  chunk_size: 3000
```

#### 其他服务商环境变量参考

| 服务商 | API Key 环境变量 | Base URL 环境变量 | Base URL 值 |
|--------|-----------------|-------------------|-------------|
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| Moonshot | `MOONSHOT_API_KEY` | `MOONSHOT_BASE_URL` | `https://api.moonshot.cn/v1` |
| 智谱 | `ZHIPU_API_KEY` | `ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` |
| 通义千问 | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Mimo | `MIMO_API_KEY` | `MIMO_BASE_URL` | `https://token-plan-cn.xiaomimimo.com/v1` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` | `http://localhost:11434/v1` |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` |
| SiliconFlow | `SILICONFLOW_API_KEY` | `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` |

设置好环境变量后，运行 `paperforge config --vault <vault路径>` 选择即可。

## CLI 命令

### 核心命令

| 命令 | 说明 |
|------|------|
| `paperforge ingest <pdf> --vault <path>` | 导入论文 |
| `paperforge config --vault <path>` | 自动检测 API Key 并配置 LLM |
| `paperforge list --vault <path>` | 列出所有论文 |
| `paperforge info <slug> --vault <path>` | 查看论文详情 |
| `paperforge status <slug> --vault <path>` | 查看任务状态 |
| `paperforge doctor --vault <path>` | 检查环境和依赖 |

### 管理命令

| 命令 | 说明 |
|------|------|
| `paperforge remove <slug> --vault <path>` | 删除论文及其所有数据 |
| `paperforge rebuild-index --vault <path>` | 重建所有 index.md |
| `paperforge open <slug> --vault <path>` | 用默认应用打开论文 |
| `paperforge export --vault <path>` | 导出知识库为 zip |

### LLM 命令

| 命令 | 说明 |
|------|------|
| `paperforge regenerate <slug> --vault <path> --type <type>` | 重新生成指定 LLM 输出 |
| `paperforge retry <slug> --vault <path>` | 重试所有失败的 LLM 任务 |

### 引用命令

| 命令 | 说明 |
|------|------|
| `paperforge relink --vault <path>` | 重新扫描参考文献并匹配 |
| `paperforge confirm-ref <src> <tgt> --vault <path>` | 确认待审引用 |
| `paperforge reject-ref <src> <tgt> --vault <path>` | 拒绝待审引用 |

### 通用选项

- `--vault <path>`：所有命令必需，指向 Obsidian vault 路径
- `--no-llm`：跳过 LLM 生成（仅解析）
- `--translate <mode>`：翻译模式（`off` / `abstract` / `full`）
- `--year <year>`：按年份过滤（list 命令）
- `--status <status>`：按状态过滤（list 命令）
- `--yes` / `-y`：跳过确认提示（remove 命令）

## 输出结构

```
<vault>/
├── paperforge/
│   ├── config.yaml          # 配置文件
│   └── paperforge.db        # SQLite 数据库
└── papers/
    ├── index.md             # 总论文索引
    ├── pending_review.md    # 待确认引用
    ├── 2024/
    │   └── paper-slug/
    │       ├── index.md     # 论文元数据 + 引用链接
    │       ├── paper.md     # 解析后的论文内容
    │       ├── summary.md   # AI 生成的摘要
    │       ├── qa.md        # AI 生成的问答
    │       ├── glossary.md  # AI 生成的术语表
    │       ├── paper.zh.md   # 中文翻译（如启用）
    │       └── figures/     # 提取的图片
    └── 2023/
        └── another-paper/
            └── ...
```

## Obsidian 集成

PaperForge 生成 Obsidian 兼容的 Markdown：

- **YAML Frontmatter**：标题、作者、年份、会议/期刊、DOI、语言、标签
- **Wikilink**：`[[slug]]` 格式的论文间引用链接
- **图谱视图**：引用关系在 Obsidian 图谱中可视化
- **反向链接**："被以下论文引用" 展示谁引用了当前论文
- **搜索**：所有内容可在 Obsidian 中搜索

### 推荐 Obsidian 插件

- **Dataview**：按年份、会议、标签查询论文
- **Graph Analysis**：探索引用网络
- **Tag Wrangler**：管理论文标签

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -q

# 运行并生成覆盖率报告
python -m pytest tests/ --cov=paperforge --cov-report=term-missing

# 运行指定测试文件
python -m pytest tests/test_parse.py -q
```

### 项目结构

```
PaperForge/
├── src/
│   └── paperforge/
│       ├── cli.py           # CLI 命令
│       ├── config.py        # 配置管理
│       ├── pipeline.py      # 导入流水线
│       ├── models/
│       │   └── paper.py     # 论文数据模型
│       ├── parse/
│       │   ├── docling_parser.py  # 主解析器
│       │   ├── fallback_parser.py # 备用解析器
│       │   └── metadata.py        # 元数据提取
│       ├── generate/
│       │   ├── summarizer.py   # 摘要生成
│       │   ├── qa_generator.py # 问答生成
│       │   ├── glossary.py     # 术语表生成
│       │   └── translator.py   # 翻译
│       ├── link/
│       │   ├── references.py  # 参考文献提取
│       │   ├── matcher.py     # DOI/标题匹配
│       │   ├── linker.py      # 引用图谱构建
│       │   ├── semantic_scholar.py # S2 API
│       │   └── crossref.py    # Crossref API
│       ├── llm/
│       │   ├── client.py      # LLM API 客户端
│       │   ├── prompts.py     # Prompt 模板
│       │   └── schemas.py     # Pydantic 响应模型
│       ├── store/
│       │   ├── db.py          # SQLite CRUD
│       │   └── writer.py      # 文件写入 + 模板
│       └── templates/         # Jinja2 模板
├── tests/                     # 测试文件
├── obsidian-plugin/           # Obsidian 插件（TypeScript）
└── pyproject.toml
```

### 贡献

1. Fork 仓库
2. 创建功能分支
3. 为新功能添加测试
4. 运行测试套件
5. 提交 Pull Request

## 许可证

MIT License
