import logging
import os

import gradio as gr
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_litellm import ChatLiteLLM
from langchain_neo4j import Neo4jVector
from rich.logging import RichHandler

# 设置日志记录
logger = logging.getLogger("chat")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

# 从环境变量加载配置
load_dotenv()

# 初始化 LLM
llm = ChatLiteLLM(
    model="deepseek/deepseek-chat",
    temperature=0.7,
    api_key=os.getenv("API_KEY", "enter_your_api_key_in_.env"),
)

# 初始化 Embeddings 和 Neo4j
embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

neo4j_vector = Neo4jVector.from_existing_graph(
    embedding=embeddings,
    node_label="Document",
    embedding_node_property="embedding",
    text_node_properties=["name", "description"],
    url=os.getenv("NEO4J_URL", "enter_your_neo4j_url_in_.env"),
    username=os.getenv("NEO4J_USER", "enter_your_neo4j_username_in_.env"),
    password=os.getenv("NEO4J_PASSWORD", "enter_your_neo4j_password_in_.env"),
)


def retrieve_from_neo4j(query: str, top_k: int = 5):
    """从 Neo4j 检索相关上下文"""
    try:
        logger.info(f"🔍 正在检索与问题相关的知识: {query}")
        results = neo4j_vector.similarity_search(query, k=top_k)
        if not results:
            return []

        contexts = [doc.page_content for doc in results]
        logger.info(f"✅ 检索到 {len(contexts)} 条相关知识")
        logger.info(f"🔗 相关知识内容: {contexts}")
        return contexts
    except Exception as e:
        logger.error(f"❌ Neo4j 检索失败: {e}")
        return []


def rag_chat(query: str):
    """基于 RAG 的问答流程"""
    # 检索上下文
    context_list = retrieve_from_neo4j(query)
    if not context_list:
        return "未找到相关知识，请换个问题试试～"

    # 拼接上下文
    context_str = "\n".join(f"- {c}" for c in context_list)

    # 构建提示词
    prompt = f"""你是一个知识丰富的AI助手，请根据以下背景知识回答问题。

    背景知识:
    {context_str}

    问题:
    {query}

    请用简洁、准确的语言回答:
    """

    # 调用 LLM
    try:
        logger.info("🤖 正在生成回答...")
        response = llm.invoke(prompt)
        return str(response).strip()
    except Exception as e:
        logger.error(f"❌ LLM 调用失败: {e}")
        return "生成回答失败，请稍后再试。"


# Gradio 界面部分
def gradio_interface(user_query):
    return rag_chat(user_query)


with gr.Blocks(title="RAG 问答系统") as demo:
    gr.Markdown("# 💬 RAG 问答系统")
    with gr.Row():
        with gr.Column():
            user_input = gr.Textbox(
                label="请输入您的问题", placeholder="例如：脱敏民航是什么？"
            )
            submit_button = gr.Button("提交")
        with gr.Column():
            answer_output = gr.Textbox(
                label="🤖 回答", placeholder="AI 回答将在这里显示", lines=5
            )

    submit_button.click(fn=gradio_interface, inputs=user_input, outputs=answer_output)

# 启动 Gradio
if __name__ == "__main__":
    demo.launch()
