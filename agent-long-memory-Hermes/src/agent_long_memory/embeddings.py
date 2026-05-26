from __future__ import annotations

from functools import lru_cache


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install an embedding extra before using local embeddings."
        ) from exc
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    model = load_embedding_model(model_name)
    vectors = model.encode(texts, normalize_embeddings=True)
    return [[float(value) for value in vector] for vector in vectors]


def embed_text(text: str, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    return embed_texts([text], model_name=model_name)[0]
