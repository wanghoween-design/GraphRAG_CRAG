import json
from typing import Dict, List

from .vector_store import load_vector_store
from .graph_service import GraphQueryService
from .reranker import rerank_context

def retrieve_text_context(query: str, k: int = 5):
    """通过向量相似度进行检索"""
    db = load_vector_store()
    docs = db.similarity_search(query, k=k)

    results = []

    for doc in docs:
        results.append(
            f"【卷名】{doc.metadata.get('volume')}"
            f"【章节】{doc.metadata.get('chapter_title')}"
            f"【内容】{doc.page_content[:]}"
        )
    return results

def retrieve_graph_context(person_name: str, graph_service: GraphQueryService):
    graph_results = graph_service.query_graph_context(person_name)
    return [{"source":"graph", "content": item} for item in graph_results]

def merge_retrievers(question: str, graph_service: GraphQueryService):
    """
    整合向量检索和图谱检索，统一格式，准备送入 Rerank

    输出格式统一为: [{"content": "...", "source": "...", "type": "vector|graph"}, ...]
    """
    print(f"\n{'='*60}")
    print(f"【问题】{question}")
    print(f"{'='*60}")

    all_contexts = []

    # ---------- 1. 向量检索 ----------
    print("\n>> 向量检索 (FAISS)...", end=" ")
    try:
        text_results = retrieve_text_context(question, k=8)
        for r in text_results:
            all_contexts.append({
                "content":r,
                "source": "vector_db",
                "retriever_type": "vector"
            })
        print(f"召回 {len(text_results)} 条")

    except Exception as e:
        print(f"失败: {e}")

    # ---------- 2. 图谱检索 ----------
    print(">> 图谱检索 (Neo4j)...", end=" ")
    # 从 question 中提取人物名（简单匹配，后续可换 NER）
    # 从 entity.json 加载所有人物名
    try:
        with open("./data/graph/entity.json", "r", encoding="utf-8") as f:
            eneities = json.load(f)
        person_names = [e for e in eneities if e["type"]=="Character"]
    except:
        person_names = ["范闲", "庆帝", "叶轻眉", "五竹", "陈萍萍", "范建"]

    found_persons = [name for name in person_names if name in question]
    if found_persons:
        for person_name in found_persons:
            graph_results = graph_service.query_graph_context(person_name)
            for r in graph_results:
                all_contexts.append({
                    "content": r,
                    "source": f"neo4j:{person_name}",
                    "retriever_type": "graph"
                })
        print(f"召回 {len(found_persons)} 个人物: {found_persons}")
    else:
        print("未检测到人物名")

    print(f"\n【总计召回】{len(all_contexts)} 条")
    return all_contexts

def retrieve_and_rerank(question: str, graph_service: GraphQueryService) -> List[Dict]:
    """
    完整流程：双路召回 → Rerank 精排 → 返回 Top-K

    对应简历："利用 Neo4j 搭建知识图谱，结合 FAISS 实现双路召回"
    """
    # 1. 召回
    contexts = merge_retrievers(question, graph_service)

    if not contexts:
        print("警告: 未召回任何文档")
        return []

    # 2. Rerank 精排
    print("\n>> FlagReranker 精排...")
    ranked = rerank_context(
        question=question,
        contexts=contexts,
        top_k=5,           # 简历中的 Top-K 筛选
        threshold=0.3      # 置信度阈值，过滤低质量
    )

    print(f"\n【精排结果】保留 {len(ranked)} 条 (阈值=0.3, Top-5):")
    for i, ctx in enumerate(ranked, 1):
        source_short = ctx.get('source', 'unknown')
        print(f"  {i}. [score={ctx['score']:.3f}],[{ctx['retriever_type']}] ,{source_short}.")
        # 内容预览（前 50 字）
        preview = ctx['content'].replace('\n', ' ')
        print(f"      {preview}...")

    return ranked
