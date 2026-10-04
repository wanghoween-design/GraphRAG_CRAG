import json
import os
from typing import Dict, List

from .vector_store import load_vector_store
from .graph_service import GraphQueryService
from .reranker import rerank_context

# 项目根目录下的原著名册索引 (人物名录, 供图谱检索做实体匹配)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NAME_INDEX_PATH = os.path.join(_PROJECT_ROOT, "data", "graph", "name_index.json")

_FALLBACK_PERSONS = ["范闲", "庆帝", "叶轻眉", "五竹", "陈萍萍", "范建"]
_person_names_cache: List[Dict] = None


def _load_character_names() -> List[Dict]:
    """从 name_index.json 加载全部人物名录 (绝对路径, 只加载一次)。"""
    global _person_names_cache
    if _person_names_cache is not None:
        return _person_names_cache
    try:
        with open(_NAME_INDEX_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f).get("entries", [])
        _person_names_cache = [
            {"name": e["name"], "type": e.get("type", "Character")}
            for e in entries if e.get("name")
        ]
    except Exception as e:
        print(f"[Retriever] name_index 加载失败, 使用内置人物表: {e}")
        _person_names_cache = [{"name": n, "type": "Character"} for n in _FALLBACK_PERSONS]
    return _person_names_cache


def retrieve_text_context(query: str, k: int = 8) -> List[Dict]:
    """通过向量相似度进行检索, 返回带卷章元数据的结构化上下文"""
    db = load_vector_store()
    docs = db.similarity_search(query, k=k)

    results = []
    for doc in docs:
        meta = doc.metadata or {}
        results.append({
            "content": (
                f"【卷名】{meta.get('volume', '')}"
                f"【章节】{meta.get('chapter_title', '')}"
                f"【内容】{doc.page_content}"
            ),
            "source": "vector_db",
            "retriever_type": "vector",
            "volume": meta.get("volume", ""),
            "chapter_title": meta.get("chapter_title", ""),
            "chapter_index": meta.get("chapter_index"),
        })
    return results

def retrieve_graph_context(person_name: str, graph_service: GraphQueryService):
    graph_results = graph_service.query_graph_context(person_name)
    return [{"source":"graph", "content": item} for item in graph_results]

def merge_retrievers(question: str, graph_service: GraphQueryService):
    """
    整合向量检索和图谱检索，统一格式，准备送入 Rerank

    输出格式统一为: [{"content": "...", "source": "...", "retriever_type": "vector|graph"}, ...]
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
            all_contexts.append(r)
        print(f"召回 {len(text_results)} 条")

    except Exception as e:
        print(f"失败: {e}")

    # ---------- 2. 图谱检索 ----------
    print(">> 图谱检索 (Neo4j)...", end=" ")
    entities = _load_character_names()
    found_persons = [e["name"] for e in entities if e["name"] in question]

    if found_persons:
        recalled = 0
        for person_name in found_persons:
            try:
                graph_results = graph_service.query_graph_context(person_name)
            except Exception as e:
                print(f"\n   [警告] 图谱查询失败({person_name}): {e}")
                continue
            for r in graph_results:
                all_contexts.append({
                    "content": r,
                    "source": f"neo4j:{person_name}",
                    "retriever_type": "graph"
                })
                recalled += 1
        print(f"命中 {len(found_persons)} 个人物 {found_persons}, 召回 {recalled} 条")
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
