import logging
import os
from dataclasses import dataclass

import faiss
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from rich.logging import RichHandler
from sentence_transformers import SentenceTransformer

load_dotenv()


def setup_logger(name: str = __name__) -> logging.Logger:
    """统一设置日志"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                markup=True,
                rich_tracebacks=True,
            )
        ],
    )
    return logging.getLogger(name)


logger = setup_logger()
app = FastAPI(title="RAG with Text Example")


@dataclass
class Deps:
    embedding_model: SentenceTransformer
    dim: int | None = 384
    index: faiss.IndexFlatIP = faiss.IndexFlatIP(dim)


class QueryRequest(BaseModel):
    query: str = Field(default_factory=str, description="用户查询的问题")


class ModelResponse(BaseModel):
    answer: str = Field(default_factory=str, description="回答内容")
    sources: list[str] = Field(default_factory=list, description="参考来源")


model = OpenAIChatModel(
    os.getenv("MODEL", "deepseek/deepseek-chat-v3.1:free"),
    provider=LiteLLMProvider(
        api_base=os.getenv("API_BASE"), api_key=os.getenv("API_KEY")
    ),
)
embedding_model = SentenceTransformer("/data1/hf-models/all-MiniLM-L6-v2")
logger.info(f"Embedding model loaded: {embedding_model}")
agent = Agent(
    model=model,
    deps_type=Deps,
    output_type=ModelResponse,
)
logger.info(f"Agent loaded: {agent}")

deps: Deps = Deps(
    embedding_model=embedding_model,
    dim=embedding_model.get_sentence_embedding_dimension(),
    index=faiss.IndexFlatIP(embedding_model.get_sentence_embedding_dimension()),
)
# --------- 2. 示例数据 ----------
documents = [
    "FAISS is a library for efficient similarity search.",
    "Sentence Transformers can generate embeddings for sentences.",
    "Milvus and Weaviate are popular vector databases.",
    "LangChain and LlamaIndex help build RAG applications.",
]


def embedding_fn(texts: list[str], embedding_model) -> np.ndarray:
    return embedding_model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def add_embeddings(
    texts: list[str],
    index: faiss.IndexFlatIP,
    embedding_model: SentenceTransformer,
):
    vectors = embedding_fn(texts, embedding_model)
    index.add(vectors)  # type: ignore
    logger.info(f"Added {len(texts)} embeddings to the index.")


def search_embeddings(
    query: str,
    index: faiss.IndexFlatIP,
    embedding_model: SentenceTransformer,
    k: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    query_vec = embedding_fn([query], embedding_model)
    scores, ids = index.search(query_vec, k)  # type: ignore
    return scores, ids


add_embeddings(
    documents,
    index=deps.index,
    embedding_model=embedding_model,
)


@agent.system_prompt
async def get_system_prompt(context: RunContext[Deps]) -> str:
    return (
        "你是一个知识渊博的助手，擅长使用检索到的内容回答用户的问题。"
        "请先使用retrieve工具，找到相关内容，再基于相关内容回答用户的问题。"
    )


@agent.tool
async def retrieve(context: RunContext[Deps], search_query: str, k=2) -> str:
    scores, ids = search_embeddings(
        query=search_query,
        index=context.deps.index,
        embedding_model=context.deps.embedding_model,
        k=k,
    )

    results = []
    for i, idx in enumerate(ids[0]):
        results.append(f"Rank {i + 1}: {documents[idx]} (score={scores[0][i]:.4f})")
    logger.info(f"[bold magenta]Top {k} results:[/bold magenta]\n" + "\n".join(results))
    return "\n".join(results)


async def query(
    query: str, agent: Agent[Deps, ModelResponse], deps: Deps
) -> ModelResponse:
    logger.info(f"Query: [bold blue]{query}[/bold blue]")
    response = await agent.run(query, deps=deps)
    logger.info(f"Answer: [bold green]{response}[/bold green]")
    return response.output


@app.get("/query", response_model=ModelResponse, description="基于文本的RAG问答")
async def query_endpoint(query_request: QueryRequest):
    return await query(query_request.query, agent=agent, deps=deps)
