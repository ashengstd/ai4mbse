import logging
import xml.etree.ElementTree as ET

from rich.logging import RichHandler

logger = logging.getLogger("TMXController")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False)],
)


class TMXController:
    def __init__(self, file_path):
        self.file_path = file_path
        self.root = None
        self.namespaces = {}
        self.dependencies = []
        self.load_xml()

    def load_xml(self):
        """加载并解析XML文件"""
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                xml_content = file.read()
            self.root = ET.fromstring(xml_content)
            logger.info("XML解析成功")
            logger.info(f"根元素标签: {self.root.tag}")
        except FileNotFoundError:
            logger.info(f"未找到文件: {self.file_path}，请检查文件路径是否正确。")
        except ET.ParseError as e:
            logger.info(f"XML 解析出错: {e}，请检查 XML 文件的格式是否正确。")

        # 提取命名空间
        self.namespaces = dict(
            [node for _, node in ET.iterparse(self.file_path, events=["start-ns"])]
        )
        logger.info(f"命名空间: {self.namespaces}")

    def extract_dependencies(self):
        """提取uml:Dependency类型的packagedElement"""
        if self.root is None:
            logger.info("XML内容为空，请检查是否成功加载XML文件。")
            return []

        for elem in self.root.findall(".//packagedElement"):
            if elem.get(f"{{{self.namespaces['xmi']}}}type") == "uml:Dependency":
                client = elem.get("client")
                supplier = elem.get("supplier")
                if client and supplier:
                    self.dependencies.append((client, supplier))

        return self.dependencies

    def find_type_and_name(self, xmi_id):
        """根据xmi_id查找类型和名称"""
        if self.root is None:
            logger.info("XML内容未加载，请先调用load_xml()方法。")
            return None, None

        for elem in self.root.findall(".//packagedElement"):
            if elem.get(f"{{{self.namespaces['xmi']}}}id") == xmi_id:
                xmi_type = elem.get(f"{{{self.namespaces['xmi']}}}type")
                name = elem.get("name")
                return xmi_type, name
        return None, None

    # 遍历依赖关系并打印
    def traverse_dependencies(self):
        """遍历依赖关系"""
        if not self.dependencies:
            logger.info("没有依赖关系可供遍历，请先调用extract_dependencies()方法。")
            return

        for client, supplier in self.dependencies:
            client_type, client_name = self.find_type_and_name(client)
            supplier_type, supplier_name = self.find_type_and_name(supplier)

            if client_type and client_name and supplier_type and supplier_name:
                logger.info(
                    f"{client_name} ({client_type}) 依赖于 {supplier_name} ({supplier_type})"
                )
            else:
                logger.info(f"未能找到 {client} 或 {supplier} 的详细信息")
        return self.dependencies

    def traverse_classes(self):
        """遍历所有类并打印"""
        if self.root is None:
            logger.info("XML内容未加载，请先调用load_xml()方法。")
            return

        for elem in self.root.findall(".//packagedElement", self.namespaces):
            if elem.get(f"{{{self.namespaces['xmi']}}}type") == "uml:Class":
                xmi_id = elem.get(f"{{{self.namespaces['xmi']}}}id")
                name = elem.get("name")
                xmi_type = elem.get(f"{{{self.namespaces['xmi']}}}type")
                logger.info(f"id: {xmi_id} 名称: {name} 类型: {xmi_type}")
                return


if __name__ == "__main__":
    # 示例用法
    tmx_controller = TMXController("./data/trufun.xml")
    tmx_controller.extract_dependencies()
    tmx_controller.traverse_dependencies()
    tmx_controller.traverse_classes()
