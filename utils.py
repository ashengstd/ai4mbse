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
    # 设置日志记录
    logger = logging.getLogger("query")
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    # 初始化 LLM
    llm = ChatLiteLLM(
        model="deepseek/deepseek-chat",
        temperature=0.7,
    )
    load_dotenv()
    graph_controller = Neo4jGraphController(
        url=os.getenv("NEO4J_URL", "enter_your_neo4j_url_in_.env"),
        username=os.getenv("NEO4J_USER", "enter_your_neo4j_username_in_.env"),
        password=os.getenv("NEO4J_PASSWORD", "enter_your_neo4j_password_in_.env"),
    )
    questions = [
        "什么是脱敏民航",
        "sysml有哪些视图",
        "UML的类图和时序图有什么区别",
        "需求图包含哪些元素",
    ]

    for q in questions:
        query_by_subgraphs(
            llm=llm, graph_controller=graph_controller, logger=logger, question=q
        )


def extract_triples(input_txt: Path, output_json: Path):
    input_txt = Path(input_txt)
    output_json = Path(output_json)
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
        llm=llm, input_path=input_txt, output_path=output_json, logger=logger
    )


def tasks(
    task: Literal["import_triples"],
    triples_path=Optional[str],
    input_txt=Optional[str],
    output_json=Optional[str],
):
    """
    执行指定任务
    可用任务:
    - import_triples: 导入三元组数据到 Neo4j
    - test_query: 测试查询功能
    - extratct_triples: 从文本中提取需求相关的三元组并保存为 JSON 文件
    Args:
        task (str): 任务名称
        triples_path (str, optional): 三元组文件路径，仅在 task 为 import_triples 时需要
        input_txt (str, optional): 输入文本文件路径，仅在 task 为 extratct_triples 时需要
        output_json (str, optional): 输出 JSON 文件路径，仅在 task 为 extratct_triples 时需要
    """
    if task not in ["import_triples", "test_query", "extratct_triples"]:
        raise ValueError(
            f"未知任务: {task}. 可用任务: import_triples, test_query, extratct_triples"
        )
    if task == "import_triples":
        import_triples(triples_path)
    elif task == "test_query":
        test_query()
    elif task == "extratct_triples":
        extract_triples(input_txt, output_json)


if __name__ == "__main__":
    load_dotenv()
    Fire(tasks)
