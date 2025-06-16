import logging
from typing import Optional

from langchain.prompts import PromptTemplate
from langchain_litellm import ChatLiteLLM

from chat.template import entity_prompt_template
from controller.graph import Neo4jGraphController


# --- 实体提取函数 ---
def extract_entities(
    llm: ChatLiteLLM, question: str, logger: logging.Logger
) -> list[str]:
    """
    使用 LLM 从问题中提取实体列表。
    Args:
        question (str): 用户提问
    Returns:
        list: 提取到的实体列表
    例如：['比尔·盖茨', '苹果公司', '马斯克', '飞机']
    """
    logger.info(f"🧠 正在提取实体: {question}")
    entities_text = llm.invoke(
        PromptTemplate(
            input_variables=["question"], template=entity_prompt_template
        ).format(question=question)
    ).content
    if not isinstance(entities_text, str):
        logger.error("❌ 实体提取结果不是字符串类型，请检查 LLM 响应格式。")
        return []
    entities_text_list = entities_text.split(",")
    entities = [
        e.strip().strip("'").strip('"') for e in entities_text_list if e.strip()
    ]
    logger.info(f"✅ 提取到实体: {entities}")
    return entities


# --- 问题处理主流程 ---
def query_by_subgraphs(
    llm: ChatLiteLLM,
    graph_controller: Neo4jGraphController,
    logger: logging.Logger,
    question: str,
    depth=2,
    limit=20,
) -> Optional[str]:
    # 1. 提取实体
    entities = extract_entities(llm=llm, question=question, logger=logger)
    if not entities:
        logger.warning("⚠️ 没有提取到实体，无法进行子图查询。")
        return None

    # 2.与数据库中的实体进行检索
    logger.info(f"🔍 查询实体: {entities}")
    likely_entities = graph_controller.search_likely_entities(entities)
    if not likely_entities:
        logger.warning("⚠️ 没有找到匹配的实体，无法进行子图查询。")
        return None
    logger.info(f"✅ 匹配到的实体: {likely_entities}")

    # 3. 查询子图
    subgraphs = graph_controller.query_subgraph(
        likely_entities, depth=depth, limit=limit
    )
    if not subgraphs:
        logger.warning("⚠️ 子图查询结果为空。")
        return None
    logger.info(f"🌟 子图查询成功，结果数量: {len(subgraphs)}，内容为：{subgraphs}")

    # 4. 再次格式化问题
    prompt = PromptTemplate(
        input_variables=["question", "subgraph"],
        template="请根据以下子图信息回答问题：\n\n{question}\n\n子图信息：{subgraph}",
    )
    question = prompt.format(question=question, subgraph=subgraphs)
    answer = llm.invoke(question).content
    logger.info(f"📝 格式化后的问题: {question}")
    logger.info(f"💡 回答: {answer}")
    return answer
