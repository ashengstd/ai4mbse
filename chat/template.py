entity_prompt_template = (
    "请从以下问题中**只**提取所有实体，用**逗号**分隔，只输出实体列表，不要解释，不要加上任何其他内容。"
    "例如：'比尔·盖茨, 苹果公司, 马斯克, 飞机'。\n问题：{question}"
)

triple_prompt_template = (
    "你正在处理一份技术文档，任务是从文本中提取与“建模”密切相关的结构化知识。请特别关注以下类型的信息：\n"
    "\n"
    "有效实体类型（label）包括：\n"
    "- Requirement：建模需求（如功能、性能、接口等要求）\n"
    "- ModelingMethod：建模方法（如 UML、SysML、BPMN 等）\n"
    "- ModelElement：建模中的元素（如类、状态、组件、接口等）\n"
    "- View：模型视图（如结构视图、行为视图、用例视图）\n"
    "- Constraint：建模相关约束（如系统约束、性能限制等）\n"
    "- Actor：交互者或用户角色\n"
    "- UseCase：系统的用例场景\n"
    "- Tool：建模工具（如 MagicDraw、Enterprise Architect）\n"
    "- Standard：建模相关标准（如 ISO/IEC 42010）\n"
    "- GlossaryTerm：专业术语或概念词条\n"
    "\n"
    "请忽略以下内容：\n"
    "- 人物介绍（如作者、研究者）\n"
    "- 书籍、出版、课程背景等无关描述\n"
    "- 与建模无关的通识知识\n"
    "\n"
    "以下是四个相邻段落：\n"
    "段落一：\n"
    "{p1}\n"
    "\n"
    "段落二：\n"
    "{p2}\n"
    "\n"
    "段落三：\n"
    "{p3}\n"
    "\n"
    "段落四：\n"
    "{p4}\n"
    "\n"
    "请你完成以下任务：\n"
    "1. 抽取上述段落中与建模相关的实体及其属性。\n"
    "2. 若这些实体间存在关系，请构建包含“实体-关系-实体”的三元组。\n"
    "3. 生成结果 JSON 格式如下（如果没有符合的三元组，则输出空列表）：\n"
    "3. 生成结果 JSON 格式如下（如果没有符合的三元组，则输出空列表）：\n"
    "\n"
    "{{\n"
    '  "triples": [\n'
    "    {{\n"
    '      "head": {{\n'
    '        "label": "ModelElement",\n'
    '        "id": "me-001",\n'
    '        "properties": {{\n'
    '          "name": "组件A",\n'
    '          "description": "系统中负责处理信号的部分"\n'
    "        }}\n"
    "      }},\n"
    '      "relation": {{\n'
    '        "type": "PART_OF",\n'
    '        "properties": {{}}\n'
    "      }},\n"
    '      "tail": {{\n'
    '        "label": "ModelElement",\n'
    '        "id": "me-002",\n'
    '        "properties": {{\n'
    '          "name": "系统B"\n'
    "        }}\n"
    "      }}\n"
    "    }},\n"
    "    ...\n"
    "  ]\n"
    "}}\n"
    "请注意：\n"
    "- label 字段仅允许使用上述定义的10种类型。\n"
    "- relation.type 可以是 BELONGS_TO、PART_OF、USED_BY、DEFINED_BY、CONSTRAINED_BY、INTERACTS_WITH 等合理关系。\n"
    "- 请严格输出 JSON 格式，不要添加任何解释。\n"
    "- 所有文本均使用中文，字段名请保留英文。\n"
)
