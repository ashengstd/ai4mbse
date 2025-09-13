# AI4MBSE - RAG 示例项目

这是一个简单的示例仓库，展示如何使用向量检索（FAISS）与 LLM agent（基于 pydantic-ai）构建文本检索增强生成（RAG, Retrieval-Augmented Generation）服务。

项目核心功能：

- 使用 Sentence-Transformers 生成文本嵌入。
- 使用 FAISS 做向量相似度检索。
- 使用 pydantic-ai 框架将检索工具与 LLM agent 结合，提供基于检索的回答。
- 提供一个 FastAPI HTTP 接口用于查询。

目录

- `rag.py`：主入口，包含向量索引构建、检索工具、Agent 配置和 FastAPI 接口。
- `pyproject.toml`：项目依赖与元信息。
- `README.md`：本文件。

快速开始（开发环境）

1. 准备 Python 3.12+ 环境（建议使用虚拟环境，例如 venv 或 conda）。

2. 安装依赖（示例使用 uv）：

```fish
uv sync
```

注意：仓库的 `pyproject.toml` 中声明了若干依赖，例如 `faiss-cpu`, `fastapi[standard]`, `pydantic-ai`, 和 `sentence-transformers`。请根据你的平台适配 FAISS（GPU 版本或 CPU 版本）。
FAISS-GPU 版本安装请参考 [FAISS 官方文档](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md)，需要走 conda 环境（也可以选择 pixi）。
环境变量

- API_KEY / API_BASE: 用于 LiteLLMProvider（或其它 LLM provider）的访问配置，代码通过 `python-dotenv` 的 `load_dotenv()` 自动加载 `.env` 文件。
- LOG_LEVEL: 可选，设置日志级别（默认 INFO）。

示例 `.env` 文件：

```text
MODEL=deepseek/deepseek-chat-v3.1:free
API_KEY=your_api_key_here
API_BASE=https://your-llm-provider.example
LOG_LEVEL=INFO
```

运行服务

```fish
# 运行 FastAPI 服务（示例使用 uvicorn）
uvicorn rag:app --host 0.0.0.0 --port 8000 --reload
```

API 使用

当服务运行后，打开 http://127.0.0.1:8000/docs 可以查看 OpenAPI 文档并直接调用 `/query` 接口。

GET /query

- 参数：query（字符串）
- 返回：JSON，包含 answer（模型回答）和 sources（用于检索的文档片段）

代码要点说明

- `rag.py` 中通过 `SentenceTransformer` 加载嵌入模型（示例路径 `/data1/hf-models/all-MiniLM-L6-v2`），并用 FAISS 的 `IndexFlatIP` 存储向量。
- 函数 `embedding_fn`, `add_embeddings`, `search_embeddings` 分别负责生成嵌入、添加到索引以及基于查询向量做最近邻检索。
- 使用 `pydantic_ai.Agent` 将检索工具（`@agent.tool def retrieve(...)`）注册到 agent；agent 的 `system_prompt` 会提示模型先检索再回答。

定制与扩展建议

- 向量数据库：当前示例使用内存中的 FAISS 索引；生产环境建议使用 Milvus、Weaviate 或 FAISS 持久化后端以支持大规模数据与持久化。
- 嵌入模型：可更换为 Hugging Face 的远程模型或更大/更小的本地模型以平衡成本与准确性。
- 多文档返回：当前示例返回 top-k 文档，建议在 agent 层做更细粒度的拼接与去重逻辑。
- 安全与速率限制：在生产环境中，为 API 添加认证与速率限制。

测试

- 目前仓库未包含单元测试；建议为检索函数、向量索引与 FastAPI 接口添加简单的 pytest 测试用例。

许可和贡献

欢迎提交 issue 和 PR。此项目采用自由协议（请在此处补充许可，例如 MIT）。

完成状态

- 本 README 基于仓库现有文件自动生成，已覆盖依赖、运行与 API 使用示例。如需更具体的部署脚本或 CI 配置，请告知。
