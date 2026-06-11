
# filename: mcp_server.py
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List

from fastmcp import FastMCP
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

try:
    from langchain_community.agent_toolkits.sql.base import create_sql_agent
except ImportError:
    from langchain_community.agent_toolkits import create_sql_agent


mcp = FastMCP("engineering-supervisor-tools")

session_store: Dict[str, List[dict]] = {}


def require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is not set.")


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    require_api_key()
    return OpenAIEmbeddings(model="text-embedding-3-large", base_url="https://us.api.openai.com/v1")


@lru_cache(maxsize=1)
def get_vectorstore() -> FAISS:
    return FAISS.load_local(
        "faiss_index",
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )


@lru_cache(maxsize=1)
def get_sql_agent():
    require_api_key()
    llm = ChatOpenAI(model="gpt-4.1", temperature=0, base_url="https://us.api.openai.com/v1")
    db = SQLDatabase.from_uri("sqlite:///project_management.db")
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    return create_sql_agent(llm=llm, toolkit=toolkit, verbose=False)


def run_rag_search(query: str) -> str:
    docs = get_vectorstore().similarity_search(query, k=3)
    if not docs:
        return "No matching knowledge-base results found."

    lines = []
    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        doc_title = (
            metadata.get("doc_title")
            or metadata.get("title")
            or metadata.get("source")
            or "Unknown"
        )
        chunk_text = " ".join(doc.page_content.split())
        lines.append(f"Result {i} (Source: {doc_title}): {chunk_text}")
    return "\n".join(lines)


def run_db_query(question: str) -> str:
    result = get_sql_agent().invoke({"input": question})
    if isinstance(result, dict):
        return str(result.get("output", result))
    return str(result)


def format_session_history(thread_id: str) -> str:
    history = session_store.get(thread_id, [])
    if not history:
        return "No prior queries in this session"

    worker_labels = {
        "rag": "knowledge base",
        "db": "project database",
        "memory": "memory",
    }

    parts = [f"Session history ({len(history)} queries):"]
    for item in history:
        worker_name = worker_labels.get(item["worker"], item["worker"])
        parts.append(
            f"{item['turn']}. {item['query']} — answered via {worker_name}."
        )
    return " ".join(parts)


def add_session_entry(
    thread_id: str,
    query: str,
    worker: str,
    summary: str,
) -> List[dict]:
    history = session_store.setdefault(thread_id, [])
    history.append(
        {
            "turn": len(history) + 1,
            "query": query,
            "worker": worker,
            "summary": summary,
        }
    )
    return history


@mcp.tool()
def rag_search(query: str) -> str:
    return run_rag_search(query)


@mcp.tool()
def db_query(question: str) -> str:
    return run_db_query(question)


@mcp.tool()
def get_session_history(thread_id: str) -> str:
    return format_session_history(thread_id)


if __name__ == "__main__":
    mcp.run()
