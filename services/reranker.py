from typing import Dict, List, Optional

from FlagEmbedding import FlagReranker

from config import RERANK_MODEL_NAME

_reranker: Optional[FlagReranker]=None

def get_reranker(model_name: str = RERANK_MODEL_NAME)->FlagReranker:
    """懒加载单例，避免重复加载模型"""
    global _reranker
    if _reranker is None:
        print(f"[Reranker]Loading model{model_name}..")
        _reranker = FlagReranker(model_name, use_fp16=True)
        print(f"[Reranker]Loaded successfully")
    return _reranker

def rerank_context(
        question: str,
        contexts: List[Dict],
        top_k: Optional[int]=None,
        threshold: float = 0.0
)->List[Dict]:
    """
    对候选文档进行重排序，返回按相关性降序排列的结果

    Args:
        question: 用户查询问题
        contexts: 候选文档列表，每个元素必须包含 "content" 字段
        top_k: 只返回前K个最相关的文档，None则返回全部
        threshold: 相关性分数阈值（0-1），低于此值的文档被过滤

    Returns:
        按相关性降序排列的文档列表，每个文档包含原始字段 + score
    """
    if not contexts:
        return []

    for i, ctx in enumerate(contexts):
        if "content" not in ctx:#因为后面有把向量检索和图检索整合统一格式的要求，因此没有content就是没有信息
            raise ValueError(f"Context at index {i} missing 'content' field")

    pairs = [[question, ctx["content"]]for ctx in contexts]# 构造 [[query, doc1], [query, doc2], ...] 格式

    # 计算分数
    try:
        reranker = get_reranker()
        scores = reranker.compute_score(pairs, normalize=True)

    except Exception as e:
        print(f"[Reranker] Error: {e}, falling back to original order")
        return [{**ctx, "score": 0.0} for ctx in contexts]

    # 组装结果
    scored_contexts = []
    for ctx, score in zip(contexts, scores):
        new_ctx = ctx.copy()
        new_ctx["score"] = float(score)
        scored_contexts.append(new_ctx)

    # 阈值过滤
    if threshold>0:
        scored_contexts = [c for c in scored_contexts if c["score"]>=threshold]

    # 排序
    scored_contexts.sort(key=lambda x: x["score"], reverse=True)

    # Top-K
    if top_k is not None and top_k > 0:
        scored_contexts = scored_contexts[:top_k]

    return scored_contexts
