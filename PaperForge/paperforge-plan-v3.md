# PaperForge — 详细执行方案 v3

## 1. 项目定位

PaperForge = **独立文献档案生成器 CLI + Obsidian 集成插件**。

核心处理逻辑全部放在 Python CLI 中完成，Obsidian 插件只负责调用 CLI、配置、展示处理进度和打开生成结果。这样可以避免把 PDF 解析、LLM 调用、SQLite、引用匹配等重型逻辑塞进 Obsidian 插件，同时保留后续扩展到 VS Code、Logseq、Zotero、Web UI、GitHub Actions 的可能性。

### 核心流程

```text
用户输入一篇 PDF
  ↓
PaperForge 解析 PDF、提取图片/表格/正文/元数据
  ↓
生成结构化 Markdown 文献档案
  ↓
LLM 生成摘要、问答、术语表，可选全文翻译
  ↓
提取参考文献并与已有文献库匹配
  ↓
生成 Obsidian 双链和总索引
```

### 单篇论文输出

```text
papers/{year}/{paper-slug}/
├── index.md            # 论文索引页，含 YAML frontmatter、元数据、双向引用
├── paper.md            # 论文全文 Markdown，保留章节结构、图片、表格
├── paper.zh.md         # 中文翻译，可选，仅英文论文生成
├── summary.md          # 结构化摘要
├── qa.md               # 5-8 个常见问题
├── glossary.md         # 专业术语表
└── figures/            # 提取的图片
    ├── fig_001.png
    └── fig_002.png
```

## 2. 设计原则

1. **CLI 优先，插件后置**  
   Phase 1-6 只做 CLI，确保核心 pipeline 稳定；Obsidian 插件作为 Phase 7 集成层。

2. **稳定 ID 与可变 slug 分离**  
   数据库主键不使用 slug。slug 可以随着标题、年份、目录策略变化，paper id 必须稳定。

3. **多阶段任务可追踪**  
   parse、metadata、summary、qa、glossary、translate、references、link、index 每一步都记录状态，便于 retry、regenerate、status。

4. **引用匹配保守自动化**  
   DOI 精确匹配可以自动确认；标题模糊匹配必须结合年份、作者和置信度；低置信度进入 pending_review.md，不自动建链。

5. **全文翻译默认关闭或降级**  
   全文翻译成本高、耗时长、易失败。默认生成 summary / qa / glossary，全文翻译通过参数显式开启。

6. **API Key 不写入 Vault**  
   Vault 可能被 Git 同步。config.yaml 只保存 env var 名称，真正的 key 放环境变量。

7. **失败可恢复**  
   任意阶段失败不应破坏已有产物。支持 retry、regenerate、doctor。

## 3. 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| PDF 解析 | Docling | 主解析器，适合输出 Markdown、图片、表格、标题结构 |
| PDF fallback | PyMuPDF + pdfplumber | 纯 CPU，作为 Docling 失败时的保底方案 |
| LLM | DeepSeek-v4-pro | 默认模型，中文能力较好，适合摘要、问答、术语、翻译 |
| 元数据 API | Semantic Scholar + Crossref | 用于 DOI、标题、年份、作者、venue、引用信息补全 |
| 语言检测 | langdetect | 判断是否需要翻译 |
| 模糊匹配 | rapidfuzz | 标题相似度匹配，速度快 |
| 存储 | SQLite + 文件系统 | 无服务依赖，适合本地文献库和 Git 同步 |
| CLI | click | 简洁，和已有 Python CLI 项目风格一致 |
| 模板 | Jinja2 | 生成 index.md、summary.md、qa.md、glossary.md、总索引 |
| 包管理 | uv + pyproject.toml | 现代 Python 打包方式 |
| Obsidian 集成 | TypeScript 插件 | 只做入口、设置、进度、打开结果 |

## 4. 项目仓库结构

```text
~/paperforge/
├── pyproject.toml
├── README.md
├── src/
│   └── paperforge/
│       ├── __init__.py
│       ├── cli.py                  # CLI 入口
│       ├── config.py               # 配置读取与校验
│       ├── pipeline.py             # 主流程编排
│       ├── parse/
│       │   ├── __init__.py
│       │   ├── docling_parser.py   # Docling 解析器
│       │   ├── fallback_parser.py  # PyMuPDF + pdfplumber 备用解析器
│       │   └── metadata.py         # 本地元数据提取
│       ├── generate/
│       │   ├── __init__.py
│       │   ├── translator.py       # 英文论文中文翻译
│       │   ├── summarizer.py       # 结构化摘要
│       │   ├── qa_generator.py     # 问答生成
│       │   └── glossary.py         # 术语表生成
│       ├── link/
│       │   ├── __init__.py
│       │   ├── references.py       # 参考文献结构化提取
│       │   ├── matcher.py          # DOI/标题/API 三层匹配
│       │   └── linker.py           # 双向链接生成与 index.md 更新
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py           # LLM API 客户端
│       │   ├── prompts.py          # Prompt 模板
│       │   └── schemas.py          # JSON 输出 schema 校验
│       ├── models/
│       │   ├── __init__.py
│       │   ├── paper.py            # Paper 数据模型
│       │   ├── reference.py        # Reference 数据模型
│       │   └── artifact.py         # 输出文件模型
│       ├── store/
│       │   ├── __init__.py
│       │   ├── db.py               # SQLite CRUD
│       │   └── writer.py           # 文件写入 + YAML frontmatter
│       ├── tasks/
│       │   ├── __init__.py
│       │   ├── runner.py           # 任务执行器
│       │   └── status.py           # 状态记录、retry、resume
│       └── templates/
│           ├── index.md.j2
│           ├── summary.md.j2
│           ├── qa.md.j2
│           ├── glossary.md.j2
│           ├── papers_index.md.j2
│           └── pending_review.md.j2
├── tests/
│   ├── test_parse.py
│   ├── test_generate.py
│   ├── test_link.py
│   ├── test_store.py
│   └── test_pipeline.py
└── obsidian-plugin/                # Phase 7 再做
    ├── manifest.json
    ├── main.ts
    └── styles.css
```

## 5. Obsidian Vault 产出结构

```text
用户的 Obsidian Vault/
├── papers/
│   ├── index.md                    # 总索引，按年份分组
│   ├── pending_review.md           # 待确认低置信度引用
│   ├── 2024/
│   │   ├── retrieval-augmented-generation/
│   │   │   ├── index.md
│   │   │   ├── paper.md
│   │   │   ├── paper.zh.md
│   │   │   ├── summary.md
│   │   │   ├── qa.md
│   │   │   ├── glossary.md
│   │   │   └── figures/
│   │   │       ├── fig_001.png
│   │   │       └── fig_002.png
│   │   └── another-paper/
│   │       └── ...
│   └── 2023/
│       └── ...
├── paperforge/
│   ├── paperforge.db               # SQLite 数据库
│   └── config.yaml                 # 配置，不直接保存 API key
└── .obsidian/
    └── plugins/
        └── paperforge/
            ├── manifest.json
            ├── main.js
            └── styles.css
```

## 6. 配置文件设计

`paperforge/config.yaml` 只保存普通配置和环境变量名称，不保存真实密钥。

```yaml
vault:
  papers_dir: papers
  data_dir: paperforge

llm:
  provider: deepseek
  model: deepseek-v4-pro
  api_key_env: DEEPSEEK_API_KEY
  base_url_env: DEEPSEEK_BASE_URL
  timeout_seconds: 120
  max_retries: 3

metadata:
  semantic_scholar_enabled: true
  crossref_enabled: true
  user_agent: "PaperForge/0.1"

translation:
  default_mode: off        # off / abstract / full
  preserve_terms: true
  chunk_size: 3000

citation_matching:
  auto_confirm_doi: true
  auto_confirm_title_threshold: 95
  pending_title_threshold: 85
  require_year_match_for_title: true

parser:
  primary: docling
  fallback: pymupdf_pdfplumber
  save_figures: true
  save_tables: true
```

环境变量示例：

```bash
export DEEPSEEK_API_KEY="你的 key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

## 7. SQLite Schema v3

### 7.1 论文主表

```sql
CREATE TABLE papers (
    id TEXT PRIMARY KEY,                 -- 稳定 ID，建议 uuid 或 pdf sha256
    slug TEXT NOT NULL,                  -- 可读目录名，可变化
    title TEXT NOT NULL,
    normalized_title TEXT,
    authors TEXT,                        -- JSON array
    year INTEGER,
    venue TEXT,
    doi TEXT UNIQUE,
    language TEXT,                       -- en / zh / unknown
    pdf_path TEXT,                       -- 原始 PDF 路径
    pdf_sha256 TEXT,                     -- 用于去重
    vault_path TEXT,                     -- papers/{year}/{slug}/index.md
    paper_dir TEXT,                      -- papers/{year}/{slug}/
    parser TEXT,                         -- docling / fallback
    parse_quality TEXT,                  -- high / medium / low
    fallback_used INTEGER DEFAULT 0,
    processed_at TEXT,
    updated_at TEXT,
    status TEXT DEFAULT 'completed'      -- pending / running / completed / failed / partial
);

CREATE INDEX idx_papers_slug ON papers(slug);
CREATE INDEX idx_papers_doi ON papers(doi);
CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_pdf_sha256 ON papers(pdf_sha256);
CREATE INDEX idx_papers_normalized_title ON papers(normalized_title);
```

### 7.2 阶段任务状态表

用于支持 `status`、`retry`、`regenerate`、断点恢复。

```sql
CREATE TABLE paper_tasks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    task_type TEXT NOT NULL,             -- parse / metadata / write / translate / summary / qa / glossary / references / link / index
    status TEXT NOT NULL,                -- pending / running / completed / failed / skipped
    input_hash TEXT,
    output_path TEXT,
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT
);

CREATE INDEX idx_tasks_paper ON paper_tasks(paper_id);
CREATE INDEX idx_tasks_status ON paper_tasks(status);
CREATE INDEX idx_tasks_type ON paper_tasks(task_type);
```

### 7.3 原始参考文献表

```sql
CREATE TABLE references_raw (
    id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_text TEXT NOT NULL,
    parsed_authors TEXT,                 -- JSON array
    parsed_title TEXT,
    normalized_title TEXT,
    parsed_year INTEGER,
    parsed_venue TEXT,
    parsed_doi TEXT,
    sequence_num INTEGER,
    extraction_method TEXT,              -- llm / regex / api
    created_at TEXT
);

CREATE INDEX idx_refs_source ON references_raw(source_paper_id);
CREATE INDEX idx_refs_doi ON references_raw(parsed_doi);
CREATE INDEX idx_refs_normalized_title ON references_raw(normalized_title);
```

### 7.4 外部参考文献候选表

用于表达“当前论文引用了库外论文，但库里还没有导入”。这是后续做文献图谱和推荐导入的重要基础。

```sql
CREATE TABLE reference_candidates (
    id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_reference_id TEXT NOT NULL REFERENCES references_raw(id),
    title TEXT,
    normalized_title TEXT,
    authors TEXT,                        -- JSON array
    year INTEGER,
    venue TEXT,
    doi TEXT,
    external_id TEXT,                    -- Semantic Scholar paperId / Crossref DOI
    matched_paper_id TEXT REFERENCES papers(id),
    match_method TEXT,                   -- doi_exact / title_fuzzy / api / manual / none
    confidence REAL,
    status TEXT DEFAULT 'unmatched',     -- unmatched / pending / matched / rejected
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX idx_candidates_source ON reference_candidates(source_paper_id);
CREATE INDEX idx_candidates_doi ON reference_candidates(doi);
CREATE INDEX idx_candidates_matched ON reference_candidates(matched_paper_id);
CREATE INDEX idx_candidates_status ON reference_candidates(status);
```

### 7.5 引用关系边表

只保存本地文献库内已经匹配到的引用边。

```sql
CREATE TABLE citation_edges (
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    target_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_reference_id TEXT REFERENCES references_raw(id),
    match_method TEXT,                   -- doi_exact / title_fuzzy / api / manual
    confidence REAL,                     -- 0.0 - 1.0
    confirmed INTEGER DEFAULT 0,         -- 0=pending, 1=confirmed
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (source_paper_id, target_paper_id)
);

CREATE INDEX idx_edges_source ON citation_edges(source_paper_id);
CREATE INDEX idx_edges_target ON citation_edges(target_paper_id);
CREATE INDEX idx_edges_confirmed ON citation_edges(confirmed);
```

## 8. index.md 模板

```yaml
---
title: "{{ title }}"
authors:
{% for author in authors %}
  - "{{ author }}"
{% endfor %}
year: {{ year }}
venue: "{{ venue }}"
doi: "{{ doi }}"
language: "{{ language }}"
slug: "{{ slug }}"
paper_id: "{{ paper_id }}"
parser: "{{ parser }}"
parse_quality: "{{ parse_quality }}"
fallback_used: {{ fallback_used }}
tags:
  - paper
{% for tag in tags %}
  - {{ tag }}
{% endfor %}
---

# {{ title }}

## 基本信息

- 年份：{{ year }}
- 会议/期刊：{{ venue }}
- DOI：{{ doi }}
- 作者：{{ authors | join(', ') }}
- 语言：{{ language }}
- 关键词：{{ keywords | join(', ') }}

## 本文档

- [[paper]]
{% if has_translation %}- [[paper.zh]]{% endif %}
- [[summary]]
- [[qa]]
- [[glossary]]

## 结构化摘要

> 可从 summary.md 中同步一句话总结。

{{ one_sentence_summary }}

## 引用了已有论文

{% for ref in citing_papers %}
- [[{{ ref.slug }}]]{% if ref.method == 'title_fuzzy' %}（相似度：{{ ref.confidence }}）{% endif %}
{% endfor %}
{% if not citing_papers %}
（无已知本地引用）
{% endif %}

## 被以下论文引用

{% for cited_by in cited_by_papers %}
- [[{{ cited_by.slug }}]]
{% endfor %}
{% if not cited_by_papers %}
（暂无）
{% endif %}

## 待确认引用

{% for item in pending_refs %}
- {{ item.title }}{% if item.year %}（{{ item.year }}）{% endif %} — 置信度：{{ item.confidence }}
{% endfor %}
{% if not pending_refs %}
（无）
{% endif %}
```

## 9. summary.md 模板

```md
# Summary — {{ title }}

## 一句话总结

{{ one_sentence_summary }}

## 研究问题

{{ research_question }}

## 核心方法

{{ method }}

## 核心结论

{{ conclusions }}

## 适用场景

{{ use_cases }}

## 局限性

{{ limitations }}

## 与已有工作的关系

{{ relation_to_prior_work }}
```

## 10. CLI 命令设计

### 10.1 导入论文

```bash
# 默认流程：解析 PDF → 生成 paper.md、summary.md、qa.md、glossary.md、index.md → 更新总索引
paperforge ingest paper.pdf --vault ~/MyVault --out papers

# 指定 LLM 模型
paperforge ingest paper.pdf --vault ~/MyVault --llm deepseek-v4-pro

# 跳过 LLM，只做 PDF 解析和元数据
paperforge ingest paper.pdf --vault ~/MyVault --no-llm

# 翻译策略：默认 off，可显式开启
paperforge ingest paper.pdf --vault ~/MyVault --translate off
paperforge ingest paper.pdf --vault ~/MyVault --translate abstract
paperforge ingest paper.pdf --vault ~/MyVault --translate full

# 批量导入
paperforge ingest ./pdfs/*.pdf --vault ~/MyVault
```

### 10.2 重新生成

```bash
paperforge regenerate <slug> --type summary --vault ~/MyVault
paperforge regenerate <slug> --type qa --vault ~/MyVault
paperforge regenerate <slug> --type glossary --vault ~/MyVault
paperforge regenerate <slug> --type translate --vault ~/MyVault
```

### 10.3 引用关系

```bash
# 重新匹配所有引用关系
paperforge relink --vault ~/MyVault

# 确认或拒绝待审引用
paperforge confirm-ref <source> <target> --vault ~/MyVault
paperforge reject-ref <source> <target> --vault ~/MyVault
```

### 10.4 管理命令

```bash
# 列出所有论文
paperforge list --vault ~/MyVault

# 查看论文详情
paperforge info <slug> --vault ~/MyVault

# 查看处理状态
paperforge status <slug> --vault ~/MyVault

# 重试失败任务
paperforge retry <slug> --vault ~/MyVault

# 删除论文及引用边
paperforge remove <slug> --vault ~/MyVault

# 重建总索引
paperforge rebuild-index --vault ~/MyVault

# 打开论文 index.md
paperforge open <slug> --vault ~/MyVault

# 检查环境、配置、依赖、API、数据库
paperforge doctor --vault ~/MyVault

# 导出文献库
paperforge export --vault ~/MyVault --format zip
```

## 11. Pipeline 处理流程

```text
paperforge ingest paper.pdf --vault ~/MyVault
  │
  ├─ 0. 初始化与检查
  │     ├─ 读取 config.yaml
  │     ├─ 检查 SQLite 是否存在，不存在则建表
  │     ├─ 计算 PDF sha256，判断是否重复导入
  │     └─ 创建 paper_id 与 task 记录
  │
  ├─ 1. 解析 PDF
  │     ├─ Docling → Markdown + 图片 + 表格
  │     ├─ 记录 parser、parse_quality、fallback_used
  │     └─ Fallback: PyMuPDF + pdfplumber
  │
  ├─ 2. 提取与补全元数据
  │     ├─ 从首页/正文提取标题、作者、摘要、DOI
  │     ├─ Semantic Scholar DOI 查询或标题搜索
  │     ├─ Crossref fallback
  │     └─ 生成稳定 paper_id、slug、paper_dir
  │
  ├─ 3. 写入基础文件
  │     ├─ papers/{year}/{slug}/paper.md
  │     ├─ papers/{year}/{slug}/figures/
  │     └─ SQLite: papers
  │
  ├─ 4. 语言检测与翻译
  │     ├─ langdetect 判断 en / zh / unknown
  │     ├─ 默认不全文翻译
  │     ├─ --translate abstract 只翻译摘要和结论
  │     └─ --translate full 分块生成 paper.zh.md
  │
  ├─ 5. LLM 生成
  │     ├─ summary.md
  │     ├─ qa.md
  │     ├─ glossary.md
  │     └─ 所有 LLM 输出都做 JSON schema 校验和重试
  │
  ├─ 6. 参考文献结构化提取
  │     ├─ 从 paper.md 末尾定位 References / Bibliography
  │     ├─ LLM 或规则抽取 raw references
  │     ├─ 结构化标题、作者、年份、venue、DOI
  │     └─ 写入 references_raw 与 reference_candidates
  │
  ├─ 7. 引用匹配
  │     ├─ DOI 精确匹配：自动确认
  │     ├─ 标题 fuzzy + 年份匹配：高置信自动确认
  │     ├─ Semantic Scholar / Crossref API 辅助匹配
  │     ├─ 低置信度：写入 pending_review.md
  │     └─ 匹配成功：写入 citation_edges
  │
  ├─ 8. 生成论文 index.md
  │     ├─ YAML frontmatter
  │     ├─ 本文档链接
  │     ├─ 引用了已有论文
  │     ├─ 被哪些已有论文引用
  │     └─ 待确认引用
  │
  └─ 9. 更新总索引
        ├─ papers/index.md 按年份分组
        ├─ 更新被引用论文的 index.md
        └─ 写入所有任务状态
```

## 12. 引用匹配策略

### 12.1 匹配优先级

```text
1. DOI 精确匹配
2. 标题规范化 + rapidfuzz 相似度匹配
3. 标题 + 年份 + 作者联合匹配
4. Semantic Scholar API 辅助确认
5. Crossref API fallback
6. 人工确认 / 拒绝
```

### 12.2 置信度规则

```text
DOI exact:
  confidence = 1.0
  confirmed = 1

标题相似度 >= 95 且年份一致:
  confidence = 0.95 - 0.99
  confirmed = 1

标题相似度 85 - 95:
  status = pending
  写入 pending_review.md

标题相似度 < 85:
  status = unmatched
  不建立 citation_edges
```

### 12.3 标题规范化

```text
- 全部转小写
- 去除标点符号
- 去除多余空格
- 去除常见副标题分隔符后的噪声，保留完整标题原文
- Unicode normalize
```

## 13. pending_review.md 设计

```md
# PaperForge Pending Citation Review

以下引用匹配置信度不足，需要人工确认。

## {{ source_title }}

### Candidate 1

- 原始引用：{{ raw_text }}
- 解析标题：{{ parsed_title }}
- 候选本地论文：[[{{ candidate_slug }}]]
- 相似度：{{ confidence }}
- 匹配方式：{{ match_method }}

确认：

```bash
paperforge confirm-ref {{ source_slug }} {{ candidate_slug }} --vault ~/MyVault
```

拒绝：

```bash
paperforge reject-ref {{ source_slug }} {{ candidate_slug }} --vault ~/MyVault
```
```

## 14. 总索引 papers/index.md

```md
# Papers Index

## 2024

| 论文 | 作者 | Venue | DOI | 标签 |
|------|------|-------|-----|------|
| [[2024/retrieval-augmented-generation/index|Retrieval-Augmented Generation]] | Author A, Author B | NeurIPS | 10.xxxx | rag, llm |

## 2023

...
```

后续可扩展为 Dataview 查询版本：

```dataview
TABLE year, venue, doi, tags
FROM "papers"
WHERE contains(tags, "paper")
SORT year DESC
```

## 15. Obsidian 插件设计

### 15.1 插件职责

Obsidian 插件只做轻量集成，不承担核心处理逻辑。

```text
Obsidian 插件负责：
- 选择 PDF
- 调用 paperforge CLI
- 显示 CLI 日志和处理进度
- 打开生成的 index.md
- 提供设置页
- 提供重建索引、刷新引用按钮

Obsidian 插件不负责：
- 直接解析 PDF
- 直接调用 Docling
- 直接执行 LLM 生成
- 直接维护复杂引用匹配逻辑
```

### 15.2 插件命令

```text
PaperForge: Import PDF
  选择 PDF → 调用 paperforge ingest → 自动打开 index.md

PaperForge: Rebuild Library Index
  调用 paperforge rebuild-index

PaperForge: Refresh Citation Links
  调用 paperforge relink

PaperForge: Open Paper Dashboard
  打开侧边栏，显示论文列表、年份、处理状态

PaperForge: Doctor
  调用 paperforge doctor 并显示检查结果
```

### 15.3 插件设置页

```text
- PaperForge CLI 路径
- Vault 路径
- papers 输出目录
- 默认 LLM provider
- 默认翻译策略：off / abstract / full
- 是否导入后自动打开 index.md
```

## 16. MVP 分阶段计划

### MVP 1：稳定导入引擎

目标：`paperforge ingest paper.pdf` 能稳定生成基础文献档案。

输出：

```text
index.md
paper.md
summary.md
figures/
papers/index.md
```

任务：

- [ ] uv init + pyproject.toml
- [ ] click CLI 基础框架
- [ ] Docling parser
- [ ] PyMuPDF + pdfplumber fallback
- [ ] PDF sha256 去重
- [ ] 基础元数据提取：标题、作者、年份、DOI
- [ ] slug 生成策略
- [ ] SQLite 初始化：papers、paper_tasks
- [ ] writer 生成 paper.md、index.md、papers/index.md
- [ ] summary.md 生成
- [ ] `paperforge doctor`
- [ ] 2-3 篇真实论文测试

### MVP 2：LLM 文献理解产物

目标：完善 summary / qa / glossary / 可选翻译。

输出：

```text
summary.md
qa.md
glossary.md
paper.zh.md，可选
```

任务：

- [ ] DeepSeek API client
- [ ] JSON schema 输出校验
- [ ] LLM 重试与错误记录
- [ ] qa_generator
- [ ] glossary generator
- [ ] 翻译模式：off / abstract / full
- [ ] `paperforge regenerate`
- [ ] `paperforge status`
- [ ] `paperforge retry`

### MVP 3：引用图谱与双链

目标：自动提取参考文献，匹配已有文献库，生成双向链接。

任务：

- [ ] references_raw 表
- [ ] reference_candidates 表
- [ ] citation_edges 表
- [ ] 参考文献区域定位
- [ ] LLM 参考文献结构化提取
- [ ] DOI exact matching
- [ ] rapidfuzz title matching
- [ ] Semantic Scholar / Crossref API 辅助匹配
- [ ] pending_review.md
- [ ] `paperforge relink`
- [ ] `confirm-ref` / `reject-ref`
- [ ] 更新被引用论文 index.md

### MVP 4：CLI 完善与文档

目标：把 CLI 做成可长期使用的本地工具。

任务：

- [ ] `paperforge list`
- [ ] `paperforge info`
- [ ] `paperforge remove`
- [ ] `paperforge rebuild-index`
- [ ] `paperforge open`
- [ ] `paperforge export`
- [ ] 单元测试
- [ ] 集成测试
- [ ] README.md
- [ ] 示例 vault

### MVP 5：Obsidian 插件

目标：在 Obsidian 中一键导入 PDF。

任务：

- [ ] 插件脚手架
- [ ] 设置页
- [ ] Import PDF 命令
- [ ] 调用本地 CLI
- [ ] 进度与日志展示
- [ ] 处理完成后打开 index.md
- [ ] Rebuild Index 命令
- [ ] Refresh Citation Links 命令
- [ ] Doctor 命令
- [ ] 可选 Dashboard

## 17. 推荐开发顺序

不要一开始做完整功能，建议按下面顺序推进：

```text
1. paperforge doctor
2. paperforge ingest paper.pdf --no-llm
3. 生成 paper.md + figures/
4. 写入 SQLite papers 表
5. 生成 index.md + papers/index.md
6. 接入 summary.md
7. 接入 qa.md + glossary.md
8. 加入 regenerate / retry / status
9. 加入 references_raw
10. 加入 citation_edges 和 pending_review.md
11. 最后做 Obsidian 插件
```

## 18. 关键风险与处理策略

### 18.1 PDF 解析质量不稳定

风险：双栏论文、扫描版 PDF、公式密集论文、跨页表格、图片标题错位、参考文献换行都会影响输出质量。

处理策略：

```text
- 记录 parser、fallback_used、parse_quality
- Docling 失败时自动 fallback
- 不追求 paper.md 完美还原，优先保证可读、章节完整、图片可引用
- 解析失败不影响数据库状态，允许 retry
```

### 18.2 LLM 输出不稳定

风险：JSON 格式错误、遗漏字段、翻译超长、API 超时。

处理策略：

```text
- 所有 LLM 输出要求 JSON schema 校验
- 自动 retry
- 分块输入
- 失败任务写入 paper_tasks
- 用户可以 regenerate 单个文件
```

### 18.3 引用误匹配

风险：标题相似但不是同一篇论文，尤其是同领域相近标题。

处理策略：

```text
- DOI exact 才无条件自动确认
- 标题匹配必须结合年份
- 85-95 相似度进入 pending_review.md
- 所有人工确认写入 match_method = manual
```

### 18.4 API Key 泄露

风险：config.yaml 放在 vault 中，可能被 Git 同步。

处理策略：

```text
- config.yaml 只保存 api_key_env
- README 明确提醒不要提交 .env
- doctor 检查环境变量是否存在
```

### 18.5 Obsidian 插件跨平台问题

风险：Windows / macOS / Linux 调用本地 CLI 的路径、权限、shell 行为不同。

处理策略：

```text
- 插件允许用户手动配置 CLI 路径
- doctor 显示实际调用命令
- 第一版插件只支持桌面端
- 移动端不作为目标
```

## 19. 验收标准

### MVP 1 验收

- [ ] 对 3 篇真实英文论文运行 `paperforge ingest`
- [ ] 能生成 paper.md、summary.md、index.md、figures/
- [ ] papers/index.md 能按年份展示论文
- [ ] SQLite papers 表有记录
- [ ] `doctor` 能检查配置和依赖

### MVP 2 验收

- [ ] summary.md 包含研究问题、核心方法、核心结论、适用场景、一句话总结
- [ ] qa.md 生成 5-8 个问题
- [ ] glossary.md 包含英文术语、中文定义、首次出现位置
- [ ] `regenerate` 能单独重建 summary / qa / glossary
- [ ] LLM 失败能记录到 paper_tasks

### MVP 3 验收

- [ ] 能从论文中提取 references_raw
- [ ] DOI 精确匹配能自动建立 citation_edges
- [ ] 标题低置信度匹配进入 pending_review.md
- [ ] `confirm-ref` 后 index.md 出现双向链接
- [ ] 被引用论文 index.md 能更新“被以下论文引用”

### MVP 5 验收

- [ ] Obsidian 中可以通过命令选择 PDF
- [ ] 插件能调用 CLI
- [ ] 能显示处理日志
- [ ] 完成后自动打开生成的 index.md
- [ ] 插件设置页可以配置 CLI 路径和默认翻译策略

## 20. 当前最终判断

PaperForge 的最佳形态不是单纯的 Obsidian 插件，而是：

```text
独立 Python 文献处理引擎
  + 本地 SQLite 文献图谱
  + Markdown 文件系统输出
  + Obsidian 双链集成
```

优先做稳定的 `paperforge ingest`，再逐步增加 LLM 文献理解、引用图谱和 Obsidian 插件。这样可以先获得一个可用工具，再逐渐把它发展成面向科研工作流的文献知识库生成器。
