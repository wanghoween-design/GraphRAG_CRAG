import os

from dotenv import load_dotenv

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# 锚定项目根目录, 避免依赖启动时的工作目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAISS_PATH = os.path.join(BASE_DIR, "data", "vector_store", "qyn_faiss")
EMBED_MODEL_NAME = "nomic-embed-text"
RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
LLM_NAME = "qwen3:4b"
tavily_api_key = os.getenv("TAVILY_API_KEY")
