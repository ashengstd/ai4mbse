import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel
from rich.logging import RichHandler

from chat import extract_requirement_triples, query_by_subgraphs
from controller.graph import Neo4jGraphController
from controller.tmx import SysMLParser

load_dotenv()
app = FastAPI(title="Triple Graph API")

# 日志配置
logger = logging.getLogger("triple_extractor")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

# 初始化 Graph Controller
graph_controller = Neo4jGraphController(
    url=os.getenv("NEO4J_URL", ""),
    username=os.getenv("NEO4J_USER", ""),
    password=os.getenv("NEO4J_PASSWORD", ""),
)


class QueryRequest(BaseModel):
    question: str


# 临时保存上传文件
def save_upload_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(upload_file.file.read())
        return Path(tmp.name)


@app.post("/extract_triples")
async def extract_triples_api(file: UploadFile = File(...)):
    """
    上传一段需求文本，提取三元组并返回 JSON
    """
    input_path = save_upload_file(file)
    output_path = input_path.with_suffix(".json")

    llm = ChatLiteLLM(model="deepseek/deepseek-chat", temperature=0.7)
    extract_requirement_triples(
        llm=llm, input_path=input_path, output_path=output_path, logger=logger
    )

    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    # 清理临时文件
    input_path.unlink()
    output_path.unlink()

    return {"triples": result}


@app.post("/import_triples")
async def import_triples_api(file: UploadFile = File(...)):
    """
    上传一个三元组 JSON 文件，导入 Neo4j
    """
    triples_path = save_upload_file(file)
    try:
        graph_controller.import_triples(triples_path=triples_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    finally:
        triples_path.unlink()
    return {"message": "三元组导入成功"}


@app.post("/parse_tmx")
async def parse_tmx_api(file: UploadFile = File(...)):
    """
    上传一个 TMX 文件，提取图结构 JSON
    """
    input_path = save_upload_file(file)
    try:
        parser = SysMLParser(input_path)
        parser.parse_all()
        graph = parser.triples_to_graph_json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        input_path.unlink()

    return {"graph": graph}


@app.post("/query")
async def query_api(request: QueryRequest):
    llm = ChatLiteLLM(model="deepseek/deepseek-chat")
    try:
        result = query_by_subgraphs(
            llm=llm, graph_controller=graph_controller, question=request.question
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    return {"question": request.question, "result": result or "无结果"}


@app.get("/")
def root():
    return {"message": "Triple Graph Web API 正常运行中 🚀"}
