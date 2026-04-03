from langchain_ollama import ChatOllama

from models import GraphState
from config import LLM_NAME

def rewrite_node(state: GraphState) -> GraphState:
    """
    Rewrite 节点：查询改写，获取更多信息

    对应简历："对低质结果触发 Query Rewrite"
    """
    print(f"\n{'='*60}")
    print("【Step 4】Query Rewrite")
    print(f"{'='*60}")

    llm = ChatOllama(model=LLM_NAME, temperature=0.7)  # 需要创造性，温度稍高

    prompt = f"""原问题检索结果不足，需要进行查询改写。

原问题：{state['question']}
缺失信息：{state.get('missing_info', '未知')}

请改写查询，使其更具体、更容易检索到准确信息。可以：
1. 补充关键实体名（如"范闲"→"范闲 庆帝 父子关系 确认"）
2. 明确时间线索（如"什么时候"→"大东山之战 第几章"）
3. 分解复杂问题

只输出改写后的查询，不要解释。"""

    try:
        response = llm.invoke(prompt)
        rewritten = response.content.strip()
        print(f"  原问题：{state['question']}")
        print(f"  改写后：{rewritten}")

        return {
            **state,
            "rewritten_question": rewritten,
            "question": rewritten,  # 更新问题，用于重新检索
            "iteration": state.get("iteration", 0) + 1
        }
    except Exception as e:
        print(f"  [警告] Rewrite 失败: {e}")
        return {
            **state,
            "rewritten_question": state["question"],
            "iteration": state.get("iteration", 0) + 1
        }
