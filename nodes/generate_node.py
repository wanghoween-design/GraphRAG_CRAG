from langchain_ollama import ChatOllama

from models import GraphState
from config import LLM_NAME

def generate_node(state: GraphState) -> GraphState:
    """
    Generate 节点：基于检索结果生成答案
    """
    print(f"\n{'='*60}")
    print("【Step 5】生成答案")
    print(f"{'='*60}")

    question = state["question"]
    web_context = state.get("web_context") # 👇 提取联网内容

    # ---------- 构造上下文逻辑调整 ----------
    context_text = ""

    # 情况 A：有本地图谱/向量文档
    if state.get("contexts"):
        local_text = "\n\n".join([
            f"【来源：{ctx.get('source', '未知')}】{ctx['content'][:400]}"
            for ctx in state["contexts"][:3]
        ])
        context_text += f"【本地知识库检索结果】\n{local_text}\n\n"

    # 情况 B：有联网结果
    if web_context:
        context_text += f"【互联网实时搜索结果】\n{web_context}\n\n"

    if not context_text:
        return {**state, "final_answer": "抱歉，本地和联网均未找到相关信息。"}

    # ---------- Prompt 调整 ----------
    prompt = f"""基于以下检索到的文档，回答用户问题。

用户问题：{question}

检索文档：
{context_text}

要求：
1. 如果【本地知识库】中有明确答案，优先以本地知识库为准，并引用卷名/章节。
2. 如果【本地知识库】无答案，请基于【互联网实时搜索结果】进行回答，并说明"根据网络资料"。
3. 直接回答问题，不要绕弯。
4. 如果信息依然不足，明确说明。

答案："""

    try:
        llm = ChatOllama(model=LLM_NAME, temperature=0.0)
        response = llm.invoke(prompt)
        answer = response.content
        print(f"\n{answer[:500]}...")
        return {**state, "final_answer": answer}
    except Exception as e:
        return {**state, "final_answer": f"生成答案时出错: {e}"}
