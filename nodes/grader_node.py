from langchain_ollama import ChatOllama

from models import GraphState, GraderOutput
from config import LLM_NAME

def grader_node(state: GraphState) -> GraphState:
    """
    Grader 节点：评估检索质量，决定是否进入 Rewrite

    对应简历："引入 Grader Node 对图谱及向量检索结果进行置信度评分"
    """
    print(f"\n{'='*60}")
    print("【Step 3】Grader 评估")
    print(f"{'='*60}")

    contexts = state["contexts"]
    question = state["question"]

    if not contexts:
        return {
            **state,
            "is_sufficient": False,
            "confidence": 0.0,
            "missing_info": "未检索到任何文档"
        }

    # 准备评估内容（取前3个高分文档）
    top_contexts = contexts[:3]
    context_text = "\n\n".join([
        f"[{i+1}] {ctx['content'][:300]}..."
        for i, ctx in enumerate(top_contexts)
    ])

    # LLM 结构化评估
    llm = ChatOllama(model=LLM_NAME, temperature=0.0)
    structured_llm = llm.with_structured_output(GraderOutput)

    prompt = f"""评估以下检索结果是否足够回答用户问题。

用户问题：{question}

检索到的文档（按相关性排序）：
{context_text}

评估标准：
1. 信息完整性：是否直接回答了问题？
2. 准确性：信息是否准确、无矛盾？
3. 时效性：对于小说情节，是否有明确的章节定位？

注意：小说问答需要精确的情节定位。如果文档只有猜测、暗示，没有明确确认，视为不足。"""

    try:
        result = structured_llm.invoke(prompt)
        print(f"  评估结果：{result.is_sufficient} (置信度: {result.confidence_score:.2f})")
        print(f"  理由：{result.reasoning[:100]}...")
        if result.missing_info:
            print(f"  缺失：{result.missing_info}")

        return {
            **state,
            "is_sufficient": result.is_sufficient,
            "confidence": result.confidence_score,
            "missing_info": result.missing_info
        }
    except Exception as e:
        print(f"  [警告] Grader 解析失败: {e}")
        # 保守策略：认为不足
        return {
            **state,
            "is_sufficient": False,
            "confidence": 0.0,
            "missing_info": f"评估解析失败: {e}"
        }
