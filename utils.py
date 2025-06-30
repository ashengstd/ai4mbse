import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from fire import Fire  # type: ignore
from langchain_litellm import ChatLiteLLM
from rich.logging import RichHandler

from chat import extract_requirement_triples, query_by_subgraphs
from controller.graph import Neo4jGraphController
from controller.tmx import SysMLParser


def import_triples(triples_path: Path):
    """导入三元组数据到 Neo4j"""
    triples_path = Path(triples_path)
    graph_controller = Neo4jGraphController(
        url=os.getenv("NEO4J_URL", "enter_your_neo4j_url_in_.env"),
        username=os.getenv("NEO4J_USER", "enter_your_neo4j_username_in_.env"),
        password=os.getenv("NEO4J_PASSWORD", "enter_your_neo4j_password_in_.env"),
    )
    if not triples_path.exists():
        raise FileNotFoundError(f"文件 {triples_path} 不存在")

    graph_controller.import_triples(triples_path=triples_path)
    print(f"✅ 成功导入三元组数据: {triples_path}")


def test_query():
    # 初始化 LLM
    llm = ChatLiteLLM(
        model="deepseek/deepseek-chat",
    )
    graph_controller = Neo4jGraphController(
        url=os.getenv("NEO4J_URL", "enter_your_neo4j_url_in_.env"),
        username=os.getenv("NEO4J_USER", "enter_your_neo4j_username_in_.env"),
        password=os.getenv("NEO4J_PASSWORD", "enter_your_neo4j_password_in_.env"),
    )
    questions = [
        "分析机内通话的需求",
    ]

    for q in questions:
        query_by_subgraphs(llm=llm, graph_controller=graph_controller, question=q)


def extract_triples(input_txt_path: Path, output_json_path: Path):
    input_txt_path = Path(input_txt_path)
    output_json_path = Path(output_json_path)
    logger = logging.getLogger("triple_extractor")

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    llm = ChatLiteLLM(
        model="deepseek/deepseek-chat",
        temperature=0.7,
    )
    extract_requirement_triples(
        llm=llm, input_path=input_txt_path, output_path=output_json_path, logger=logger
    )


def parse_tmx(input_tmx_path: Path, output_json_path: Path):
    input_tmx_path = Path(input_tmx_path)
    parser = SysMLParser(input_tmx_path)
    parser.parse_all()
    graph = parser.triples_to_graph_json()
    with open(output_json_path, "w") as f:
        json.dump(graph, f, ensure_ascii=False, indent=4)
    print(f"📊 已提取图数据结构（JSON格式）: {output_json_path}")


def check_path(path):
    if not path:
        raise ValueError("路径不能为空")
    if not Path(path).exists():
        raise FileNotFoundError(f"文件 {path} 不存在")


def tasks(
    task: Literal["import_triples", "test_query", "extract_triples", "parse_tmx"],
    triples_path: Optional[str] = None,
    input_txt_path: Optional[str] = None,
    input_tmx_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
):
    """
    执行指定任务
    可用任务:
    - import_triples: 导入三元组数据到 Neo4j
    - test_query: 测试查询功能
    - extract_triples: 从文本中提取需求相关的三元组并保存为 JSON 文件
    Args:
        task (str): 任务名称
        triples_path (str, optional): 三元组文件路径，仅在 task 为 import_triples 时需要
        input_txt_path (str, optional): 输入文本文件路径，仅在 task 为 extract_triples 时需要
        output_json_path (str, optional): 输出 JSON 文件路径，在 task 为 extract_triples 和 parse_tmx 时需要
        input_tmx_path (str, optional): 输入 TMX 文件路径，仅在 task 为 parse_tmx 时需要
    """
    if task not in ["import_triples", "test_query", "extract_triples", "parse_tmx"]:
        raise ValueError(
            f"未知任务: {task}. 可用任务: import_triples, test_query, extract_triples"
        )
    if task == "import_triples":
        check_path(triples_path)
        import_triples(triples_path)
    elif task == "test_query":
        test_query()
    elif task == "extract_triples":
        check_path(input_txt_path)
        extract_triples(input_txt_path, output_json_path)
    elif task == "parse_tmx":
        check_path(input_tmx_path)
        parse_tmx(input_tmx_path, output_json_path)


if __name__ == "__main__":
    load_dotenv()
    Fire(tasks)
