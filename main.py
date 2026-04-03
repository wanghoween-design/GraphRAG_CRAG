from graph import build_crag_graph, crag_graph
from services import GraphQueryService
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

# ==================== 交互式对话入口 ====================

if __name__ == "__main__":
    # 初始化
    print("[初始化] 连接 Neo4j...")
    graph_service = GraphQueryService(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)

    # 构建图 (注意：这里的 build_crag_graph 内部必须已经 return workflow.compile(checkpointer=MemorySaver()) )
    print("[初始化] 构建 LangGraph...")
    crag_graph = build_crag_graph()

    # 必须带上 thread_id，代表同一个会话窗口
    config = {"configurable": {"thread_id": "user_console_session"}}

    is_first_run = True  # 👈 用一个清晰的布尔值做标记，不要搞什么占位符

    print("\n" + "="*50)
    print("  庆余年知识库 CRAG 系统 (输入 'quit' 或 'exit' 退出)")
    print("="*50 + "\n")

    try:
        while True:
            user_input = input("👤 你: ").strip()

            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("🤖 再见！")
                break

            # 👇 清清爽爽的逻辑判断
            if is_first_run:
                # 第一次：给完整的初始状态
                current_state = {
                    "question": user_input,
                    "contexts": [],
                    "is_sufficient": False,
                    "confidence": 0.0,
                    "missing_info": None,
                    "rewritten_question": None,
                    "final_answer": None,
                    "iteration": 0,
                    "chat_summary": None,
                    "standalone_question": None,
                    "web_context": None
                }
                is_first_run = False  # 👈 打上标记，下次再也不进来了
            else:
                # 以后每一次：只给问题，让图自己合并历史记忆
                current_state = {"question": user_input}


            # 3. 执行图
            print("🤖 思考中...\n")
            result = crag_graph.invoke(current_state, config)

            # 4. 打印结果（你可以把调试信息删掉，只留答案，体验更好）
            # 这里为了你调试方便，保留了部分状态打印，正式使用时可以删减
            if result.get('rewritten_question') and result['rewritten_question'] != result['question']:
                print(f"🔍 [系统自动改写提问]: {result['rewritten_question']}\n")

            print(f"🤖 回答:\n{result['final_answer']}\n")
            print("-" * 50)

    except KeyboardInterrupt:
        print("\n🤖 检测到中断，退出程序。")
    finally:
        graph_service.close()
        print("[清理] Neo4j 连接已关闭")
