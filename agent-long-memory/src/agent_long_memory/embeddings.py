from __future__ import annotations

import os
import json
import subprocess
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import lru_cache
from typing import Iterator


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    _disable_embedding_progress()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install an embedding extra before using local embeddings."
        ) from exc
    with _quiet_embedding_io():
        return SentenceTransformer(model_name)


def embed_texts(texts: list[str], *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    if not texts:
        return []
    if os.environ.get("AGENT_LONG_MEMORY_EMBEDDING_SUBPROCESS") == "1":
        return _embed_texts_subprocess(texts, model_name=model_name)
    return _embed_texts_in_process(texts, model_name=model_name)


def _embed_texts_in_process(texts: list[str], *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    _disable_embedding_progress()
    model = load_embedding_model(model_name)
    with _quiet_embedding_io():
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [[float(value) for value in vector] for vector in vectors]


def embed_text(text: str, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    return embed_texts([text], model_name=model_name)[0]


def _disable_embedding_progress() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _embed_texts_subprocess(texts: list[str], *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    timeout = int(os.environ.get("AGENT_LONG_MEMORY_EMBEDDING_TIMEOUT", "180"))
    payload = json.dumps({"model_name": model_name, "texts": texts}, ensure_ascii=False)
    env = os.environ.copy()
    env["AGENT_LONG_MEMORY_EMBEDDING_SUBPROCESS"] = "0"
    env.setdefault("AGENT_LONG_MEMORY_EMBEDDING_QUIET", "1")
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    completed = subprocess.run(
        [sys.executable, "-m", "agent_long_memory.embedding_worker"],
        input=payload,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"embedding worker failed with code {completed.returncode}: {detail}")
    return json.loads(completed.stdout)


@contextmanager
def _quiet_embedding_io() -> Iterator[None]:
    if os.environ.get("AGENT_LONG_MEMORY_EMBEDDING_QUIET", "1") == "0":
        yield
        return
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with redirect_stdout(devnull), redirect_stderr(devnull):
            yield
