import logging
import xml.etree.ElementTree as ET

from rich.logging import RichHandler

# --- 日志记录器设置 ---
logger = logging.getLogger("SysMLParser")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, markup=True)],
)


class SysMLParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.root = None
        self.namespaces = {}
        self.elements_by_id = {}
        self.stereotype_applications = {}
        self.found_requirements_ids = set()

        self.load_xml()

        if self.root is not None:
            self.build_id_map()
            self._build_stereotype_map()

    def load_xml(self):
        try:
            # 解析命名空间（关键修复）
            self.namespaces = {
                prefix if prefix else "default": uri
                for _, (prefix, uri) in ET.iterparse(
                    self.file_path, events=["start-ns"]
                )
            }

            # 使用 ElementTree 加载并解析 XML 内容
            tree = ET.parse(self.file_path)
            self.root = tree.getroot()

            logger.info(
                f"✅ 成功加载 XML 文件: [bold green]{self.file_path}[/bold green]，"
                f"检测到命名空间: [cyan]{list(self.namespaces.keys())}[/cyan]"
            )

        except (FileNotFoundError, ET.ParseError) as e:
            logger.error(f"❌ [bold red]加载失败[/bold red]: 无法解析 XML 文件 - {e}")
            self.root = None

    def _strip_ns(self, tag):
        # 用于 strip namespace {…} 前缀
        return tag.split("}")[-1] if "}" in tag else tag

    def build_id_map(self):
        self.elements_by_id = {
            elem.get(f"{{{self.namespaces.get('xmi', '')}}}id"): elem
            for elem in self.root.findall(".//*[@xmi:id]", self.namespaces)
        }
        logger.info("🗺️  [bold]XMI ID 映射构建完成[/bold]")

    def _build_stereotype_map(self):
        """
        [关键优化] 构造型映射逻辑优化，使其更通用，不再依赖于标签中的':'。
        它现在查找任何带有 'base_*' 属性的元素，这对于识别构造型应用更可靠。
        """
        logger.info("🛠️  [bold]开始构建构造型映射[/bold]...")
        for elem in self.root.findall(".//*"):
            base_element_id = None
            # 查找任何以 'base_' 开头的属性
            for attr_name, attr_value in elem.attrib.items():
                if attr_name.startswith("base_"):
                    base_element_id = attr_value
                    # 提取构造型名称（标签名本身）并转为小写，以便不区分大小写比较
                    stereotype_type = elem.tag.split("}")[-1].lower()
                    self.stereotype_applications[base_element_id] = stereotype_type
                    break  # 找到一个 'base_' 属性就足够了
        logger.info(
            f"✅ 构造型映射完成，共发现 [green]{len(self.stereotype_applications)}[/green] 个应用"
        )

    def get_element_by_id(self, xmi_id):
        return self.elements_by_id.get(xmi_id)

    def get_element_details(self, xmi_id):
        element = self.get_element_by_id(xmi_id)
        if element is not None:
            name = element.get("name", "N/A")
            xmi_type = element.get(f"{{{self.namespaces.get('xmi', '')}}}type", "N/A")
            return {"element": element, "name": name, "type": xmi_type}
        return None

    def extract_requirement_diagrams(self):
        if self.root is None:
            logger.warning("XML根元素未加载，无法提取需求图。")
            return

        logger.info("📜 [bold yellow]开始提取需求图及其结构关系[/bold yellow]")

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
                    ".//nodes[@stereotype='<<requirement>>']"
                ):
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    req_name = node.get("name", "未命名需求").strip()

                    if node_id:
                        node_id_to_name[node_id] = req_name
                        logger.info(
                            f"  🔹 发现需求节点: [bold green]{req_name}[/bold green]"
                        )

                        props_compartment = node.find(
                            "./nodes[@type='stereotype_properties']"
                        )
                        if props_compartment is not None:
                            for prop in props_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']"
                            ):
                                prop_name = prop.get("name", "未命名属性").strip()
                                clean_prop_name = prop_name.split(":")[0].strip()
                                logger.info(
                                    f"    🔸 属性: [cyan]{clean_prop_name}[/cyan]"
                                )

                # --- 2. Extract and resolve connections (relationships) ---
                found_connections = False
                for conn in req_diagram_elem.findall("./connections"):
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

                if not found_connections:
                    logger.info("  -> No connections found in this diagram.")

    def extract_internal_block_diagrams(self):
        if self.root is None:
            logger.warning(
                "⚠️  [bold yellow]未加载 XML 根元素，无法提取内部块图。[/bold yellow]"
            )
            return

        logger.info("🧩 [bold magenta]开始提取内部块图及其连接关系[/bold magenta]")

        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            if (
                tag == "contents"
                and elem.get("stereotype") == "SysmlInternalBlockDiagram"
            ):
                diagram_name = elem.get("name", "未命名内部块图")
                logger.info(f"\n📊 分析内部块图: [bold]{diagram_name}[/bold]")

                node_id_to_name = {}
                for node in elem.findall(".//nodes[@name]"):
                    node_id = node.get(f"{{{self.namespaces.get('xmi', '')}}}id")
                    node_name = node.get("name", "未命名节点").strip()
                    if node_name.startswith(":"):
                        node_name = node_name[1:].strip()
                    if node_id:
                        node_id_to_name[node_id] = node_name
                        logger.info(f"  🟢 节点: [green]{node_name}[/green]")

                found_connections = False
                for conn in elem.findall("./connections"):
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
                            # Use the explicit xmi:type, e.g., "trufun:TConnector"
                            type_name = conn_xmi_type.split(":")[
                                -1
                            ]  # Becomes "TConnector"
                            conn_type = type_name.replace("T", "").replace(
                                "Connection", ""
                            )  # Becomes "Connector"
                        else:
                            # Fallback for safety
                            conn_type = self._strip_ns(conn.tag)

                        logger.info(
                            f"  🔗 连接 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )

                if not found_connections:
                    logger.info("  ⚠️  未发现任何连接关系。")

    def extract_block_diagrams(self):
        if self.root is None:
            logger.warning("XML根元素未加载，无法提取块图。")
            return

        logger.info("📘 [bold blue]提取块图及其结构关系[/bold blue]")

        # Iterate through all elements to find Block Diagrams
        for elem in self.root.iter():
            tag = self._strip_ns(elem.tag)

            # Find the diagram element
            if tag == "contents" and elem.get("stereotype") == "SysmlBlockDiagram":
                bdd_elem = elem
                diagram_name = bdd_elem.get("name", "未命名块图")
                logger.info(f"\nAnalyzing Diagram: [bold]{diagram_name}[/bold]")

                # --- 1. Extract all nodes (Blocks, ValueTypes, etc.) in this diagram ---
                node_id_to_name = {}
                for node in bdd_elem.findall(".//nodes[@name]"):
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
                            "./nodes[@type='value_properties']"
                        )
                        if value_props_compartment is not None:
                            # Find all properties listed inside
                            for prop in value_props_compartment.findall(
                                "./nodes[@type='ListCompartmentChild']"
                            ):
                                prop_name = prop.get("name", "未命名属性").strip()
                                logger.info(f"    🔸 属性: [cyan]{prop_name}[/cyan]")

                # --- 2. Extract and resolve connections within this diagram ---
                found_connections = False
                for conn in bdd_elem.findall("./connections"):
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
                            f"  🔗 连接 ([blue]{conn_type}[/blue]): [bold green]{source_name}[/bold green] → [bold blue]{target_name}[/bold blue]"
                        )

                if not found_connections:
                    logger.info("  -> No connections found in this diagram.")


if __name__ == "__main__":
    # 请确保这里的路径是正确的
    file_path = "./trufun.tmx"

    parser = SysMLParser(file_path)

    if parser.root is not None:
        parser.extract_requirement_diagrams()
        parser.extract_internal_block_diagrams()
        parser.extract_block_diagrams()
