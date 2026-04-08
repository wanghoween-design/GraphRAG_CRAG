# GraphRAG-CRAG: 基于知识图谱的矫正检索增强生成系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0-green.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个结合**知识图谱**与**向量检索**的智能问答系统，采用 **CRAG (Corrective RAG)** 架构实现检索质量的自动评估与矫正。

## 项目亮点

- **双路检索架构**: 同时利用 Neo4j 知识图谱和 FAISS 向量库进行信息检索
- **CRAG 闭环流程**: 基于 LangGraph 实现 Retrieve-Grade-Recover 自动矫正机制
- **智能查询改写**: 当检索结果不足时，自动改写查询并重新检索
- **多轮对话记忆**: 支持上下文理解与指代消解
- **联网搜索兜底**: 本地知识库穷尽后自动调用 Tavily 联网搜索

## 系统架构
<img width="854" height="539" alt="项目流程图" src="https://github.com/user-attachments/assets/9ae3437b-6a5b-4818-a1a8-8b05b84dea35" />


## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 图数据库 | Neo4j | 存储人物关系、地点等结构化知识 |
| 向量数据库 | FAISS | 存储文档的向量表示，支持相似度检索 |
| LLM 框架 | LangChain + LangGraph | 构建可编排的 LLM 应用 |
| 本地 LLM | Ollama (Qwen3:4b) | 支持本地部署的大语言模型 |
| Embedding | nomic-embed-text | 文本向量化模型 |
| Reranker | BAAI/bge-reranker-v2-m3 | 检索结果重排序模型 |
| 联网搜索 | Tavily API | 实时网络搜索服务 |

## 项目结构

```
GraphRAG_CRAG/
├── config.py                 # 配置文件（环境变量、模型名称等）
├── main.py                   # 程序入口
├── models/
│   ├── __init__.py
│   └── state.py              # LangGraph 状态定义、Pydantic 模型
├── services/
│   ├── __init__.py
│   ├── vector_store.py       # FAISS 向量库服务
│   ├── graph_service.py      # Neo4j 图数据库服务
│   ├── reranker.py           # FlagReranker 重排序服务
│   └── retriever.py          # 检索服务（向量+图谱双路召回）
├── nodes/
│   ├── __init__.py
│   ├── grader_node.py        # 检索质量评估节点
│   ├── rewrite_node.py       # 查询改写节点
│   ├── generate_node.py      # 答案生成节点
│   ├── web_search_node.py    # 联网搜索节点
│   ├── memory_node.py        # 对话记忆节点
│   └── router.py             # 条件路由（状态转移判断）
├── graph/
│   ├── __init__.py
│   └── crag_graph.py         # CRAG 图构建
├── requirements.txt          # 依赖清单
├── .env.example              # 环境变量模板
├── .gitignore
└── README.md
```

## 快速开始

### 1. 环境准备

#### 1.1 安装 Neo4j

```bash
# Docker 方式（推荐）
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest

# 或下载桌面版: https://neo4j.com/download/
```

#### 1.2 安装 Ollama 并下载模型

```bash
# 安装 Ollama
# macOS/Linux: curl -fsSL https://ollama.com/install.sh | sh
# Windows: https://ollama.com/download

# 下载所需模型
ollama pull qwen3:4b              # LLM 模型
ollama pull nomic-embed-text      # Embedding 模型
```

### 2. 克隆项目

```bash
git clone https://github.com/your-username/GraphRAG-CRAG.git
cd GraphRAG-CRAG
```

### 3. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件，填入你的配置
```

`.env` 文件内容：

```env
# Neo4j 配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# Tavily API（联网搜索）
TAVILY_API_KEY=your_tavily_api_key
```

> **获取 Tavily API Key**: 访问 https://tavily.com 注册并获取免费 API Key

### 5. 准备数据

#### 5.1 向量数据库

将你的 FAISS 向量库放置到 `data/vector_store/qyn_faiss/` 目录下。

#### 5.2 知识图谱

确保 Neo4j 中已导入相关知识图谱数据，并在 `data/graph/entity.json` 中维护实体列表。

### 6. 运行

```bash
cd GraphRAG_CRAG
python main.py
```

## 核心模块说明

### 1. 双路召回 (Dual Retrieval)

```python
# 同时进行向量检索和图谱检索
def merge_retrievers(question: str, graph_service: GraphQueryService):
    # 向量检索：从 FAISS 召回相关文档
    text_results = retrieve_text_context(question, k=8)
    
    # 图谱检索：从 Neo4j 查询实体关系
    graph_results = graph_service.query_graph_context(person_name)
    
    # 统一格式返回
    return all_contexts
```

### 2. Rerank 精排

使用 `BAAI/bge-reranker-v2-m3` 对召回结果进行相关性重排序：

```python
ranked = rerank_context(
    question=question,
    contexts=contexts,
    top_k=5,        # 返回前5个最相关文档
    threshold=0.3   # 过滤相关性低于0.3的结果
)
```

### 3. Grader 质量评估

使用 LLM 对检索结果进行结构化评估：

```python
class GraderOutput(BaseModel):
    is_sufficient: bool      # 检索结果是否足够
    confidence_score: float  # 置信度分数 (0-1)
    missing_info: str        # 缺失的信息
    reasoning: str           # 评估理由
```

### 4. CRAG 闭环流程

```
检索 → 评估 → 充足? → 生成答案
              ↓ 否
         改写查询 → 重新检索 (最多2轮)
              ↓ 仍不足
         联网搜索 → 生成答案
```

## API 参考

### GraphQueryService

```python
from services import GraphQueryService

service = GraphQueryService(uri, username, password)

# 查询人物关系
results = service.query_graph_context("范闲")
# 返回: ["范闲的母亲是叶轻眉", "保护范闲的是五竹", ...]

service.close()
```

### 检索函数

```python
from services import retrieve_and_rerank

# 完整检索流程：双路召回 + Rerank
ranked = retrieve_and_rerank(question, graph_service)
```

### CRAG Graph

```python
from graph import build_crag_graph

graph = build_crag_graph()
result = graph.invoke(
    {"question": "范闲的母亲是谁?"},
    config={"configurable": {"thread_id": "session_1"}}
)
print(result["final_answer"])
```

## 性能优化建议

1. **Reranker 懒加载**: 首次调用时才加载模型，避免启动慢
2. **批量检索**: 向量检索设置 `k=8`，经 Rerank 后取 Top-5
3. **迭代限制**: 本地检索最多2轮，避免无限循环
4. **温度参数**: Grader 使用 `temperature=0.0` 保证评估稳定性

## 常见问题

### Q: Reranker 模型下载慢？

```bash
# 使用镜像站
export HF_ENDPOINT=https://hf-mirror.com
```

### Q: Ollama 连接失败？

```bash
# 确保 Ollama 服务已启动
ollama serve

# 检查模型是否已下载
ollama list
```

### Q: Neo4j 连接超时？

检查防火墙设置，确保 7687 端口开放：
```bash
# 测试连接
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password')); d.verify_connectivity()"
```

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

## 致谢

- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 状态图编排
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) - Reranker 模型
- [Tavily](https://tavily.com/) - AI 搜索 API

---

**Star 本项目以支持开发!**
