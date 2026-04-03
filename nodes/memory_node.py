from langchain_ollama import ChatOllama

from models import GraphState
from config import LLM_NAME

def memory_node(state: GraphState) -> GraphState:
    """
    记忆节点：指代消解与问题独立化
    """
    current_q = state["question"]
    history_summary = state.get("chat_summary", "")

    # 如果是第一轮对话，直接跳过
    if not history_summary:
        return {**state, "standalone_question": current_q}

    print("\n>> [记忆召回] 检测到多轮对话，进行指代消解...")

    llm = ChatOllama(model=LLM_NAME, temperature=0.0)
    prompt = f"""根据历史对话总结，将用户的当前提问改写为一个独立、完整的问题。
不要回答问题，只输出改写后的问题。

历史总结：
{history_summary}

当前提问：{current_q}

改写后的问题："""

    try:
        response = llm.invoke(prompt)
        standalone_q = response.content.strip()
        print(f"  原问题：{current_q}")
        print(f"  消解后：{standalone_q}")

        return {
            **state,
            "standalone_question": standalone_q,
            # 👇 关键：用消解后的问题去替换原来的问题，送给后面的检索节点！
            "question": standalone_q
        }
    except Exception as e:
        print(f"  [警告] 指代消解失败: {e}")
        return {**state, "standalone_question": current_q}

def update_memory_node(state: GraphState) -> GraphState:
    """
    记忆更新节点：压缩对话，更新总结
    """
    current_q = state.get("standalone_question") or state["question"]
    current_a = state["final_answer"]
    old_summary = state.get("chat_summary", "")

    llm = ChatOllama(model=LLM_NAME, temperature=0.0)
    prompt = f"""请用一句简短的话（不超过50字），总结以下新发生的对话内容，并与旧总结合并。
旧总结：{old_summary if old_summary else '无'}
新对话：
Q: {current_q}
A: {current_a[:200]} # 只取答案前200字，省Token

合并后的新总结："""

    try:
        response = llm.invoke(prompt)
        new_summary = response.content.strip()
        print(f"\n>> [记忆更新] 当前对话记忆：{new_summary}")
        return {**state, "chat_summary": new_summary}
    except Exception as e:
        print(f"  [警告] 记忆更新失败: {e}")
        return {**state, "chat_summary": old_summary}
