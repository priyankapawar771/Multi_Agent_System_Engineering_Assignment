
from __future__ import annotations

from typing import Literal, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from mcp_server import (
    add_session_entry,
    format_session_history,
    run_db_query,
    run_rag_search,
    session_store,
)
from dotenv import load_dotenv

load_dotenv()



class AssistantState(TypedDict, total=False):
    messages: list
    route: str
    worker_result: str
    session_history: list[dict]
    thread_id: str
    query: str


class RouteDecision(BaseModel):
    route: Literal["rag", "db", "memory", "FINISH"]


router_llm = ChatOpenAI(model="gpt-4.1", temperature=0, base_url="https://us.api.openai.com/v1")
answer_llm = ChatOpenAI(model="gpt-4.1", temperature=0, base_url="https://us.api.openai.com/v1")


def compact_summary(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def rule_based_route(query: str) -> str | None:
    q = query.lower().strip()

    finish_phrases = {
        "done",
        "thanks",
        "thank you",
        "that's all",
        "thats all",
        "all good",
        "bye",
    }
    if q in finish_phrases:
        return "FINISH"

    memory_keywords = [
        "what have i asked",
        "what did i ask",
        "recap our conversation",
        "recap the conversation",
        "so far",
        "earlier",
        "session",
        "conversation history",
        "asked you before",
    ]
    if any(keyword in q for keyword in memory_keywords):
        return "memory"

    db_keywords = [
        "task",
        "tasks",
        "incident",
        "incidents",
        "team member",
        "team members",
        "story point",
        "story points",
        "sprint",
        "blocked",
        "assigned",
        "assignee",
        "database",
        "project data",
        "project status",
    ]
    rag_keywords = [
        "microservices",
        "monolith",
        "trunk-based",
        "devops",
        "best practice",
        "best practices",
        "architecture",
        "methodology",
        "pattern",
        "patterns",
        "engineering concept",
        "engineering concepts",
        "ci/cd",
        "testing strategy",
    ]

    has_db = any(keyword in q for keyword in db_keywords)
    has_rag = any(keyword in q for keyword in rag_keywords)

    if has_db and has_rag:
        return "rag"
    if has_db:
        return "db"
    if has_rag:
        return "rag"

    return None


def llm_route(query: str) -> str:
    prompt = f"""
Classify the user's query into exactly one route:
- rag: engineering concepts, best practices, methodology, architecture patterns
- db: project data such as tasks, incidents, team members, story points, sprint status
- memory: asks about this session or prior turns
- FINISH: done/thanks/stop signals

Ambiguous policy:
If the user asks for advice or best practices based on earlier project data,
choose rag.

User query: {query}
"""
    decision = router_llm.with_structured_output(RouteDecision).invoke(prompt)
    return decision.route


def get_query(state: AssistantState) -> str:
    if state.get("query"):
        return state["query"]
    messages = state.get("messages", [])
    if messages:
        return messages[-1]["content"]
    return ""


def supervisor_node(state: AssistantState) -> AssistantState:
    query = get_query(state)
    route = rule_based_route(query) or llm_route(query)
    return {"route": route}


def rag_worker_node(state: AssistantState) -> AssistantState:
    query = get_query(state)
    thread_id = state["thread_id"]
    session_text = format_session_history(thread_id)

    retrieval_query = query
    if "based on our conversation" in query.lower() or "blocked tasks" in query.lower():
        retrieval_query = f"Session context: {session_text}\n\nUser question: {query}"

    tool_output = run_rag_search(retrieval_query)

    prompt = f"""
You are the RAG worker.
Answer the user's question using only the retrieved knowledge-base text and
the session context below.
If the user asks for best practices based on prior blocked tasks, tailor the
answer to that context.
If the retrieved text is weak, say so plainly.

User question:
{query}

Session context:
{session_text}

Retrieved text:
{tool_output}
"""
    answer = answer_llm.invoke(prompt).content
    return {
        "worker_result": answer,
        "messages": state.get("messages", []) + [{"role": "assistant", "content": answer}],
    }


def db_worker_node(state: AssistantState) -> AssistantState:
    query = get_query(state)
    answer = run_db_query(query)
    return {
        "worker_result": answer,
        "messages": state.get("messages", []) + [{"role": "assistant", "content": answer}],
    }


def memory_worker_node(state: AssistantState) -> AssistantState:
    thread_id = state["thread_id"]
    answer = format_session_history(thread_id)
    return {
        "worker_result": answer,
        "messages": state.get("messages", []) + [{"role": "assistant", "content": answer}],
    }


def finish_node(state: AssistantState) -> AssistantState:
    answer = "Conversation complete."
    return {
        "worker_result": answer,
        "messages": state.get("messages", []) + [{"role": "assistant", "content": answer}],
    }


def record_turn_node(state: AssistantState) -> AssistantState:
    thread_id = state["thread_id"]
    query = get_query(state)
    worker = state["route"]
    summary = compact_summary(state["worker_result"])
    updated = add_session_entry(thread_id, query, worker, summary)
    return {"session_history": updated}


def next_node(state: AssistantState) -> str:
    return state["route"]


def build_graph():
    workflow = StateGraph(AssistantState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_worker", rag_worker_node)
    workflow.add_node("db_worker", db_worker_node)
    workflow.add_node("memory_worker", memory_worker_node)
    workflow.add_node("finish", finish_node)
    workflow.add_node("record_turn", record_turn_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        next_node,
        {
            "rag": "rag_worker",
            "db": "db_worker",
            "memory": "memory_worker",
            "FINISH": "finish",
        },
    )

    workflow.add_edge("rag_worker", "record_turn")
    workflow.add_edge("db_worker", "record_turn")
    workflow.add_edge("memory_worker", "record_turn")

    workflow.add_edge("record_turn", END)
    workflow.add_edge("finish", END)

    return workflow.compile(checkpointer=MemorySaver())


def run_turn(graph, query: str, thread_id: str) -> dict:
    state = {
        "messages": [{"role": "user", "content": query}],
        "route": "",
        "worker_result": "",
        "session_history": session_store.get(thread_id, []).copy(),
        "thread_id": thread_id,
        "query": query,
    }
    return graph.invoke(
        state,
        config={"configurable": {"thread_id": thread_id}},
    )
