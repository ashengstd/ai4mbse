# RAG 知识图谱问答系统

基于 LLM（大语言模型）和 Neo4j 图数据库构建的知识图谱检索增强生成(RAG)问答系统，专注于建模领域知识。

## 项目概述

本项目实现了一个端到端的知识图谱问答流程，包括：

- 从技术文档中自动提取建模领域的三元组知识
- 将三元组知识导入 Neo4j 图数据库构建知识图谱
- 基于 RAG（检索增强生成）的智能问答
- Web 交互界面

## 功能特性

- **知识提取**：从文本中自动提取建模相关的结构化知识（三元组）
- **图谱构建**：将三元组导入 Neo4j，构建可查询的知识图谱
- **实体识别**：使用 LLM 从用户问题中识别关键实体
- **子图检索**：根据识别到的实体进行子图查询
- **向量检索**：支持语义相似度的文档检索
- **RAG 问答**：结合检索到的知识生成准确答案
- **双重界面**：同时支持命令行和 Web 交互界面

## 技术栈

- **LLM**：deepseek-chat
- **向量嵌入**：HuggingFaceEmbeddings (intfloat/multilingual-e5-large)
- **图数据库**：Neo4j
- **RAG 框架**：LangChain
- **Web 界面**：Gradio
- **环境管理**：Pixi

## 快速开始

### 环境配置

1. 克隆仓库并进入项目目录

```fish
git clone <repository-url>
cd llm-chat
```

2. 使用 pixi 创建并激活环境

```fish
pixi install
pixi shell
```

3. 配置环境变量（创建.env 文件）

```
API_KEY=your_api_key
NEO4J_URL=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 运行方式

#### 三元组提取

```fish
python utils.py extratct_triples --input_txt=path/to/input.txt --output_json=path/to/output.json
```

#### 导入知识图谱

```fish
python utils.py import_triples --triples_path=path/to/triples.json
```

## 项目结构

```
llm-chat/
├── chat/                  # 核心问答功能
│   ├── __init__.py
│   ├── query.py           # 问题处理和子图查询
│   ├── template.py        # 提示词模板
│   └── triple.py          # 三元组提取功能
├── controller/
│   └── graph.py           # Neo4j图数据库控制器
├── .env                   # 环境配置文件（需自行创建）
├── .gitignore
├── pixi.toml              # Pixi环境配置
└── utils.py               # 工具函数集合
```
