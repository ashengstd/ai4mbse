import io
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.logging import RichHandler

# --- 日志记录器设置 ---
logger = logging.getLogger("SysMLParser")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, markup=True)],
)


class SysMLParser:
    """
    SysMLParser 用于解析 SysML XML 文件，提取需求图、内部块图、块图、用例图和活动图等结构信息。
    支持提取模型元素的名称、ID、连接关系等，并将其存储为三元组形式。
    """

    def __init__(self, file_content: str):
        self.file_content = file_content
        self.root = None
        self.namespaces = {}
        self._model_elements_by_id = {}  # 新增: 全局模型元素ID到名称的映射
        self.triples = []  # 用于存储提取的三元组

        self.load_xml()

    def load_xml(self):
        # 解析命名空间（关键修复）
        # 使用列表推导式确保迭代器在使用后被清空，或者至少只迭代一次
        ns_list = []
        f = io.StringIO(self.file_content)
        for event, (prefix, uri) in ET.iterparse(f, events=["start-ns"]):
            ns_list.append((prefix, uri))
        self.namespaces = {
            prefix if prefix else "default": uri for prefix, uri in ns_list
        }

        # 使用 ElementTree 加载并解析 XML 内容
        tree = ET.fromstring(self.file_content)
        self.root = tree

        # --- 新增: 遍历所有元素，构建全局ID到名称的映射 ---
        # 这有助于在解析引用（如生命线的owner）时查找名称
        for elem in self.root.iter():
            elem_id = elem.get(f"{{{self.namespaces.get('xmi', '')}}}id")
            elem_name = elem.get("name")
            if elem_id:
                if elem_name:
                    self._model_elements_by_id[elem_id] = elem_name
                else:
                    # 尝试从StereotypeNodes中获取名称，例如 <<block>>
                    # 需要确保 findall/find 传入 namespaces
                    stereotype_nodes = elem.find(
                        "./stereotypeNodes", namespaces=self.namespaces
                    )
                    if stereotype_nodes is not None:
                        stereotype_name = stereotype_nodes.get("name")
                        if stereotype_name:
                            self._model_elements_by_id[elem_id] = stereotype_name.strip(
                                "<>"
                            ).strip()
                            continue
                    # 尝试从SubLabels中获取主名称
                    sub_label_name_elem = elem.find(
                        "./subLabels[@alias='Name']", namespaces=self.namespaces
                    )
                    if sub_label_name_elem is not None:
                        self._model_elements_by_id[elem_id] = sub_label_name_elem.get(
                            "name"
                        ).strip()
                        continue

                    # Fallback: use xmi:type as a descriptor if no name found
                    elem_xmi_type = elem.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    if elem_xmi_type:
                        self._model_elements_by_id[elem_id] = (
                            self._strip_ns(elem_xmi_type)
                            .replace("trufun:", "")
                            .replace("T", "")
                            + " (类型)"
                        )
                    else:
                        self._model_elements_by_id[elem_id] = (
                            f"未知元素 (ID: {elem_id})"
                        )
        # --- 结束新增 ---

        logger.info("✅ 成功加载 XML 文件")

    def _strip_ns(self, tag):
        return tag.split("}")[-1] if "}" in tag else tag

    def extract_requirement_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取需求图。[/bold yellow]"
            )
            return

        logger.info("\n📜 [bold yellow]开始提取需求图及其结构关系[/bold yellow]")

        # Iterate through all elements to find Requirement Diagrams
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # Find the diagram element based on its stereotype
            if (
                tag == "contents"
                and elem.get("stereotype") == "SysmlRequirementDiagram"
            ):
                req_diagram_elem = elem
                diagram_name = req_diagram_elem.get("name", "未命名需求图")
                logger.info(f"\n🧾 分析需求图: [bold]{diagram_name}[/bold]")

                # --- 1. Extract all Requirement nodes and their properties ---
                node_id_to_name = {}
                for node in req_diagram_elem.findall(
                    ".//nodes[@stereotype='<<requirement>>']",
                    namespaces=self.namespaces,
                ):
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    req_name = node.get("name", "未命名需求").strip()

                    if node_id:
                        node_id_to_name[node_id] = req_name
                        logger.info(
                            f"  🔹 发现需求节点: [bold green]{req_name}[/bold green]"
                        )

                        props_compartment = node.find(
                            "./nodes[@type='stereotype_properties']",
                            namespaces=self.namespaces,
                        )
                        if props_compartment is not None:
                            for prop in props_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                prop_name = prop.get("name", "未命名属性").strip()
                                clean_prop_name = prop_name.split(":")[0].strip()
                                logger.info(
                                    f"    🔸 属性: [cyan]{clean_prop_name}[/cyan]"
                                )

                # --- 2. Extract and resolve connections (relationships) ---
                found_connections = False
                for conn in req_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        # --- THIS IS THE CORRECTED LOGIC ---
                        conn_type = "Unknown"  # Default value

                        # Priority 1: Check for a 'stereotype' attribute (e.g., "<<allocate>>")
                        stereotype_attr = conn.get("stereotype")
                        if stereotype_attr:
                            conn_type = stereotype_attr.strip("<>").capitalize()
                        else:
                            # Priority 2: Check for a 'type' attribute (e.g., "New.ContainmentConnection")
                            type_attr = conn.get("type")
                            if type_attr:
                                conn_type = (
                                    type_attr.split(".")[-1]
                                    if "." in type_attr
                                    else type_attr
                                )
                        # --- END OF CORRECTED LOGIC ---

                        logger.info(
                            f"  🔗 关系 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  -> No connections found in this diagram.")

    def extract_internal_block_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取内部块图。[/bold yellow]"
            )
            return

        logger.info("\n🧩 [bold magenta]开始提取内部块图及其连接关系[/bold magenta]")

        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            if (
                tag == "contents"
                and elem.get("stereotype") == "SysmlInternalBlockDiagram"
            ):
                diagram_name = elem.get("name", "未命名内部块图")
                logger.info(f"\n📊 分析内部块图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}
                # 为了包含最外层上下文块以及内部的part property和port
                # 遍历所有可能作为节点的元素，包括 TStructureClassNode (上下文), TModelElementNode (part), TPortNode
                # 以及这些节点内部的SubLabel等，但SubLabel通常只用于显示，不作为独立node_id_to_name的键
                for node in elem.findall(".//nodes", namespaces=self.namespaces):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get(
                        "name", ""
                    ).strip()  # 端口可能没有name，或name是带冒号的

                    if node_id:
                        display_name = node_name  # 默认显示名称

                        if node_xmi_type == "trufun:TStructureClassNode":
                            display_name = f"上下文块: {node_name}"
                        elif (
                            node_xmi_type == "trufun:TModelElementNode"
                            and node.get("type") == "SysML.IBD.PartProperty"
                        ):
                            # 部件属性通常以冒号开头
                            display_name = f"部件: {node_name.lstrip(': ').strip()}"
                        elif node_xmi_type == "trufun:TPortNode":
                            # 端口名称可能带有类型信息和波浪线（反向接口）
                            display_name = f"端口: {node_name.replace(':', '').replace('~', '').strip()}"
                        elif node_xmi_type == "trufun:SubLabel":
                            # SubLabel 仅为可视化标签，不作为独立逻辑节点加入映射
                            continue
                        else:
                            # Fallback for other unexpected node types
                            if node_name:  # 确保有名称才记录
                                display_name = f"其他节点 ({self._strip_ns(node_xmi_type)}): {node_name}"
                            else:  # 如果没名称，就用ID
                                display_name = f"其他节点 ({self._strip_ns(node_xmi_type)}): ID {node_id}"

                        node_id_to_name[node_id] = display_name
                        # 仅记录主要节点类型，不记录所有SubLabel或 CompartmentNode
                        if (
                            "CompartmentNode" not in node_xmi_type
                            and "SubLabel" not in node_xmi_type
                        ):
                            logger.info(f"  🟢 {display_name}")

                found_connections = False
                for conn in elem.findall("./connections", namespaces=self.namespaces):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        # --- 修改的连接类型识别逻辑 ---
                        conn_type = "Unknown"  # Default value

                        # 优先级1: 检查 specific 'type' attribute (e.g., SysML.IBD.Connector)
                        specific_type_attr = conn.get("type")
                        if specific_type_attr == "SysML.IBD.Connector":
                            conn_type = "Connector"
                        else:
                            # 优先级2: 检查 xmi:type 属性
                            conn_xmi_type = conn.get(
                                f"{{{self.namespaces.get('xmi', '')}}}type"
                            )
                            if conn_xmi_type:
                                # Use the explicit xmi:type, e.g., "trufun:TModelElementConnection"
                                type_name = conn_xmi_type.split(":")[-1]
                                conn_type = type_name.replace("T", "").replace(
                                    "Connection", ""
                                )
                            else:
                                # 优先级3: Fallback for safety (use tag name)
                                conn_type = self._strip_ns(conn.tag)
                        # --- 结束修改的连接类型识别逻辑 ---

                        logger.info(
                            f"  🔗 连接 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_block_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取块图。[/bold yellow]"
            )
            return

        logger.info("\n📘 [bold blue]提取块图及其结构关系[/bold blue]")

        # Iterate through all elements to find Block Diagrams
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # Find the diagram element
            if tag == "contents" and elem.get("stereotype") == "SysmlBlockDiagram":
                bdd_elem = elem
                diagram_name = bdd_elem.get("name", "未命名块图")
                logger.info(f"\n📊 分析块图: [bold]{diagram_name}[/bold]")

                # --- 1. Extract all nodes (Blocks, ValueTypes, etc.) in this diagram ---
                node_id_to_name = {}
                for node in bdd_elem.findall(
                    ".//nodes[@name]", namespaces=self.namespaces
                ):
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "未命名节点").strip()

                    if node_id:
                        # Don't add compartment children to the main node list
                        if node.get("type") == "ListCompartmentChild":
                            continue
                        node_id_to_name[node_id] = node_name
                        logger.info(f"  🟢 节点: [green]{node_name}[/green]")

                        # --- 1a. Extract value properties inside this node ---
                        # Find the compartment for value properties
                        value_props_compartment = node.find(
                            "./nodes[@type='value_properties']",
                            namespaces=self.namespaces,
                        )
                        if value_props_compartment is not None:
                            for prop in value_props_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                prop_name = prop.get("name", "未命名属性").strip()
                                logger.info(f"    🔸 属性: [cyan]{prop_name}[/cyan]")

                # --- 2. Extract and resolve connections within this diagram ---
                found_connections = False
                for conn in bdd_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        conn_xmi_type = conn.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        if conn_xmi_type:
                            # Use the explicit xmi:type, e.g., "trufun:TGeneralizeConnection"
                            type_name = conn_xmi_type.split(":")[
                                -1
                            ]  # Becomes "TGeneralizeConnection"
                            conn_type = type_name.replace("T", "").replace(
                                "Connection", ""
                            )  # Becomes "Generalize"
                        else:
                            # Fallback for safety
                            conn_type = self._strip_ns(conn.tag)

                        logger.info(
                            f"  🔗 关系 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_usecase_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取用例图。[/bold yellow]"
            )
            return

        logger.info("\n👤 [bold cyan]开始提取用例图及其参与者和用例关系[/bold cyan]")

        # 遍历所有元素以查找用例图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 xmi:type 属性找到用例图元素
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TUsecaseDiagram"
            ):
                usecase_diagram_elem = elem
                diagram_name = usecase_diagram_elem.get("name", "未命名用例图")
                logger.info(f"\n🎭 分析用例图: [bold]{diagram_name}[/bold]")

                # --- 1. 提取所有用例节点和参与者节点 ---
                node_id_to_name = {}
                # 遍历图中的所有节点
                for node in usecase_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "未命名").strip()

                    if node_id:
                        if node_xmi_type == "trufun:TUseCaseNode":
                            # 这是一个用例节点
                            node_id_to_name[node_id] = node_name
                            logger.info(f"  ➡️ 用例: [green]{node_name}[/green]")
                        elif (
                            node_xmi_type == "trufun:TModelElementNode"
                            and node.get("stereotype") == "<<block>>"
                        ):
                            # 根据提供的XML，参与者被建模为带有 <<block>> 构造型的 ModelElementNode
                            node_id_to_name[node_id] = node_name
                            logger.info(
                                f"  🧍 参与者 (Block): [magenta]{node_name}[/magenta]"
                            )
                        # 可以根据需要添加其他类型的节点，例如注释或超链接，但通常不将其添加到连接映射中。

                # --- 2. 提取并解析连接关系 ---
                found_connections = False
                for conn in usecase_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        conn_xmi_type = conn.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        conn_type = "Unknown"
                        if conn_xmi_type:
                            type_name = conn_xmi_type.split(":")[
                                -1
                            ]  # 例如 "TAssociationConnection"
                            # 特别处理用例图中常见的关联类型
                            if type_name == "TAssociationConnection":
                                conn_type = "Association"
                            else:
                                # Fallback to general cleaning if other types appear
                                conn_type = type_name.replace("T", "").replace(
                                    "Connection", ""
                                )
                        else:
                            # Fallback for safety
                            conn_type = self._strip_ns(conn.tag)

                        logger.info(
                            f"  🔗 关系 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_activity_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取活动图。[/bold yellow]"
            )
            return

        logger.info("\n🏃 [bold yellow]开始提取活动图及其活动流[/bold yellow]")

        # 遍历所有元素以查找活动图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 xmi:type 属性找到活动图元素
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TActivityDiagram"
            ):
                activity_diagram_elem = elem
                diagram_name = activity_diagram_elem.get("name", "未命名活动图")
                logger.info(f"\n📊 分析活动图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}

                # Pass 1: Populate node_id_to_name map for all potential source/target IDs
                for node in activity_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "").strip()

                    if node_id:
                        display_name = node_name
                        if node_xmi_type == "trufun:TInitialNode":
                            display_name = "起始节点"
                        elif node_xmi_type == "trufun:TActivityFinalNode":
                            display_name = "活动终点"
                        elif node_xmi_type == "trufun:TDecisionNode":
                            display_name = "决策节点"
                        elif node_xmi_type == "trufun:TActionNode":
                            pass  # Use node_name directly
                        elif node_xmi_type == "trufun:TInputPinNode":
                            display_name = (
                                f"输入引脚: {node_name.replace(':', '').strip()}"
                                if node_name
                                else "输入引脚"
                            )
                        elif node_xmi_type == "trufun:TOutputPinNode":
                            display_name = (
                                f"输出引脚: {node_name.replace(':', '').strip()}"
                                if node_name
                                else "输出引脚"
                            )
                        elif node_xmi_type == "trufun:TCommentNode":
                            display_name = f"注释: {node_name}"
                        elif node_xmi_type == "trufun:TCallBehaviorAction":
                            display_name = f"调用行为: {node_name}"
                        elif (
                            node_xmi_type == "trufun:TSubjectNode"
                        ):  # Activity Partition
                            display_name = f"泳道: {node_name}"
                        elif (
                            node_xmi_type == "trufun:TActivityNode"
                        ):  # Main Activity Node
                            display_name = f"顶层活动: {node_name}"
                        elif node_xmi_type == "trufun:SubLabel":
                            continue  # Skip sublabels
                        else:
                            display_name = f"未知节点 ({self._strip_ns(node_xmi_type)}): {node_name if node_name else 'ID ' + node_id}"

                        node_id_to_name[node_id] = display_name

                # Pass 2: Log nodes in a more structured way, and extract internal behaviors
                main_activity_node = activity_diagram_elem.find(
                    f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TActivityNode']",
                    namespaces=self.namespaces,
                )
                if main_activity_node is not None:
                    main_activity_id = main_activity_node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}id"
                    )
                    logger.info(
                        f"  📦 [bold green]{node_id_to_name.get(main_activity_id, '未知顶层活动')}[/bold green]"
                    )

                    for partition in main_activity_node.findall(
                        f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TSubjectNode']",
                        namespaces=self.namespaces,
                    ):
                        partition_id = partition.get(
                            f"{{{self.namespaces.get('xmi', '')}}}id"
                        )
                        logger.info(
                            f"    ➡️ [bold blue]{node_id_to_name.get(partition_id, '未知泳道')}[/bold blue]"
                        )

                        for sub_node in partition.findall(
                            "./nodes", namespaces=self.namespaces
                        ):
                            sub_node_xmi_type = sub_node.get(
                                f"{{{self.namespaces.get('xmi', '')}}}type"
                            )
                            sub_node_id = sub_node.get(
                                f"{{{self.namespaces.get('xmi', '')}}}id"
                            )
                            if sub_node_xmi_type == "trufun:SubLabel":
                                continue

                            sub_display_name = node_id_to_name.get(sub_node_id, "未知")
                            if (
                                "PinNode" not in sub_node_xmi_type
                                and "CommentNode" not in sub_node_xmi_type
                            ):
                                logger.info(f"      🟢 {sub_display_name}")
                            elif "PinNode" in sub_node_xmi_type:
                                logger.info(f"        🔸 {sub_display_name}")
                            elif (
                                "CommentNode" in sub_node_xmi_type
                                and sub_node.get("type") == "HyperLink"
                            ):
                                logger.info(
                                    f"      🔗 [underline blue]{sub_display_name}[/underline blue] (目标: {sub_node.get('extendData', '未知')})"
                                )

                # 4. 提取并解析连接关系 (控制流和对象流)
                found_connections = False
                for conn in activity_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        conn_xmi_type = conn.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        conn_type = "Unknown Flow"
                        stereotype_attr = conn.get("stereotype")  # 例如 <<rate>>

                        if stereotype_attr:
                            conn_type = stereotype_attr.strip("<>")  # 优先使用构造型
                        elif conn_xmi_type:
                            type_name = conn_xmi_type.split(":")[-1]
                            if type_name == "TControlFlowConnection":
                                conn_type = "Control Flow"
                            elif type_name == "TObjectFlowConnection":
                                conn_type = "Object Flow"
                            else:
                                conn_type = type_name.replace("T", "").replace(
                                    "Connection", ""
                                )  # 通用清理

                        # 检查是否有守卫条件 (guard condition)
                        guard_condition = ""
                        for sublabel in conn.findall(
                            "./subLabels", namespaces=self.namespaces
                        ):
                            if sublabel.get("alias") == "Guard":
                                guard_condition = (
                                    f" [{sublabel.get('name', '').strip()}]"
                                )
                                break  # 假设每个流只有一个守卫条件

                        # 检查是否有构造型（如果没有在stereotype属性中，可能在subLabels中）
                        # 确保不重复添加已从stereotype属性获取的构造型
                        if not stereotype_attr:
                            for sublabel in conn.findall(
                                "./subLabels", namespaces=self.namespaces
                            ):
                                if (
                                    sublabel.get("alias") == "Stereotype"
                                    and sublabel.get("name") not in conn_type
                                ):
                                    conn_type += f" {sublabel.get('name', '').strip().strip('<>')}"

                        logger.info(
                            f"    🔗 关系 ([blue]{conn_type}{guard_condition}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_class_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取类图。[/bold yellow]"
            )
            return

        logger.info("\n📚 [bold yellow]开始提取类图及其结构和关系[/bold yellow]")

        # 遍历所有元素以查找类图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 xmi:type 属性找到类图元素
            # 假设类图的 xmi:type 是 trufun:TClassDiagram
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TClassDiagram"
            ):
                class_diagram_elem = elem
                diagram_name = class_diagram_elem.get("name", "未命名类图")
                logger.info(f"\n🧩 分析类图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}
                # --- MODIFIED: Broaden node identification criteria ---
                for node in class_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get(
                        "name", ""
                    ).strip()  # Use empty string for initial check

                    # Identify nodes that represent entities in the diagram
                    # This now includes TClassNode, TModelElementNode (for blocks/requirements), etc.
                    if node_id and (
                        node_xmi_type == "trufun:TClassNode"
                        or node_xmi_type
                        == "trufun:TModelElementNode"  # Capture all TModelElementNodes
                        or node_xmi_type
                        == "trufun:TCommentNode"  # Capture Comment Nodes like HyperLink
                    ):
                        # For TModelElementNode, the 'name' attribute directly holds the entity name.
                        # For TCommentNode, it also has a 'name' attribute.
                        if node_name:  # Ensure name is not empty
                            node_id_to_name[node_id] = node_name
                            # Log only if it's a primary entity type
                            if node_xmi_type in [
                                "trufun:TClassNode",
                                "trufun:TModelElementNode",
                            ]:
                                logger.info(
                                    f"  🔷 实体: [green]{node_name}[/green] (类型: {self._strip_ns(node_xmi_type)}, Stereotype: {node.get('stereotype', '无')})"
                                )
                            elif node_xmi_type == "trufun:TCommentNode":
                                logger.info(
                                    f"  📝 注释/链接: [green]{node_name}[/green] (类型: {self._strip_ns(node_xmi_type)})"
                                )
                        else:
                            continue

                        part_properties_compartment = node.find(
                            "./nodes[@type='part_properties']",
                            namespaces=self.namespaces,
                        )
                        if part_properties_compartment is not None:
                            for part_prop in part_properties_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                part_name = part_prop.get("name", "未命名部件").strip()
                                logger.info(f"    - 部件属性: [cyan]{part_name}[/cyan]")

                        constraint_properties_compartment = node.find(
                            "./nodes[@type='constraint_properties']",
                            namespaces=self.namespaces,
                        )
                        if constraint_properties_compartment is not None:
                            for (
                                constraint_prop
                            ) in constraint_properties_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                constraint_name = constraint_prop.get(
                                    "name", "未命名约束"
                                ).strip()
                                logger.info(
                                    f"    - 约束属性: [cyan]{constraint_name}[/cyan]"
                                )

                        # Original attribute/operation extraction (might be less relevant for your SysML-like XML)
                        attrs_compartment = node.find(
                            "./nodes[@type='attributes']", namespaces=self.namespaces
                        )
                        if attrs_compartment is not None:
                            for prop in attrs_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                prop_name = prop.get("name", "未命名属性").strip()
                                logger.info(f"    - 属性: [cyan]{prop_name}[/cyan]")

                        ops_compartment = node.find(
                            "./nodes[@type='operations']", namespaces=self.namespaces
                        )
                        if ops_compartment is not None:
                            for op in ops_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']",
                                namespaces=self.namespaces,
                            ):
                                op_name = op.get("name", "未命名操作").strip()
                                logger.info(f"    - 操作: [purple]{op_name}[/purple]")

                # --- 2. 提取并解析连接关系 ---
                found_connections = False
                for conn in class_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        conn_xmi_type = conn.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        conn_type = "Unknown Relationship"
                        stereotype_attr = conn.get("stereotype")

                        if stereotype_attr:
                            conn_type = stereotype_attr.strip("<>")
                        elif conn_xmi_type:
                            type_name = conn_xmi_type.split(":")[-1]
                            # 常见类图连接类型
                            if type_name == "TAssociationConnection":
                                conn_type = "Association"
                            elif type_name == "TGeneralizeConnection":
                                conn_type = "Generalization"
                            elif type_name == "TRealizeConnection":  # Realization
                                conn_type = "Realization"
                            elif type_name == "TDependencyConnection":  # Dependency
                                conn_type = "Dependency"
                            else:
                                conn_type = type_name.replace("T", "").replace(
                                    "Connection", ""
                                )

                        logger.info(
                            f"  🔗 关系 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type, target_name))

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_state_machine_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取状态机图。[/bold yellow]"
            )
            return

        logger.info("\n⚙️ [bold blue]开始提取状态机图及其状态转换[/bold blue]")

        # 遍历所有元素以查找状态机图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 xmi:type 和 stereotype 属性找到状态机图元素
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TStateMachineDiagram"
                and elem.get("stereotype") == "SysMLStateDiagram"
            ):
                state_machine_diagram_elem = elem
                diagram_name = state_machine_diagram_elem.get("name", "未命名状态机图")
                logger.info(f"\n🌀 分析状态机图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}

                # Pass 1: Populate node_id_to_name map for all potential source/target IDs
                # This helps in resolving connections even if nodes are deeply nested.
                for node in state_machine_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get(
                        "name", ""
                    ).strip()  # Name might be empty for choice nodes

                    if node_id:
                        display_name = node_name
                        if node_xmi_type == "trufun:TStateMachineNode":
                            display_name = (
                                f"状态机: {node_name if node_name else '未命名'}"
                            )
                        elif node_xmi_type == "trufun:TRegionNode":
                            display_name = (
                                f"区域: {node_name if node_name else '未命名'}"
                            )
                        elif node_xmi_type == "trufun:TInitialStateNode":
                            display_name = "初始状态"
                        elif node_xmi_type == "trufun:TFinalStateNode":
                            display_name = "最终状态"  # Not in provided XML, but common
                        elif node_xmi_type == "trufun:TCompositeStateNode":
                            display_name = (
                                f"状态: {node_name if node_name else '未命名'}"
                            )
                        elif node_xmi_type == "trufun:TChoiceStateNode":
                            display_name = "选择伪状态"
                        elif (
                            node_xmi_type == "trufun:TJoinStateNode"
                        ):  # Not in provided XML
                            display_name = "连接伪状态"
                        elif (
                            node_xmi_type == "trufun:TForkStateNode"
                        ):  # Not in provided XML
                            display_name = "分叉伪状态"
                        elif (
                            node_xmi_type == "trufun:TEntryPointNode"
                        ):  # Not in provided XML
                            display_name = "入口点伪状态"
                        elif (
                            node_xmi_type == "trufun:TExitPointNode"
                        ):  # Not in provided XML
                            display_name = "出口点伪状态"
                        elif (
                            node_xmi_type == "trufun:TCommentNode"
                            and node.get("type") == "HyperLink"
                        ):
                            display_name = f"超链接: {node_name}"
                        elif node_xmi_type == "trufun:SubLabel":
                            continue  # Skip sub-labels for the main map
                        else:
                            display_name = f"未知节点 ({self._strip_ns(node_xmi_type)}): {node_name if node_name else 'ID ' + node_id}"

                        node_id_to_name[node_id] = display_name

                # Pass 2: Log nodes in a more structured way, and extract internal behaviors
                # Find the main state machine node (should be only one per diagram)
                main_state_machine_node = state_machine_diagram_elem.find(
                    f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TStateMachineNode']",
                    namespaces=self.namespaces,
                )

                if main_state_machine_node is not None:
                    main_sm_id = main_state_machine_node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}id"
                    )
                    logger.info(
                        f"  ⚙️ [bold green]{node_id_to_name.get(main_sm_id, '未知状态机')}[/bold green]"
                    )

                    # Recursively process regions and states
                    def process_region_content(parent_node, indent_level=0):
                        indent = "  " * indent_level
                        for node in parent_node.findall(
                            "./nodes", namespaces=self.namespaces
                        ):  # Direct children within the region/composite state
                            node_xmi_type = node.get(
                                f"{{{self.namespaces.get('xmi', '')}}}type"
                            )
                            node_id = node.get(
                                f"{{{self.namespaces.get('xmi', '')}}}id"
                            )

                            if node_xmi_type == "trufun:SubLabel":
                                continue  # Skip display labels

                            display_name = node_id_to_name.get(
                                node_id, f"未知 ({node_id})"
                            )

                            if node_xmi_type == "trufun:TRegionNode":
                                logger.info(f"{indent}  📦 {display_name}")
                                process_region_content(
                                    node, indent_level + 1
                                )  # Recurse into sub-region
                            elif node_xmi_type == "trufun:TCompositeStateNode":
                                logger.info(f"{indent}  🟡 {display_name}")
                                # Check for internal activities (Entry, Exit, Do)
                                internet_compartment = node.find(
                                    "./internetPartCompartment",
                                    namespaces=self.namespaces,
                                )
                                if internet_compartment is not None:
                                    for internal_part in internet_compartment.findall(
                                        "./internelParts", namespaces=self.namespaces
                                    ):
                                        activity_name = internal_part.get(
                                            "name", "未命名活动"
                                        ).strip()
                                        is_do_activity = (
                                            internal_part.get("isDo") == "true"
                                        )
                                        behavior_type = (
                                            "Do" if is_do_activity else "Internal"
                                        )
                                        logger.info(
                                            f"{indent}    🔹 {behavior_type} Activity: [cyan]{activity_name}[/cyan]"
                                        )
                                # Check for nested regions within composite state
                                for sub_region in node.findall(
                                    f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TRegionNode']",
                                    namespaces=self.namespaces,
                                ):
                                    sub_region_id = sub_region.get(
                                        f"{{{self.namespaces.get('xmi', '')}}}id"
                                    )
                                    logger.info(
                                        f"{indent}  {indent}📦 {node_id_to_name.get(sub_region_id, '未知区域')}"
                                    )
                                    process_region_content(
                                        sub_region, indent_level + 2
                                    )  # Recurse into nested region
                            elif node_xmi_type == "trufun:TInitialStateNode":
                                logger.info(f"{indent}  ➡️ {display_name}")
                            elif node_xmi_type == "trufun:TChoiceStateNode":
                                logger.info(f"{indent}  ❓ {display_name}")
                            elif (
                                node_xmi_type == "trufun:TCommentNode"
                                and node.get("type") == "HyperLink"
                            ):
                                logger.info(
                                    f"{indent}  🔗 [underline blue]{display_name}[/underline blue] (目标: {node.get('extendData', '未知')})"
                                )
                            else:  # Other simple states or pseudostates
                                logger.info(f"{indent}  ⚪ {display_name}")

                    # Start processing from the region(s) directly under the main state machine node
                    for region_node in main_state_machine_node.findall(
                        f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TRegionNode']",
                        namespaces=self.namespaces,
                    ):
                        process_region_content(
                            region_node, 1
                        )  # Start with indent level 1 for main region's content

                # 3. Extract and resolve transitions (connections)
                found_transitions = False
                for conn in state_machine_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_transitions = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        _ = conn.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                        transition_type = (
                            "Transition"  # Default for TTransitionConnection
                        )

                        # Transition label (Event[Guard]/Effect)
                        transition_label = conn.get("name", "").strip()
                        # Often, the 'name' attribute contains the guard/event
                        # But also check subLabels for 'Guard' or 'Name' alias for robustness
                        for sublabel in conn.findall(
                            "./subLabels", namespaces=self.namespaces
                        ):
                            if sublabel.get("alias") in ["Name", "Guard"]:
                                sublabel_text = sublabel.get("name", "").strip()
                                if (
                                    sublabel_text and sublabel_text != transition_label
                                ):  # Avoid duplicating if already in 'name'
                                    if transition_label:
                                        transition_label += f" ({sublabel_text})"
                                    else:
                                        transition_label = sublabel_text

                        logger.info(
                            f"    🔗 {transition_type}: [bold green]{source_name}[/bold green] --({transition_label})--> [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, transition_type, target_name))

                if not found_transitions:
                    logger.info("    ⚠️  未发现任何转换关系。")

    def extract_sequence_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取序列图。[/bold yellow]"
            )
            return

        logger.info("\n➡️ [bold cyan]开始提取序列图及其交互和消息[/bold cyan]")

        # 遍历所有元素以查找序列图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 xmi:type 和 stereotype 属性找到序列图元素
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TSequenceDiagram"
                and elem.get("stereotype") == "SysMLSequenceDiagram"
            ):
                seq_diagram_elem = elem
                diagram_name = seq_diagram_elem.get("name", "未命名序列图")
                logger.info(f"\n💬 分析序列图: [bold]{diagram_name}[/bold]")

                # 查找序列图中的主要交互节点
                interaction_node = seq_diagram_elem.find(
                    f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TInteractionNode']",
                    namespaces=self.namespaces,
                )

                # --- 关键修改：只有找到 interaction_node 才继续处理 ---
                if interaction_node is None:
                    logger.warning(
                        f"  ⚠️  在序列图 '[bold]{diagram_name}[/bold]' 中未找到主要交互节点，跳过此图。"
                    )
                    continue  # 如果没有找到交互节点，则跳过当前序列图，继续下一个

                logger.info(
                    f"  ↔️ 交互: [bold green]{interaction_node.get('name', '未命名交互')}[/bold green]"
                )

                # --- Pass 1: Collect all relevant nodes and their associations ---
                # This map will store the display name for any node with an xmi:id
                diagram_node_map = {}
                # This map traces TEventOccurrenceNode IDs back to their parent lifeline ID
                event_occurrence_to_lifeline_id_map = {}

                # Recursive helper to traverse the nested nodes in sequence diagram
                def collect_seq_nodes_recursive(parent_elem, current_lifeline_id=None):
                    # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                    for node in parent_elem.findall(
                        "./nodes", namespaces=self.namespaces
                    ):
                        node_xmi_type = node.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                        node_name = node.get("name", "").strip()

                        if node_id:
                            display_name = node_name  # Default
                            effective_lifeline_id = (
                                current_lifeline_id  # Inherit context
                            )

                            if node_xmi_type == "trufun:TLifelineNode_SD":
                                effective_lifeline_id = (
                                    node_id  # This node *is* a lifeline
                                )
                                if not node_name and node.get("owner"):
                                    owner_name = self._model_elements_by_id.get(
                                        node.get("owner")
                                    )
                                    if (
                                        owner_name and "类型" not in owner_name
                                    ):  # Avoid using generic type names as actual names
                                        display_name = f":{owner_name}"
                                    else:
                                        display_name = (
                                            f"未命名生命线 ({node.get('owner')})"
                                        )
                                elif not node_name:
                                    display_name = f"未命名生命线 ({node_id})"

                                diagram_node_map[node_id] = display_name
                                # Recurse into children of lifeline (activations, etc.)
                                collect_seq_nodes_recursive(node, effective_lifeline_id)

                            elif node_xmi_type in [
                                "trufun:TInvocationSpecificationNode",
                                "trufun:TExecutionSpecificationNode",
                            ]:
                                display_name = (
                                    f"激活 ({node_id})" if not node_name else node_name
                                )  # Activations are usually unnamed
                                diagram_node_map[node_id] = display_name
                                # Recurse into activations (for event occurrences)
                                collect_seq_nodes_recursive(node, effective_lifeline_id)

                            elif node_xmi_type == "trufun:TEventOccurrenceNode":
                                # Event occurrences are message endpoints, link them to their lifeline
                                display_name = f"事件 ({node_id})"  # Usually unnamed
                                diagram_node_map[node_id] = display_name
                                if effective_lifeline_id:
                                    event_occurrence_to_lifeline_id_map[node_id] = (
                                        effective_lifeline_id
                                    )

                            elif node_xmi_type == "trufun:TStateInvariantNode":
                                display_name = f"状态不变量 ({node_name if node_name else node_id})"
                                diagram_node_map[node_id] = display_name

                            elif (
                                node_xmi_type == "trufun:TInteractionOccurrenceNode"
                            ):  # Interaction Use (ref)
                                display_name = (
                                    f"交互使用 ({node_name if node_name else node_id})"
                                )
                                diagram_node_map[node_id] = display_name

                            elif node_xmi_type == "trufun:TCombinedFragmentNode":
                                # Combined Fragments can have a 'kind' attribute (e.g., 'opt', 'alt')
                                kind = (
                                    node.get("kind", "未知类型").upper()
                                )  # "kind" is not in this XML, but common in UML
                                display_name = f"组合片段 ({kind}): {node_name if node_name else ''}".strip(
                                    ": "
                                )
                                diagram_node_map[node_id] = display_name
                                collect_seq_nodes_recursive(
                                    node, effective_lifeline_id
                                )  # Recurse into operands

                            elif node_xmi_type == "trufun:TInteractionOperandNode":
                                display_name = (
                                    f"操作数 ({node_name if node_name else node_id})"
                                )
                                diagram_node_map[node_id] = display_name
                                # Operands can contain messages or other elements, recurse
                                collect_seq_nodes_recursive(node, effective_lifeline_id)

                            elif node_xmi_type == "trufun:TMountingLinkNode":
                                # These are visual links, not logical elements to map for names
                                continue
                            elif node_xmi_type == "trufun:TSplitterNode":
                                # These are visual dividers, not logical elements
                                continue
                            elif node_xmi_type == "trufun:SubLabel":
                                # These are display labels, handled separately for connections/elements
                                continue
                            else:
                                # Fallback for any other unhandled node types, ensuring they are mapped
                                display_name = f"其他节点 ({self._strip_ns(node_xmi_type)}): {node_name if node_name else 'ID ' + node_id}"
                                diagram_node_map[node_id] = display_name

                # Start collection from the main interaction node
                collect_seq_nodes_recursive(
                    interaction_node
                )  # 现在这个调用被保护在 if interaction_node is not None 之后

                # --- Pass 2: Log nodes and messages in structured order ---

                # Log lifelines first
                logger.info("  --- 生命线 ---")
                # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                lifeline_nodes_sorted = sorted(
                    interaction_node.findall(
                        f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TLifelineNode_SD']",
                        namespaces=self.namespaces,
                    ),
                    key=lambda x: int(x.get("location", "0,0").split(",")[0]),
                    # Sort by X coordinate for consistent output
                )
                for lifeline_node in lifeline_nodes_sorted:
                    lifeline_id = lifeline_node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}id"
                    )
                    logger.info(
                        f"    --| [green]{diagram_node_map.get(lifeline_id, '未知生命线')}[/green]"
                    )
                    # Optionally, log sub-elements of lifeline here if desired for full detail
                    # For example, activations, state invariants could be logged here
                    # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                    for sub_node in lifeline_node.findall(
                        "./nodes", namespaces=self.namespaces
                    ):
                        sub_node_xmi_type = sub_node.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        sub_node_id = sub_node.get(
                            f"{{{self.namespaces.get('xmi', '')}}}id"
                        )
                        if sub_node_xmi_type in [
                            "trufun:TInvocationSpecificationNode",
                            "trufun:TExecutionSpecificationNode",
                        ]:
                            logger.info(
                                f"      ▪️ {diagram_node_map.get(sub_node_id, '未知激活')}"
                            )
                        elif sub_node_xmi_type == "trufun:TStateInvariantNode":
                            logger.info(
                                f"      💡 {diagram_node_map.get(sub_node_id, '未知状态不变量')}"
                            )
                        # Add other lifeline sub-nodes here

                # Log top-level Interaction uses and Combined Fragments
                logger.info("  --- 交互使用/组合片段 ---")
                # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                for top_level_node in interaction_node.findall(
                    "./nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = top_level_node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = top_level_node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}id"
                    )
                    if node_xmi_type == "trufun:TInteractionOccurrenceNode":
                        logger.info(
                            f"    ▶️ {diagram_node_map.get(node_id, '未知交互使用')}"
                        )
                    elif node_xmi_type == "trufun:TCombinedFragmentNode":
                        logger.info(
                            f"    🔀 {diagram_node_map.get(node_id, '未知组合片段')}"
                        )
                        # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                        for operand_node in top_level_node.findall(
                            f"./nodes[@{{{self.namespaces.get('xmi', '')}}}type='trufun:TInteractionOperandNode']",
                            namespaces=self.namespaces,
                        ):
                            operand_id = operand_node.get(
                                f"{{{self.namespaces.get('xmi', '')}}}id"
                            )
                            logger.info(
                                f"      ▪️ 操作数: {diagram_node_map.get(operand_id, '未知操作数')}"
                            )

                # 3. 提取消息 (Messages - Connections)
                logger.info("  --- 消息 ---")
                found_messages = False
                # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                for msg_conn in seq_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    conn_xmi_type = msg_conn.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    if conn_xmi_type == "trufun:TMessageConnection_SD":
                        found_messages = True
                        source_event_id = msg_conn.get("source")
                        target_event_id = msg_conn.get("target")
                        message_name = msg_conn.get("name", "Unnamed Message").strip()

                        # Resolve lifeline IDs from event occurrences
                        source_lifeline_id = event_occurrence_to_lifeline_id_map.get(
                            source_event_id
                        )
                        target_lifeline_id = event_occurrence_to_lifeline_id_map.get(
                            target_event_id
                        )

                        source_name = diagram_node_map.get(
                            source_lifeline_id, f"未知生命线 (事件: {source_event_id})"
                        )
                        target_name = diagram_node_map.get(
                            target_lifeline_id, f"未知生命线 (事件: {target_event_id})"
                        )

                        # Collect additional details from subLabels if alias is "Name" and different, or other relevant aliases
                        # --- 修复：将 ElementTree.findall 调用的 namespaces 参数传递过去 ---
                        message_label_details = []
                        for sublabel in msg_conn.findall(
                            "./subLabels", namespaces=self.namespaces
                        ):
                            if (
                                sublabel.get("alias") == "Name"
                                and sublabel.get("name").strip() != message_name
                            ):
                                message_label_details.append(
                                    sublabel.get("name").strip()
                                )
                            # You can add more specific aliases here if they appear in your XML
                            # e.g., if you have sublabels for arguments, stereotypes, etc.
                            # elif sublabel.get("alias') == "Arguments":
                            #     message_label_details.append(f"Args: {sublabel.get('name').strip()}")
                            # elif sublabel.get("alias') == "Stereotype":
                            #     message_label_details.append(f"Stereo: {sublabel.get('name').strip()}")

                        full_message_label = message_name
                        if message_label_details:
                            full_message_label += (
                                f" ({', '.join(message_label_details)})"
                            )

                        logger.info(
                            f"    -> 消息: [bold green]{source_name}[/bold green] --[blue]{full_message_label}[/blue]--> [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append(
                            (source_name, full_message_label, target_name)
                        )

                if not found_messages:
                    logger.info("    ⚠️  未发现任何消息。")

    # ----------------------------------------------------------------------
    # --- 新增的包图提取方法 ---
    # ----------------------------------------------------------------------
    def extract_package_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取包图。[/bold yellow]"
            )
            return

        logger.info("\n📦 [bold cyan]开始提取包图及其包和导入关系[/bold cyan]")

        # 遍历所有元素以查找包图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 根据 stereotype 属性找到包图元素
            # 注意：XML中xmi:type可能是TClassDiagram，但stereotype是SysMlPackageDiagram
            if tag == "contents" and elem.get("stereotype") == "SysMlPackageDiagram":
                package_diagram_elem = elem
                diagram_name = package_diagram_elem.get("name", "未命名包图")
                logger.info(f"\n📁 分析包图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}

                # 1. 提取所有包节点
                # 包节点类型为 trufun:TPackageNode
                for node in package_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "").strip()

                    if node_id and node_xmi_type == "trufun:TPackageNode":
                        node_id_to_name[node_id] = node_name
                        logger.info(f"  📂 包: [green]{node_name}[/green]")
                    # 可以在这里添加对其他类型节点（如注释）的识别，如果它们是直接的图节点

                # 2. 提取并解析连接关系 (导入关系)
                found_connections = False
                for conn in package_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    if source_id and target_id:
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知包 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知包 (ID: {target_id})"
                        )

                        conn_xmi_type = conn.get(
                            f"{{{self.namespaces.get('xmi', '')}}}type"
                        )
                        conn_type_specific = conn.get(
                            "type"
                        )  # 例如 ElementImport, PackageImport

                        relationship_label = "Unknown Relationship"

                        if (
                            conn_xmi_type == "trufun:TRealizationConnection"
                            and conn_type_specific
                        ):
                            if conn_type_specific == "ElementImport":
                                relationship_label = "元素导入"
                            elif conn_type_specific == "PackageImport":
                                relationship_label = "包导入"
                            else:
                                relationship_label = conn_type_specific  # Fallback for other realization types
                        else:
                            # Fallback if xmi:type is different or type attribute is missing
                            relationship_label = (
                                self._strip_ns(conn_xmi_type)
                                .replace("trufun:", "")
                                .replace("Connection", "")
                            )

                        # 检查 subLabels 中是否有构造型信息 (例如 <<import>>)
                        stereotype_label = ""
                        for sublabel in conn.findall(
                            "./subLabels", namespaces=self.namespaces
                        ):
                            if (
                                sublabel.get("alias") == "FixedName"
                            ):  # The XML uses FixedName for <<import>>
                                stereotype_text = sublabel.get("name", "").strip()
                                if stereotype_text:
                                    stereotype_label = f" ({stereotype_text})"
                                break  # Assume one fixed name stereotype per connection

                        logger.info(
                            f"  🔗 关系 ([blue]{relationship_label}{stereotype_label}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append(
                            (
                                source_name,
                                f"{relationship_label}{stereotype_label}",
                                target_name,
                            )
                        )

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    # ----------------------------------------------------------------------
    # --- 修正后的参数图提取方法 ---
    # ----------------------------------------------------------------------
    def extract_parametric_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取参数图。[/bold yellow]"
            )
            return

        logger.info(
            "\n📐 [bold magenta]开始提取参数图及其约束和绑定关系[/bold magenta]"
        )

        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 查找参数图元素：根据提供的XML，stereotype是"SysmlParameterDiagram"
            # 并且 xmi:type 是 "trufun:TCompositeStructureDiagram"
            if (
                tag == "contents"
                and elem.get("stereotype")
                == "SysmlParameterDiagram"  # 修正：单数 "Parameter"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TCompositeStructureDiagram"
            ):  # 增加 xmi:type 确认
                param_diagram_elem = elem
                diagram_name = param_diagram_elem.get("name", "未命名参数图")
                logger.info(f"\n📈 分析参数图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}

                # 1. 遍历图中的所有节点，构建ID到名称的映射
                # 这次遍历的目的是先收集所有节点ID及其可显示名称，以便后续连接解析时查找
                for node in param_diagram_elem.findall(
                    ".//nodes", namespaces=self.namespaces
                ):
                    node_xmi_type = node.get(
                        f"{{{self.namespaces.get('xmi', '')}}}type"
                    )
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "").strip()
                    node_type = node.get(
                        "type"
                    )  # SysML.IBD.ConstraintProperty, SysML.IBD.ValueProperty, SysML.IBD.PartProperty

                    if node_id:
                        display_name = node_name
                        if (
                            node_xmi_type == "trufun:TStructureClassNode"
                            and node.get("stereotype") == "<<block>>"
                        ):
                            display_name = f"上下文块: {node_name}"
                            node_id_to_name[node_id] = display_name
                            logger.info(f"  📦 {display_name}")  # 打印主约束块

                        elif node_type == "SysML.IBD.ConstraintProperty":
                            # 约束属性的图节点，其name属性通常包含有用的信息，例如 "约束 : 总重量约束"
                            # 如果name为空，可以尝试通过modelElement引用
                            referenced_name = None
                            if node.get("modelElement"):
                                referenced_name = self._model_elements_by_id.get(
                                    node.get("modelElement")
                                )

                            if node_name:
                                display_name = f"约束属性实例: {node_name}"
                            elif (
                                referenced_name and "类型" not in referenced_name
                            ):  # 避免使用泛型类型作为名称
                                display_name = f"约束属性实例: {referenced_name}"
                            else:
                                display_name = f"约束属性实例 (ID: {node_id})"

                            node_id_to_name[node_id] = display_name
                            logger.info(f"  ➡️ {display_name}")  # 打印约束属性实例

                        elif node_type == "SysML.IBD.ValueProperty":
                            # 值属性的图节点
                            display_name = f"值属性: {node_name}"
                            node_id_to_name[node_id] = display_name
                            logger.info(f"  📊 {display_name}")  # 打印值属性

                        elif (
                            node_type == "SysML.IBD.PartProperty"
                        ):  # 新增：识别部件属性
                            display_name = f"部件属性: {node_name.lstrip(': ').strip()}"
                            node_id_to_name[node_id] = display_name
                            logger.info(f"  🧩 {display_name}")  # 打印部件属性

                            # 遍历部件属性内部的节点，特别是值属性
                            for inner_node in node.findall(
                                "./nodes", namespaces=self.namespaces
                            ):
                                inner_node_type = inner_node.get("type")
                                _ = inner_node.get(
                                    f"{{{self.namespaces.get('xmi', '')}}}type"
                                )
                                inner_node_id = inner_node.get(
                                    f"{{{self.namespaces.get('xmi', '')}}}id"
                                )
                                inner_node_name = inner_node.get("name", "").strip()

                                if (
                                    inner_node_id
                                    and inner_node_type == "SysML.IBD.ValueProperty"
                                ):
                                    inner_display_name = (
                                        f"内部值属性: {inner_node_name}"
                                    )
                                    node_id_to_name[inner_node_id] = (
                                        inner_display_name  # 确保内部节点也被映射
                                    )
                                    logger.info(
                                        f"    - {inner_display_name}"
                                    )  # 打印内部值属性

                        elif (
                            node_xmi_type == "trufun:TPortNode"
                            and node.get("stereotype") == "<<constraintParameter>>"
                        ):  # 参数通常表现为端口
                            # 参数的名称通常在 name 属性中，例如 "p1 : Real"
                            # 或者在 SubLabel 中有更规范的名称
                            parameter_name_from_sublabel = None
                            for sublabel in node.findall(
                                "./subLabels", namespaces=self.namespaces
                            ):
                                if (
                                    sublabel.get("alias") == "Name"
                                ):  # Trufun有时会将完整参数名放在这里
                                    parameter_name_from_sublabel = sublabel.get(
                                        "name"
                                    ).strip()
                                    break

                            if parameter_name_from_sublabel:
                                display_name = f"参数: {parameter_name_from_sublabel}"
                            elif node_name:
                                # 清理掉可能的类型信息，例如 "p1 : Real" 变成 "p1"
                                display_name = (
                                    f"参数: {node_name.split(':')[0].strip()}"
                                )
                            else:
                                display_name = f"参数 (ID: {node_id})"

                            # 尝试获取其所属的图上父节点（Constraint Property或Value Property）的名称
                            parent_node_id = node.get(
                                "parentNode"
                            )  # parentNode 指向图上包含它的节点
                            parent_name = node_id_to_name.get(
                                parent_node_id
                            )  # 优先从已解析的图节点中获取
                            if (
                                not parent_name
                            ):  # 如果图节点映射中没有，尝试从全局模型元素映射中获取
                                # 这里的owner通常是模型元素而非图元素，用于更通用的查找
                                owner_id_in_model = node.get("owner")
                                parent_name = self._model_elements_by_id.get(
                                    owner_id_in_model, "未知所有者"
                                )

                            node_id_to_name[node_id] = display_name
                            # 打印参数，并指出其所属
                            logger.info(
                                f"    🔸 {display_name} (所属图节点: {parent_name})"
                            )

                        elif node_xmi_type == "trufun:SubLabel":
                            continue  # SubLabels are just for display, not primary nodes we map here
                        else:
                            # 捕获其他未处理的节点类型，以防遗漏
                            if node_name:
                                display_name = f"其他节点 ({self._strip_ns(node_xmi_type)}): {node_name}"
                            else:
                                display_name = f"其他节点 ({self._strip_ns(node_xmi_type)}): ID {node_id}"
                            node_id_to_name[node_id] = (
                                display_name  # 仍然加入map，以防被连接引用
                            )

                # 2. 提取并解析连接关系 (Binding Connectors)
                found_connections = False
                for conn in param_diagram_elem.findall(
                    "./connections", namespaces=self.namespaces
                ):
                    source_id = conn.get("source")
                    target_id = conn.get("target")

                    # 检查连接是否是绑定连接器：通过 palette_entry_id 属性精确识别
                    binding_connector_detail = conn.find(
                        "./eAnnotations/details[@key='palette_entry_id']",
                        namespaces=self.namespaces,
                    )

                    if (
                        source_id
                        and target_id
                        and binding_connector_detail is not None
                        and binding_connector_detail.get("value")
                        == "SysML.IBD.BindingConnector"
                    ):
                        found_connections = True
                        source_name = node_id_to_name.get(
                            source_id, f"未知节点 (ID: {source_id})"
                        )
                        target_name = node_id_to_name.get(
                            target_id, f"未知节点 (ID: {target_id})"
                        )

                        # 绑定连接器通常会有 <<equal>> 构造型，可以从 stereotype 属性中获取
                        conn_stereotype = conn.get("stereotype", "").strip("<>")
                        if conn_stereotype:
                            conn_type_label = f"Binding ({conn_stereotype})"
                        else:
                            conn_type_label = "Binding"

                        logger.info(
                            f"  🔗 绑定连接器 ([blue]{conn_type_label}[/blue]): [bold green]{source_name}[/bold green] ↔️ [bold blue]{target_name}[/bold blue]"
                        )
                        # Store the triple for later use
                        self.triples.append((source_name, conn_type_label, target_name))
                    # 你可能也想捕获其他类型的连接，如果它们出现在参数图中
                    # else:
                    #     conn_xmi_type = conn.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                    #     conn_type = self._strip_ns(conn_xmi_type).replace("trufun:", "").replace("Connection", "")
                    #     source_name = node_id_to_name.get(source_id, f"未知({source_id})")
                    #     target_name = node_id_to_name.get(target_id, f"未知({target_id})")
                    #     logger.info(f"  🔗 其他连接 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]")

                if not found_connections:
                    logger.info("  ⚠️  未发现任何绑定连接关系。")

    # ----------------------------------------------------------------------
    # --- 新增的表格视图提取方法 ---
    # ----------------------------------------------------------------------
    def extract_tables(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取表格信息。[/bold yellow]"
            )
            return

        logger.info("\n📊 [bold purple]开始提取模型中的表格视图[/bold purple]")

        found_tables = False
        # 遍历所有元素以查找表格视图
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # 查找 xmi:type 为 "trufun:TTable" 的 "contents" 元素
            if (
                tag == "contents"
                and elem.get(f"{{{self.namespaces.get('xmi', '')}}}type")
                == "trufun:TTable"
            ):
                found_tables = True
                table_elem = elem
                table_name = table_elem.get("name", "未命名表格")
                table_xmi_id = table_elem.get(f"{{{self.namespaces.get('xmi', '')}}}id")

                logger.info(
                    f"\n📑 发现表格: [bold]{table_name}[/bold] (ID: {table_xmi_id})"
                )

                # 提取并解析表格的元数据属性
                owner_id = table_elem.get("owner")
                row_scopes_id = table_elem.get("rowScopes")
                table_define_id = table_elem.get("tableDefineID")
                editor_id = table_elem.get("editorID")
                image_path = table_elem.get("image")

                # 解析所有者和行范围的名称
                owner_name = (
                    self._model_elements_by_id.get(
                        owner_id, f"未知所有者 (ID: {owner_id})"
                    )
                    if owner_id
                    else "N/A"
                )
                row_scopes_name = (
                    self._model_elements_by_id.get(
                        row_scopes_id, f"未知范围 (ID: {row_scopes_id})"
                    )
                    if row_scopes_id
                    else "N/A"
                )

                logger.info("  🔸 类型: [cyan]trufun:TTable[/cyan]")
                logger.info(f"  🔸 所属: [cyan]{owner_name}[/cyan]")
                logger.info(f"  🔸 行范围: [cyan]{row_scopes_name}[/cyan]")
                logger.info(
                    f"  🔸 表格定义ID: [cyan]{table_define_id if table_define_id else 'N/A'}[/cyan]"
                )
                logger.info(
                    f"  🔸 编辑器ID: [cyan]{editor_id if editor_id else 'N/A'}[/cyan]"
                )
                logger.info(
                    f"  🔸 图标路径: [cyan]{image_path if image_path else 'N/A'}[/cyan]"
                )
                logger.info(
                    f"  🔸 显示为框架: [cyan]{table_elem.get('showAsFrame', 'N/A')}[/cyan]"
                )
                logger.info(f"  🔸 缩放: [cyan]{table_elem.get('zoom', 'N/A')}[/cyan]")
                logger.info(
                    f"  🔸 网格间距: [cyan]{table_elem.get('gridSpacing', 'N/A')}[/cyan]"
                )

                # 注意: 此处未解析表格的具体内容（行、列、单元格数据），
                # 因为给定的XML片段中不包含这些结构。通常，表格的实际数据
                # 会在XML中有更复杂的嵌套结构，例如 <columns> 和 <rows> 元素。
                logger.info(
                    "  ℹ️  [yellow]当前解析仅包含表格元数据，不包含具体行/列数据。[/yellow]"
                )

        if not found_tables:
            logger.info("  ⚠️  未发现任何表格视图。")

    # 参考这个
    #     {
    #         "head": {
    #             "label": "ModelingMethod",
    #             "id": "mm-001",
    #             "properties": {
    #                 "name": "SysML",
    #                 "description": "系统建模语言，用于对更广泛的系统进行建模",
    #             },
    #         },
    #         "relation": {"type": "EXTENDS", "properties": {}},
    #         "tail": {
    #             "label": "ModelingMethod",
    #             "id": "mm-002",
    #             "properties": {"name": "UML", "description": "统一建模语言"},
    #         },
    #     },
    # 参考上面的导入格式，保存到json
    # name字段才是名字
    def triples_to_graph_json(self, label: str = "tmx"):
        graph = {"triples": []}
        for triple in self.triples:
            head, relation, tail = triple
            # id 使用name的hash,这样可以统一相同名称的节点
            graph["triples"].append(
                {
                    "head": {
                        "label": label,
                        "id": str(hash(head)),
                        "properties": {"name": head},
                    },
                    "relation": {"type": relation, "properties": {}},
                    "tail": {
                        "label": label,
                        "id": str(hash(tail)),
                        "properties": {"name": tail},
                    },
                }
            )
        return graph

    def parse_all(self):
        self.extract_requirement_diagrams()
        self.extract_internal_block_diagrams()
        self.extract_block_diagrams()
        self.extract_usecase_diagrams()
        self.extract_activity_diagrams()
        self.extract_class_diagrams()
        self.extract_state_machine_diagrams()
        self.extract_package_diagrams()
        self.extract_parametric_diagrams()
        self.extract_tables()


if __name__ == "__main__":
    # 请确保这里的路径是正确的
    file_path = "data/trufun.tmx"  # 假设这个文件包含了参数图信息
    content = Path(file_path).read_text(encoding="utf-8")
    parser = SysMLParser(content)

    if parser.root is not None:
        parser.parse_all()

    graph = parser.triples_to_graph_json()
    logger.info("📊 [bold green]已提取图数据结构（JSON格式）[/bold green]\n")
    with open("data/trufun.json", "w") as f:
        json.dump(graph, f, ensure_ascii=False, indent=4)
