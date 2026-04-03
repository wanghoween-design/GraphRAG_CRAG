import re

from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

from config import FAISS_PATH, EMBED_MODEL_NAME

def load_vector_store():
    embeddings = OllamaEmbeddings(model=EMBED_MODEL_NAME)
    db = FAISS.load_local(
        FAISS_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    return db

def clean_text(text: str):
    return re.sub(r"<think.*?</think.*?>", "", text, flags=re.DOTALL).strip()
