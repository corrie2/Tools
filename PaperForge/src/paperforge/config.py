"""Configuration management for PaperForge."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


# Known provider patterns: (provider_name, api_key_env, base_url_env, default_model, default_base_url)
KNOWN_PROVIDERS = [
    ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "deepseek-v3", "https://api.deepseek.com/v1"),
    ("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL", "gpt-4o", "https://api.openai.com/v1"),
    ("moonshot", "MOONSHOT_API_KEY", "MOONSHOT_BASE_URL", "moonshot-v1-128k", "https://api.moonshot.cn/v1"),
    ("zhipu", "ZHIPU_API_KEY", "ZHIPU_BASE_URL", "glm-4", "https://open.bigmodel.cn/api/paas/v4"),
    ("qwen", "DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("mimo", "MIMO_API_KEY", "MIMO_BASE_URL", "mimo-v2.5-pro", "https://token-plan-cn.xiaomimimo.com/v1"),
    ("ollama", "OLLAMA_API_KEY", "OLLAMA_BASE_URL", "qwen2.5:14b", "http://localhost:11434/v1"),
    ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "anthropic/claude-sonnet-4", "https://openrouter.ai/api/v1"),
    ("siliconflow", "SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL", "Qwen/Qwen2.5-72B-Instruct", "https://api.siliconflow.cn/v1"),
    ("together", "TOGETHER_API_KEY", "TOGETHER_BASE_URL", "meta-llama/Llama-3-70b-chat-hf", "https://api.together.xyz/v1"),
]


def detect_providers() -> List[Tuple[str, str, str, str, str]]:
    """Scan environment variables and return available providers.

    Returns list of (provider, api_key_env, base_url_env, default_model, default_base_url)
    for providers whose API key is set in environment.
    """
    found = []
    for entry in KNOWN_PROVIDERS:
        provider, key_env, url_env, model, base_url = entry
        key = os.environ.get(key_env)
        if key and key.strip():
            # Skip dummy/placeholder keys (like "ollama")
            if provider == "ollama" or len(key) > 5:
                found.append(entry)
    return found


def get_provider_config(provider_name: str) -> Optional[Tuple[str, str, str, str]]:
    """Get config values for a known provider by name.

    Returns (api_key_env, base_url_env, default_model, default_base_url) or None.
    """
    for entry in KNOWN_PROVIDERS:
        if entry[0] == provider_name:
            return (entry[1], entry[2], entry[3], entry[4])
    return None


def fetch_models(api_key: str, base_url: str, timeout: int = 15) -> List[dict]:
    """Fetch available models from an OpenAI-compatible API.

    Returns list of dicts with 'id' key, or empty list on failure.
    """
    import urllib.request
    import urllib.error

    url = f"{base_url.rstrip('/')}/models"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            # Sort by id
            models.sort(key=lambda m: m.get("id", ""))
            return models
    except Exception as e:
        logger.debug("Failed to fetch models from %s: %s", url, e)
        return []


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url_env: str = "DEEPSEEK_BASE_URL"
    timeout_seconds: int = 120
    max_retries: int = 3

    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    @property
    def base_url(self) -> Optional[str]:
        return os.environ.get(self.base_url_env)


@dataclass
class ParserConfig:
    primary: str = "docling"
    fallback: str = "pymupdf_pdfplumber"
    save_figures: bool = True
    save_tables: bool = True


@dataclass
class CitationConfig:
    auto_confirm_doi: bool = True
    auto_confirm_title_threshold: float = 95.0
    pending_title_threshold: float = 85.0
    require_year_match_for_title: bool = True


@dataclass
class TranslationConfig:
    default_mode: str = "off"  # off / abstract / full
    preserve_terms: bool = True
    chunk_size: int = 3000


@dataclass
class Config:
    vault: Path = field(default_factory=lambda: Path.home())
    papers_dir: str = "papers"
    data_dir: str = "paperforge"
    llm: LLMConfig = field(default_factory=LLMConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    citation: CitationConfig = field(default_factory=CitationConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)

    @property
    def db_path(self) -> Path:
        return self.vault / self.data_dir / "paperforge.db"

    @property
    def config_path(self) -> Path:
        return self.vault / self.data_dir / "config.yaml"

    @property
    def papers_path(self) -> Path:
        return self.vault / self.papers_dir

    @property
    def data_path(self) -> Path:
        return self.vault / self.data_dir


def load_config(vault: Path) -> Config:
    """Load config from vault/paperforge/config.yaml, falling back to defaults.

    Auto-creates vault/paperforge/ directory if it doesn't exist.
    """
    config = Config(vault=vault)
    config_dir = vault / "paperforge"
    config_path = config_dir / "config.yaml"

    # Auto-create paperforge directory if missing
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        with open(config_path, encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        vault_cfg = data.get("vault", {})
        config.papers_dir = vault_cfg.get("papers_dir", "papers")
        config.data_dir = vault_cfg.get("data_dir", "paperforge")

        llm_cfg = data.get("llm", {})
        provider_name = llm_cfg.get("provider", "deepseek")
        # Resolve provider-aware defaults for api_key_env and base_url_env
        pcfg = get_provider_config(provider_name)
        default_key_env = pcfg[0] if pcfg else "DEEPSEEK_API_KEY"
        default_url_env = pcfg[1] if pcfg else "DEEPSEEK_BASE_URL"
        config.llm = LLMConfig(
            provider=provider_name,
            model=llm_cfg.get("model", "deepseek-v4-pro"),
            api_key_env=llm_cfg.get("api_key_env", default_key_env),
            base_url_env=llm_cfg.get("base_url_env", default_url_env),
            timeout_seconds=llm_cfg.get("timeout_seconds", 120),
            max_retries=llm_cfg.get("max_retries", 3),
        )

        parser_cfg = data.get("parser", {})
        config.parser = ParserConfig(
            primary=parser_cfg.get("primary", "docling"),
            fallback=parser_cfg.get("fallback", "pymupdf_pdfplumber"),
            save_figures=parser_cfg.get("save_figures", True),
            save_tables=parser_cfg.get("save_tables", True),
        )

        citation_cfg = data.get("citation_matching", {})
        config.citation = CitationConfig(
            auto_confirm_doi=citation_cfg.get("auto_confirm_doi", True),
            auto_confirm_title_threshold=citation_cfg.get("auto_confirm_title_threshold", 95.0),
            pending_title_threshold=citation_cfg.get("pending_title_threshold", 85.0),
            require_year_match_for_title=citation_cfg.get("require_year_match_for_title", True),
        )

        trans_cfg = data.get("translation", {})
        config.translation = TranslationConfig(
            default_mode=trans_cfg.get("default_mode", "off"),
            preserve_terms=trans_cfg.get("preserve_terms", True),
            chunk_size=trans_cfg.get("chunk_size", 3000),
        )

    return config


DEFAULT_CONFIG_YAML = """\
# PaperForge configuration
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
"""


def create_default_config(vault: Path) -> Path:
    """Create a default config.yaml in the vault's paperforge directory.

    Returns path to the created config file.
    """
    config_dir = vault / "paperforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    return config_path
