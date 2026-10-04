from typing import Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

# ---------- 1. 状态定义（所有节点共享的数据结构）----------

class GraphState(TypedDict):
    """LangGraph 状态定义"""
    question: str                    # 原始问题
    contexts: List[Dict]             # Rerank后的文档
    is_sufficient: bool              # Grader判断：是否足够
    confidence: float                # 置信度分数
    missing_info: str                # 缺失什么信息
    grader_reasoning: Optional[str]  # Grader评估理由 (供前端CRAG过程展示)
    rewritten_question: Optional[str]  # 改写后的问题
    final_answer: Optional[str]      # 最终答案
    iteration: int                   # 迭代次数（防止无限循环）
    web_context: Optional[str]     # 从网络获取的额外上下文
    chat_summary: Optional[str]       # 之前对话的压缩总结
    standalone_question: Optional[str] # 指代消解后的"独立问题"

# ---------- 2. Grader 结构化输出（Pydantic V2）----------

class GraderOutput(BaseModel):
    """
    Grader Node 的结构化输出
    对应简历："遵循 Pydantic V2 标准，定义严格的 BaseModel 数据契约"
    """
    is_sufficient: bool = Field(
        description="当前检索结果是否足够完整、准确地回答问题"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="置信度分数，0-1之间"
    )
    missing_info: Optional[str] = Field(
        default=None,
        description="如果信息不足，具体缺失什么（如'缺少时间信息'、'缺少确认情节'）"
    )
    reasoning: str = Field(
        description="评估理由，简要说明"
    )
