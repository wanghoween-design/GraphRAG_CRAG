from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from models import GraphState
from nodes import grader_node, rewrite_node, generate_node, web_search_node, memory_node, update_memory_node, should_continue
from services import retrieve_and_rerank, GraphQueryService
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

# 初始化图服务（全局变量，build_crag_graph 使用）
graph_service = None

def build_crag_graph():
    """
    构建 CRAG 闭环图

    对应简历："基于 LangGraph 开发 Retrieve-Grade-Recover 闭环流程"
    """
    global graph_service
    graph_service = GraphQueryService(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)

    workflow = StateGraph(GraphState)


    # 添加节点
    workflow.add_node("memory", memory_node)
    workflow.add_node("retrieve_rerank", lambda state: {
        **state,
        "contexts": retrieve_and_rerank(state["question"], graph_service),
        "iteration": state.get("iteration", 0)
    })
    workflow.add_node("grader", grader_node)
    workflow.add_node("rewrite", rewrite_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("update_memory", update_memory_node)
    workflow.add_node("generate", generate_node)

    # 边：Memory → Retrieve → Grader
    workflow.set_entry_point("memory")
    workflow.add_edge("memory", "retrieve_rerank")
    workflow.add_edge("retrieve_rerank", "grader")


    # 条件边：Grader → Generate 或 Rewrite
    workflow.add_conditional_edges(
        "grader",
        should_continue,
        {
            "generate": "generate",
            "rewrite": "rewrite",
            "web_search": "web_search"
        }
    )

    # Rewrite 后重新 Retrieve（闭环！）
    workflow.add_edge("rewrite", "retrieve_rerank")
    # Web Search 后重新 直接去生成（不再回头检索本地了）
    workflow.add_edge("web_search", "generate")

    # Generate 后记忆更新
    workflow.add_edge("generate", "update_memory")
    workflow.add_edge("update_memory", END)

    # 使用 MemorySaver 作为 checkpoint，实现多轮对话记忆
    return workflow.compile(checkpointer=MemorySaver())

# 全局图实例（需要 graph_service，稍后初始化）
crag_graph = None
