# AI4MBSE - 面向模型的系统工程 AI 助手

一个基于大型语言模型（LLM）和 Neo4j 图数据库的知识图谱检索增强生成（RAG）问答系统，专注于模型基系统工程（MBSE）领域的知识处理和分析。

## 项目概述

本项目实现了一个端到端的 MBSE 知识图谱问答流程，包括：

- 从技术文档和 SysML 模型中自动提取建模领域的三元组知识。
- 支持 TMX 文件解析，以提取 SysML 模型结构。
- 将三元组知识导入 Neo4j 图数据库，以构建知识图谱。
- 基于 RAG（检索增强生成）的智能问答。
- 提供 RESTful API 和一个基于 Web 的交互界面。

## 功能特性

- **需求三元组提取**：从文本文档中自动提取与建模相关的结构化知识（三元组）。
- **SysML 模型解析**：支持解析 TMX 格式文件，以提取 SysML 模型结构和关系。
- **图构建**：将三元组导入 Neo4j，以构建可查询的知识图谱。
- **实体识别**：使用 LLM 从用户问题中识别关键实体。
- **子图检索**：根据已识别的实体执行子图查询。
- **向量检索**：支持基于语义相似性的文档检索。
- **RAG 问答**：通过结合检索到的知识生成准确的答案。
- **多重接口**：支持命令行工具、RESTful API 和 Web 界面。

## 技术栈

- **LLM**：deepseek-chat（通过 LiteLLM 集成）
- **图数据库**：Neo4j
- **RAG 框架**：LangChain
- **Web API**：FastAPI
- **依赖管理**：uv
- **SysML 解析**：自定义 TMX 解析器

## 快速开始

### 环境设置

1.  克隆仓库并进入项目目录：

    ```bash
    git clone <repository-url>
    cd ai4mbse
    ```

2.  使用 uv 安装依赖：

    ```bash
    uv sync
    ```

3.  配置环境变量（创建一个 `.env` 文件）：

    ```
    DEEPSEEK_API_KEY=your_deepseek_api_key
    NEO4J_URL=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password
    ```

### 用法

#### 1. 命令行工具

**从文本中提取三元组：**

```bash
python utils.py extract_triples --input_txt_path=path/to/input.txt --output_json_path=path/to/output.json
```

**解析 TMX 文件：**

```bash
python utils.py parse_tmx --input_tmx_path=path/to/model.tmx --output_json_path=path/to/graph.json
```

**导入知识图谱：**

```bash
python utils.py import_triples --triples_path=path/to/triples.json
```

**测试查询：**

```bash
python utils.py test_query
```

#### 2. Web API 服务

启动 FastAPI 服务器：

```bash
uvicorn web:app --reload
```

API 端点：

-   `POST /extract_triples` - 上传文档以提取三元组。
-   `POST /parse_tmx` - 上传 TMX 文件以解析模型结构。
-   `POST /import_triples` - 将三元组导入 Neo4j。
-   `POST /query` - 基于知识图谱进行查询。
-   `GET /` - 检查 API 状态。

您还可以运行测试脚本来检查后端 API：
```bash
./test_backend.sh
```

## 项目结构

```
ai4mbse/
├── chat/                    # 核心问答模块
│   ├── __init__.py
│   ├── query.py             # 问题处理和子图查询
│   ├── template.py          # LLM 提示模板
│   └── triple.py            # 三元组提取功能
├── controller/              # 控制器模块
│   ├── graph.py             # Neo4j 图数据库控制器
│   └── tmx.py               # SysML TMX 文件解析器
├── data/
│   ├── test_requirements.txt
│   ├── test_triples.json
│   └── trufun.tmx
├── utils.py                 # 命令行工具的入口点
├── web.py                   # FastAPI Web 服务
├── test_backend.sh          # 后端 API 的测试脚本
├── pyproject.toml           # 项目配置和依赖管理
├── uv.lock                  # 依赖锁定文件
├── .env                     # 环境配置文件（由用户创建）
└── README.md                # 项目文档
```

## API 文档

### 三元组提取 API

```http
POST /extract_triples
Content-Type: multipart/form-data

# 上传一个文本文件以返回提取的三元组。
```

### TMX 解析 API

```http
POST /parse_tmx
Content-Type: multipart/form-data

# 上传一个 TMX 文件以返回解析后的图结构。
```

### 知识导入 API

```http
POST /import_triples
Content-Type: multipart/form-data

# 上传一个包含三元组的 JSON 文件以导入 Neo4j。
```

### 问答 API

```http
POST /query
Content--Type: application/json

{
  "question": "分析机上通信的需求。"
}
```

## 依赖

主要依赖包括：

-   `fastapi[standard]` - Web API 框架
-   `langchain` - LLM 应用开发框架
-   `langchain-litellm` - LiteLLM 集成
-   `langchain-neo4j` - Neo4j 集成
-   `neo4j` - Neo4j 数据库驱动
-   `fire` - 命令行界面生成
-   `rich` - 终端美化

## 许可证

本项目采用开源许可证。详情请参阅 LICENSE 文件。