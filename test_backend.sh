#!/bin/bash

# API 服务器地址
BASE_URL="http://127.0.0.1:8000"

echo "🚀 开始测试 Triple Graph Web API..."
echo "======================================="

# 检查 API 是否在线
echo "1. 测试 GET / (检查服务是否在线)"
curl -s -X GET "$BASE_URL/"
echo -e "\n---------------------------------------\n"

# 测试提取三元组
echo "2. 测试 POST /extract_triples (从文本提取三元组)"
echo "上传文件: data/test_requirements.txt"
curl -s -X POST "$BASE_URL/extract_triples" \
     -F "file=@data/test_requirements.txt"
echo -e "\n---------------------------------------\n"

# 测试导入三元组
echo "3. 测试 POST /import_triples (导入三元组 JSON)"
echo "上传文件: data/test_triples.json"
curl -s -X POST "$BASE_URL/import_triples" \
     -F "file=@data/test_triples.json"
echo -e "\n---------------------------------------\n"

# 测试解析 TMX 文件
echo "4. 测试 POST /parse_tmx (解析 TMX 文件)"
echo "上传文件: data/trufun.tmx"
curl -s -X POST "$BASE_URL/parse_tmx" \
     -F "file=@data/trufun.tmx"
echo -e "\n---------------------------------------\n"

# 测试查询
echo "5. 测试 POST /query (查询)"
echo "发送问题: '用户如何登录？'"
curl -s -X POST "$BASE_URL/query" \
     -H "Content-Type: application/json" \
     -d '{"question": "用户如何登录？"}'
echo -e "\n\n======================================="
echo "✅ 测试完成"
