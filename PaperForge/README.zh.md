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

```bash
# 克隆仓库
git clone https://github.com/corrie2/Tools.git
cd Tools/PaperForge

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装（开发模式）
pip install -e .
# 或使用 uv：
uv pip install -e .

# 安装开发依赖
pip install -e ".[dev]"
```

## 快速开始

```bash
# 检查环境
paperforge doctor --vault ~/my-vault

# 导入论文
paperforge ingest paper.pdf --vault ~/my-vault

# 跳过 LLM，只做解析（更快）
paperforge ingest paper.pdf --vault ~/my-vault --no-llm

# 列出所有论文
paperforge list --vault ~/my-vault

# 查看论文详情
paperforge info paper-slug --vault ~/my-vault
```

## 配置

PaperForge 会在 `<vault>/paperforge/config.yaml` 查找配置文件。如果不存在，使用默认配置。

### LLM 配置

PaperForge 使用 **OpenAI 兼容的 API 格式**，支持所有兼容此标准的模型服务商。只需设置环境变量并更新 `config.yaml` 即可。

#### 第一步：设置环境变量

将 API Key 设置为环境变量。**不要将 API Key 写入 config.yaml**，该文件可能会被 Git 同步。

```bash
# Linux / macOS
export YOUR_PROVIDER_API_KEY="sk-xxxxxxxx"

# Windows (PowerShell)
$env:YOUR_PROVIDER_API_KEY = "sk-xxxxxxxx"

# Windows (CMD)
set YOUR_PROVIDER_API_KEY=sk-xxxxxxxx
```

如果你的服务商使用自定义 base URL，还需要设置：

```bash
export YOUR_PROVIDER_BASE_URL="https://your-provider.com/v1"
```

#### 第二步：更新 config.yaml

编辑 `<vault>/paperforge/config.yaml`，设置 `llm` 部分：

```yaml
llm:
  provider: your-provider       # 服务商名称
  model: model-name             # 模型名称
  api_key_env: YOUR_PROVIDER_API_KEY      # API Key 环境变量名
  base_url_env: YOUR_PROVIDER_BASE_URL    # Base URL 环境变量名（可选）
  timeout_seconds: 120
  max_retries: 3
```

#### 各服务商配置示例

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

**Moonshot（月之暗面）**

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

**智谱（Zhipu）**

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

**通义千问（Qwen）**

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

**Ollama（本地部署）**

不需要 API Key，只需设置 base URL：

```bash
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```

```yaml
llm:
  provider: ollama
  model: qwen2.5:14b
  api_key_env: OLLAMA_API_KEY  # 不需要，但字段必填
  base_url_env: OLLAMA_BASE_URL
```

如果需要填 API Key，设置一个占位值：`export OLLAMA_API_KEY="ollama"`

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

#### 完整 config.yaml 参考

```yaml
vault:
  papers_dir: papers        # 论文文件存储目录
  data_dir: paperforge      # 数据库和配置存储目录

llm:
  provider: deepseek        # 服务商名称
  model: deepseek-v3        # 模型名称
  api_key_env: DEEPSEEK_API_KEY    # API Key 环境变量名
  base_url_env: DEEPSEEK_BASE_URL  # Base URL 环境变量名（可选）
  timeout_seconds: 120      # 请求超时时间
  max_retries: 3            # 失败重试次数

parser:
  primary: docling          # 主解析器
  fallback: pymupdf_pdfplumber  # 备用解析器
  save_figures: true        # 保存图片
  save_tables: true         # 保存表格

citation_matching:
  auto_confirm_doi: true    # DOI 精确匹配自动确认
  auto_confirm_title_threshold: 95.0  # 标题匹配自动确认阈值
  pending_title_threshold: 85.0       # 待确认阈值
  require_year_match_for_title: true  # 标题匹配要求年份一致

translation:
  default_mode: off         # off / abstract / full
  preserve_terms: true      # 保留英文术语
  chunk_size: 3000          # 翻译分块大小
```

#### 验证配置

运行 `doctor` 检查配置是否正确：

```bash
paperforge doctor --vault ~/MyVault
```

会检查：配置文件、API Key、模型可用性、依赖项。

## CLI 命令

### 核心命令

| 命令 | 说明 |
|------|------|
| `paperforge ingest <pdf> --vault <path>` | 导入论文 |
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
    │       ├── translated.md # 翻译内容（如启用）
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
