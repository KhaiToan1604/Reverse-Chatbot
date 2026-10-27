from dataclasses import dataclass

from app.config import Settings
from app.modules.adaptive.selector import QuestionSelector
from app.modules.embedding.base import Embedder
from app.modules.embedding.factory import build_embedder
from app.modules.generation.service import GenerationService
from app.modules.grading.service import GradingService
from app.modules.ingestion.service import IngestionService
from app.modules.llm.base import LLMProvider
from app.modules.llm.factory import build_llm
from app.modules.quiz.service import QuizService
from app.modules.vectorstore.numpy_store import NumpyVectorStore


@dataclass
class Container:
    """Nơi lắp ráp các module (dependency injection thủ công, dễ thay thế khi test)."""

    settings: Settings
    llm: LLMProvider
    embedder: Embedder
    store: NumpyVectorStore
    ingestion: IngestionService
    generation: GenerationService
    grader: GradingService
    selector: QuestionSelector
    quiz: QuizService


def build_container(s: Settings, llm: LLMProvider | None = None, embedder: Embedder | None = None) -> Container:
    llm = llm or build_llm(s)
    embedder = embedder or build_embedder(s)
    store = NumpyVectorStore(None if s.vector_store_path == ":memory:" else s.vector_store_path)
    ingestion = IngestionService(s, embedder, store)
    generation = GenerationService(s, llm, embedder, store)
    grader = GradingService(s, llm)
    selector = QuestionSelector(s, generation)
    quiz = QuizService(s, selector, grader)
    return Container(s, llm, embedder, store, ingestion, generation, grader, selector, quiz)
