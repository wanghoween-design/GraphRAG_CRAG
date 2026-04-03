from typing import Dict

from tavily import TavilyClient

from models import GraphState
from config import tavily_api_key

tavily_client = TavilyClient(api_key=tavily_api_key)

def web_search_node(state: GraphState) -> GraphState:
    """
    Web Search 节点：本地知识库穷尽后的兜底方案
    """
    print(f"\n{'='*60}")
    print("【Step X】启动 Tavily 联网搜索 (本地检索已达上限)")
    print(f"{'='*60}")

    question = state["question"]

    try:
        client = tavily_client
        # 搜索 Top-3 结果，限定搜索深度为 basic 提升速度
        response = client.search(query=question, max_results=3, search_depth="basic")

        web_results = []
        for result in response.get("results", []):
            web_results.append(f"- {result.get('title', '')}: {result.get('content', '')}")

        web_text = "\n".join(web_results)
        print(f"  成功获取 {len(web_results)} 条网络结果")

        return {
            **state,
            "web_context": web_text,
            # 联网搜索到了，强行把充足度置为 True，让其进入生成环节
            "is_sufficient": True,
            "confidence": 0.6  # 联网结果的置信度给个及格分即可
        }
    except Exception as e:
        print(f"  [警告] Tavily 搜索失败: {e}")
        return {
            **state,
            "web_context": f"联网搜索失败: {e}",
            "is_sufficient": True, # 即使失败也放行，去生成节点报错，避免死循环
            "confidence": 0.0
        }
