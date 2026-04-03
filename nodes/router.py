from typing import Literal

from models import GraphState

def should_continue(state: GraphState) -> Literal["generate", "rewrite", "web_search"]:
    """
    条件边：判断是否足够，或已达到最大迭代次数
    """
    iteration = state.get("iteration", 0)

    # 防止无限循环：循环两次后联网搜索
    if iteration >= 2:
        print(f"\n[系统] 本地检索已达最大迭代次数({iteration})，触发 Tavily 联网兜底")
        return "web_search"

    # 判断质量
    if state.get("is_sufficient", False) and state.get("confidence", 0) > 0.7:
        return "generate"
    else:
        return "rewrite"
