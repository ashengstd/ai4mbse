import logging
import re
from typing import Optional

from neo4j import AsyncGraphDatabase, AsyncSession
from rich.logging import RichHandler

logger = logging.getLogger("graph_controller")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, markup=True)],
)


def safe_name(name: str) -> str:
    """
    将标签或关系类型中的非法字符替换为下划线
    - 只允许字母、数字、下划线
    - 多个连续下划线合并为一个
    - 不允许以数字开头
    """
    # 替换非法字符为 _
    safe = re.sub(r"[^\w]", "_", name)
    # 合并连续下划线
    safe = re.sub(r"_+", "_", safe)
    # 去除首尾下划线（可选）
    safe = safe.strip("_")
    # 避免以数字开头
    if re.match(r"^\d", safe):
        safe = f"_{safe}"
    return safe


class Neo4jGraphController:
    def __init__(self, url: str, username: str, password: str):
        self.driver = AsyncGraphDatabase.driver(url, auth=(username, password))

    async def close(self):
        await self.driver.close()

    async def ensure_indexes(self):
        """
        确保数据库中的索引存在，如果不存在则创建。
        """
        logger.info("🔍 正在检查并确保数据库索引...")
        async with self.driver.session() as session:
            # 为节点的 name 属性创建索引，以加速实体匹配
            index_query = "CREATE INDEX node_name_index IF NOT EXISTS FOR (n:LabelName) ON (n.name)"
            await session.run(index_query)
            logger.info("✅ 索引 'node_name_index' 已确保存在。")

    async def query(
        self,
        cypher: str,
        parameters: Optional[dict] = None,
        session: Optional[AsyncSession] = None,
    ) -> list:
        """
        执行 Cypher 查询，支持外部 Session 复用。
        """
        if session:
            result = await session.run(cypher, parameters or {})
            return await result.data()
        async with self.driver.session() as session:
            result = await session.run(cypher, parameters or {})
            return await result.data()

    async def import_triples(self, triples: dict) -> None:
        if not triples or "triples" not in triples:
            raise ValueError("三元组数据格式不正确，请检查 LLM 输出。")

        async with self.driver.session() as session:
            async with session.begin_transaction() as tx:
                for triple in triples["triples"]:
                    head = triple["head"]
                    relation = triple["relation"]
                    tail = triple["tail"]

                    head_label = safe_name(head["label"])
                    tail_label = safe_name(tail["label"])
                    rel_type = safe_name(relation["type"])

                    # MERGE head node
                    await tx.run(
                        f"""
                        MERGE (h:{head_label} {{id: $head_id}})
                        SET h += $head_properties
                        """,
                        {
                            "head_id": head.get("id"),
                            "head_properties": head.get("properties", {}),
                        },
                    )

                    # MERGE tail node
                    await tx.run(
                        f"""
                        MERGE (t:{tail_label} {{id: $tail_id}})
                        SET t += $tail_properties
                        """,
                        {
                            "tail_id": tail.get("id"),
                            "tail_properties": tail.get("properties", {}),
                        },
                    )

                    # MERGE relation
                    await tx.run(
                        f"""
                        MATCH (h:{head_label} {{id: $head_id}}), (t:{tail_label} {{id: $tail_id}})
                        MERGE (h)-[r:{rel_type}]->(t)
                        SET r += $relation_properties
                        """,
                        {
                            "head_id": head.get("id"),
                            "tail_id": tail.get("id"),
                            "relation_properties": relation.get("properties", {}),
                        },
                    )

    async def search_likely_entities(
        self, entities: list[str], threshold: float = 0.5, top_k: int = 5
    ) -> list[str]:
        if not entities:
            return []

        cypher = """
        UNWIND $entities AS entity
        MATCH (n)
        WHERE n.name IS NOT NULL AND apoc.text.sorensenDiceSimilarity(n.name, entity) >= $threshold
        WITH entity, n, apoc.text.sorensenDiceSimilarity(n.name, entity) AS similarity
        ORDER BY similarity DESC
        WITH entity, collect(n.name)[..$top_k] AS matches
        RETURN apoc.coll.toSet(apoc.coll.flatten(collect(matches))) AS all_matches
        """
        async with self.driver.session() as session:
            res = await session.run(
                cypher, {"entities": entities, "threshold": threshold, "top_k": top_k}
            )
            data = await res.single()
            if data and data["all_matches"]:
                return data["all_matches"]
        return []

    async def query_subgraph(
        self, entities: list[str], depth: int = 4, limit: int = 20
    ) -> list[dict[str, list[dict]]]:
        # 查询子图只返回节点和关系的名称和描述
        if not entities:
            return []

        cypher = """
        MATCH (n)
        WHERE n.name IN $entities
        CALL apoc.path.expand(n, null, null, 0, $depth) YIELD path
        WITH collect(path) AS paths
        WITH apoc.coll.flatten([p IN paths | nodes(p)]) AS all_nodes, 
            apoc.coll.flatten([p IN paths | relationships(p)]) AS all_rels
        WITH apoc.coll.toSet(all_nodes) AS nodes, apoc.coll.toSet(all_rels) AS relationships
        WITH nodes, relationships, $limit AS limit
        WITH
            [i IN range(0, size(nodes) - 1) WHERE i < limit | nodes[i]] AS sliced_nodes,
            [i IN range(0, size(relationships) - 1) WHERE i < limit | relationships[i]] AS sliced_relationships
        RETURN 
            [node IN sliced_nodes | {name: node.name, description: node.description}] AS nodes,
            [rel IN sliced_relationships | {type: type(rel), start: startNode(rel).name, end: endNode(rel).name}] AS relationships
        """
        subgraphs = await self.query(
            cypher, {"entities": entities, "depth": depth, "limit": limit}
        )
        if not subgraphs:
            return []

        return subgraphs


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    graph_controller = Neo4jGraphController(
        url=os.getenv("NEO4J_URL", "enter_your_neo4j_url_in_.env"),
        username=os.getenv("NEO4J_USER", "enter_your_neo4j_username_in_.env"),
        password=os.getenv("NEO4J_PASSWORD", "enter_your_neo4j_password_in_.env"),
    )
