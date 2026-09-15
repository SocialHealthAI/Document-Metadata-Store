from __future__ import annotations

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Encode `contextual_text` strings with the baked MiniLM model."""
    model = _load_model()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False,
    )
    return [row.tolist() for row in vectors]


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model
