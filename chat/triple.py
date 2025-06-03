import json
import logging
from pathlib import Path

from langchain.prompts import PromptTemplate
from langchain_litellm import ChatLiteLLM

from chat.template import triple_prompt_template


# --- 加载 txt 文件并分段 ---
def split_paragraphs(path: Path) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    return paragraphs


def extract_triples_from_paragraphs(
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
def extract_requirement_triples(
    llm: ChatLiteLLM,
    input_path: Path,
    output_path: Path,
    window_size=4,
    step=3,
    logger: logging.Logger = logging.getLogger("triple_extractor"),
):
    """
    从输入文本中提取需求相关的三元组，并保存为 JSON 文件。
    Args:
        input_path (Path): 输入文本文件路径
        output_path (Path): 输出 JSON 文件路径
        window_size (int): 窗口大小，默认为4段
        step (int): 步长，默认为3段
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"输入文件不存在或者错误：{input_path}")

    paragraphs = split_paragraphs(input_path)
    output_triples = []

    total_windows = (len(paragraphs) - window_size) // step + 1

    for i in range(total_windows):
        start_idx = i * step
        window_paragraphs = paragraphs[start_idx : start_idx + window_size]

        # 确保有4段
        if len(window_paragraphs) < window_size:
            break

        result = extract_triples_from_paragraphs(
            llm=llm,
            p1=window_paragraphs[0],
            p2=window_paragraphs[1],
            p3=window_paragraphs[2],
            p4=window_paragraphs[3],
            logger=logger,
        )

        try:
            result_json = json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"❌ JSON 解析失败：{result}")
            continue

        triples = result_json.get("triples", [])  # 注意这里用 "triples"
        output_triples.extend(triples)
        logger.info(f"✅ 已处理窗口 {i + 1}/{total_windows}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {"requirement_triples": output_triples}, f, indent=2, ensure_ascii=False
        )

    logger.info(f"\n🎉 提取完成，共提取三元组数: {len(output_triples)}")
