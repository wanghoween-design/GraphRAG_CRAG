# -*- coding: utf-8 -*-
"""
FastAPI Web Server for 《庆余年》 Novel Character GraphRAG & CRAG Interactive Assistant.
Serves both REST APIs and the aesthetic Neo-Chinese novel interface.

问答走 WebCRAGService 统一门面:
- Ollama 可达 → LangGraph Retrieve-Grade-Recover 闭环 (多轮会话记忆)
- 不可达/失败 → 离线规则引擎 (全书章节检索兜底)
LangGraph 的 invoke 是同步阻塞调用, 通过 asyncio.to_thread 交给线程池执行。
"""
import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from graph_data_provider import graph_provider
from crag_service import crag_service, is_ollama_active
from config import LLM_NAME

app = FastAPI(
    title="余年卷册 · GraphRAG 智能考据阁",
    description="《庆余年》小说人物关系图谱与 CRAG 智能问答系统",
    version="2.0.0"
)

# 允许跨域请求 (通配符源不允许携带凭据, 两者只能取其一)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源目录
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = "user_web_session"

@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "Frontend building", "message": "Index file is being created"})

@app.get("/api/status")
async def get_system_status():
    """获取系统运行健康状态与图谱容量指标"""
    graph = graph_provider.get_full_graph()
    ollama_ok = is_ollama_active()
    return {
        "neo4j_connected": graph_provider.driver is not None,
        "ollama_active": ollama_ok,
        "total_nodes": len(graph["nodes"]),
        "total_links": len(graph["links"]),
        "total_factions": len(graph["factions"]),
        "crag_engine": f"LangGraph CRAG 闭环 (Ollama · {LLM_NAME})" if ollama_ok else "离线规则引擎 (全书语料兜底)",
        "novel_title": "《庆余年》 (猫腻 著)"
    }

@app.get("/api/graph")
async def get_graph_data():
    """获取全量关系图谱数据供前端 SVG 绘制与拖拽物理模拟"""
    return graph_provider.get_full_graph()

@app.get("/api/character/{name}")
async def get_character_profile(name: str):
    """获取指定小说人物的深度秘档与全向关系网"""
    detail = graph_provider.get_character_detail(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"未找到原著人物「{name}」的秘卷")
    return detail

@app.post("/api/chat")
async def chat_interaction(req: ChatRequest):
    """
    CRAG 闭环小说智能问答接口
    - LangGraph 模式: 真实 Retrieve-Grade-Recover 推演 + 按 session_id 的多轮记忆
    - 离线模式: 图谱三元组 + 全书 719 章真实章节引用
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="提问内容不可为空")

    session_id = req.session_id or "user_web_session"
    result = await asyncio.to_thread(crag_service.query, req.question.strip(), session_id)
    return result

# 挂载静态资源
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("  余年卷册 · GraphRAG 智能考据阁 Web 服务启动中...")
    print("  访问地址: http://127.0.0.1:8000")
    print("="*60 + "\n")
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=False)
