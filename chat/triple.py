import asyncio
import json
import logging
from typing import Any, Coroutine

from langchain.prompts import PromptTemplate
from langchain_litellm import ChatLiteLLM
from rich.logging import RichHandler

from chat.template import triple_prompt_template

logger = logging.getLogger("triple_extractor")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, markup=True)],
)


# --- 加载 txt 文件并分段 ---
def split_paragraphs(content: str) -> list[str]:
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    return paragraphs


async def extract_triples_from_paragraphs(
    llm: ChatLiteLLM,
    p1: str,
    p2: str,
    p3: str,
    p4: str,
    logger: logging.Logger,
) -> str:
    """
    使用 LLM 从四个段落中提取三元组。
    Args:
        p1, p2, p3, p4 (str): 四个段落文本
    Returns:
        str: LLM 返回的 JSON 格式字符串
    """
    prompt = PromptTemplate(
        input_variables=["p1", "p2", "p3", "p4"], template=triple_prompt_template
    ).format(p1=p1, p2=p2, p3=p3, p4=p4)
    logger.info(f"🧠 正在处理段落：\n{p1}\n{p2}\n{p3}\n{p4}")
    response = llm.invoke(prompt)
    if not response.content:
        logger.error("❌ LLM 响应内容为空，请检查模型配置或输入段落。")
        return ""
    return str(response.content)


# --- 主流程（修改滑动窗口为4段，步长3） ---
async def extract_requirement_triples(
    llm: ChatLiteLLM,
    content: str,
    window_size=4,
    step=3,
) -> dict:
    """
    从输入文本中提取需求相关的三元组，并返回 JSON 。
    Args:
        content (str): 输入文本文件内容
        window_size (int): 窗口大小，默认为4段
        step (int): 步长，默认为3段
    """
    paragraphs = split_paragraphs(content)
    output_triples = []

    tasks: list[Coroutine[Any, Any, str]] = []
    total_windows = (len(paragraphs) - window_size) // step + 1

    for i in range(total_windows):
        start_idx = i * step
        window_paragraphs = paragraphs[start_idx : start_idx + window_size]

        # 确保有4段
        if len(window_paragraphs) < window_size:
            break

        tasks.append(
            extract_triples_from_paragraphs(
                llm=llm,
                p1=window_paragraphs[0],
                p2=window_paragraphs[1],
                p3=window_paragraphs[2],
                p4=window_paragraphs[3],
                logger=logger,
            )
        )

    results = await asyncio.gather(*tasks)

    for i, result in enumerate(results):
        try:
            result_json = json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"❌ JSON 解析失败：{result}")
            continue

        triples = result_json.get("triples", [])  # 注意这里用 "triples"
        output_triples.extend(triples)
        logger.info(f"✅ 已处理窗口 {i + 1}/{total_windows}")

    logger.info(f"🎉 提取完成，共提取三元组数: {len(output_triples)}")
    return {"triples": output_triples}


if __name__ == "__main__":
    # 测试代码
    test_content = (
        "系统应该允许用户登录。\n"
        "用户可以使用用户名和密码进行认证。\n"
        "系统具有一系列安全措施。\n"
        "系统保证用户的独一。"
    )
    llm = ChatLiteLLM(model="deepseek/deepseek-chat")
    result = asyncio.run(extract_requirement_triples(llm=llm, content=test_content))
    print(json.dumps(result, ensure_ascii=False, indent=2))
