import json
import logging
import os
from contextlib import asynccontextmanager
from typing import LiteralString, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel
from rich.logging import RichHandler

from chat import extract_requirement_triples, query_by_subgraphs
from controller.graph import Neo4jGraphController
from controller.tmx import SysMLParser

load_dotenv()


# 日志配置
logger = logging.getLogger("triple_graph_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, markup=True)],
)

# 模型配置
llm = ChatLiteLLM(
    model="deepseek/deepseek-chat",
)


# 初始化 Graph Controller
def get_env_or_raise(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"环境变量 `{key}` 未设置，请检查 .env 文件")
    return value


graph_controller = Neo4jGraphController(
    url=get_env_or_raise("NEO4J_URL"),
    username=get_env_or_raise("NEO4J_USER"),
    password=get_env_or_raise("NEO4J_PASSWORD"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用启动时，检查并创建数据库索引
    """
    await graph_controller.ensure_indexes()
    yield
    await graph_controller.close()
    logger.info("Neo4j 连接已关闭")


app = FastAPI(title="Triple Graph API", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


class CypherRequest(BaseModel):
    cypher: LiteralString
    parameters: Optional[dict] = None
    token: str


@app.post("/extract_triples")
async def extract_triples_api(file: UploadFile = File(...)):
    """
    上传一段需求文本，提取三元组并返回 JSON
    """
    try:
        content = await file.read()
        result = await extract_requirement_triples(
            llm=llm, content=content.decode("utf-8")
        )
        return {"triples": result}
    except Exception as e:
        logger.error(f"提取三元组失败,报错: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="提取三元组失败，请检查输入文件格式或内容。"
        )


@app.post("/import_triples")
async def import_triples_api(file: UploadFile = File(...)):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="未上传文件")
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 .json 格式文件")
    try:
        content = await file.read()
        triples = json.loads(content)
        await graph_controller.import_triples(triples=triples)
    except Exception as e:
        logger.error(f"导入三元组失败,报错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    return {"message": "三元组导入成功"}


@app.post("/parse_tmx")
async def parse_tmx_api(file: UploadFile = File(...)):
    """
    上传一个 TMX 文件，提取图结构 JSON
    """
    content = await file.read()
    try:
        parser = SysMLParser(content.decode("utf-8"))
        parser.parse_all()
        graph = parser.triples_to_graph_json()
    except Exception as e:
        logger.error(f"解析 TMX 文件失败,报错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

    return {"graph": graph}


@app.post("/query")
async def query_api(request: QueryRequest):
    try:
        result = await query_by_subgraphs(
            llm=llm, graph_controller=graph_controller, question=request.question
        )
    except Exception as e:
        logger.error(f"查询失败,报错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    return {
        "question": request.question,
        "result": result if result else [],
        "message": "查询成功" if result else "未找到相关内容",
    }


@app.post("/cypher")
async def cypher_api(request: CypherRequest):
    """
    执行任意 Cypher 查询
    """
    if not request.token:
        raise HTTPException(status_code=400, detail="缺少身份验证令牌")
    if request.token != os.getenv("NEO4J_PASSWORD"):
        raise HTTPException(status_code=403, detail="无效的身份验证令牌")

    try:
        result = await graph_controller.execute_cypher(
            cypher=request.cypher, parameters=request.parameters
        )
        return {"result": result}
    except Exception as e:
        logger.error(f"Cypher 查询失败,报错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cypher 查询失败: {str(e)}")


@app.get("/")
def root():
    return {"message": "Triple Graph Web API 正常运行中 🚀"}
