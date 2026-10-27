from app.config import Settings
from app.modules.embedding.base import Embedder


def build_embedder(s: Settings) -> Embedder:
    if s.embedding_provider == "hashing":
        from app.modules.embedding.hashing import HashingEmbedder

        return HashingEmbedder()
    from app.modules.embedding.sentence_transformer import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(s.embedding_model)
