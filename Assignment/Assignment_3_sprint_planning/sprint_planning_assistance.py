import asyncio
import operator
import os
import re
import sys
from pathlib import Path
from typing import Annotated, Literal
from typing_extensions import TypedDict

from fastmcp import Client, FastMCP
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


# -----------------------------
# FastMCP Server
# -----------------------------
mcp = FastMCP("SprintPlanningMCP")

BACKLOG = [
    {
        "title": "Login API hardening",
        "assignee": "Ava",
        "story_points": 5,
        "status": "in_progress",
        "risk_level": "medium",
    },
    {
        "title": "Analytics dashboard filters",
        "assignee": "Ben",
        "story_points": 8,
        "status": "todo",
        "risk_level": "high",
    },
    {
        "title": "Regression suite cleanup",
        "assignee": "Cara",
        "story_points": 3,
        "status": "done",
        "risk_level": "low",
    },
]


def format_task(task: dict, index: int) -> str:
    return (
        f"{index}. {task['title']} | assignee={task['assignee']} | "
        f"story_points={task['story_points']} | status={task['status']} | "
        f"risk_level={task['risk_level']}"
    )


@mcp.tool
def get_backlog() -> str:
    """Returns all tasks as a readable list."""
    if not BACKLOG:
        return "Backlog is empty."
    return "\n".join(format_task(task, i) for i, task in enumerate(BACKLOG, start=1))


@mcp.tool
def add_task(title: str, assignee: str, story_points: int) -> str:
    """Creates a new task with default status/risk."""
    BACKLOG.append(
        {
            "title": title,
            "assignee": assignee,
            "story_points": int(story_points),
            "status": "todo",
            "risk_level": "low",
        }
    )
    return f"Task added: {title} ({story_points} SP, assigned to {assignee})"


@mcp.tool
def check_capacity(velocity: int = 40) -> str:
    """Sums story points of all non-done tasks."""
    total = sum(task["story_points"] for task in BACKLOG if task["status"] != "done")
    diff = abs(total - velocity)
    if total > velocity:
        return f"Sprint is at {total}/{velocity} SP. Over capacity by {diff} SP."
    return f"Sprint is at {total}/{velocity} SP. Under capacity by {diff} SP."


@mcp.tool
def get_risk_summary() -> str:
    """Returns medium/high risk tasks as a numbered list."""
    risky = [t for t in BACKLOG if t["risk_level"] in {"medium", "high"}]
    if not risky:
        return "No medium or high risk tasks."
    lines = []
    for i, task in enumerate(risky, start=1):
        lines.append(
            f"{i}. {task['title']} | assignee={task['assignee']} | "
            f"story_points={task['story_points']} | status={task['status']} | "
            f"risk_level={task['risk_level']}"
        )
    return "\n".join(lines)


# -----------------------------
# Shared Models
# -----------------------------
class TaskBreakdown(BaseModel):
    title: str = Field(..., description="Clear sprint task title")
    assignee: str = Field(..., description="Role or person name")
    story_points: int = Field(..., ge=1, le=13)


class BreakdownResponse(BaseModel):
    feature: str
    tasks: list[TaskBreakdown] = Field(..., min_length=3, max_length=5)


class RouteDecision(BaseModel):
    route: Literal["SPRINT_BUILDER", "CAPACITY_CHECKER", "RISK_ASSESSOR", "FINISH"]


class PlanningState(TypedDict):
    user_input: str
    route: str
    worker_result: str
    final_response: str
    trace: Annotated[list[str], operator.add]
    tool_calls: Annotated[list[str], operator.add]


# -----------------------------
# MCP Client Wrapper
# -----------------------------
import sys
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

class SprintMCPClient:
    def __init__(self):
        self.client = None
        self._cm = None

    async def __aenter__(self):
        script_path = str(Path(__file__).resolve())

        transport = StdioTransport(
            command=sys.executable,
            args=[script_path, "server"],
        )

        self.client = Client(transport)
        self._cm = self.client
        await self._cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._cm:
            await self._cm.__aexit__(exc_type, exc, tb)

    async def call(self, tool_name: str, args: dict | None = None) -> str:
        result = await self.client.call_tool(tool_name, args or {})
        if isinstance(result, str):
            return result
        if hasattr(result, "content"):
            parts = []
            for item in result.content:
                text = getattr(item, "text", None)
                parts.append(text if text is not None else str(item))
            return "\n".join(parts).strip()
        return str(result)


# -----------------------------
# Helper Parsers
# -----------------------------
TASK_RE = re.compile(
    r"^\d+\.\s(?P<title>.*?)\s\| assignee=(?P<assignee>.*?)\s\| "
    r"story_points=(?P<sp>\d+)\s\| status=(?P<status>.*?)\s\| "
    r"risk_level=(?P<risk>.*)$"
)


def parse_backlog(backlog_text: str) -> list[dict]:
    tasks = []
    for line in backlog_text.splitlines():
        match = TASK_RE.match(line.strip())
        if match:
            tasks.append(
                {
                    "title": match.group("title"),
                    "assignee": match.group("assignee"),
                    "story_points": int(match.group("sp")),
                    "status": match.group("status"),
                    "risk_level": match.group("risk"),
                }
            )
    return tasks


# -----------------------------
# LangGraph App Builder
# -----------------------------
def build_graph(mcp_client: SprintMCPClient):
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        temperature=0,
        base_url='https://us.api.openai.com/v1'
    )
    router_llm = llm.with_structured_output(RouteDecision)
    builder_llm = llm.with_structured_output(BreakdownResponse)

    async def supervisor_node(state: PlanningState):
        if state.get("worker_result"):
            return {"route": "FINISH", "trace": ["Supervisor -> FINISH"]}

        prompt = f"""
You are a sprint-planning supervisor.
Route the user request to exactly one option:
- SPRINT_BUILDER: "Plan [feature]", "Add tasks for...", "Break down..."
- CAPACITY_CHECKER: "Check capacity", "How many SP", "Are we over budget", "Velocity"
- RISK_ASSESSOR: "Any risks", "What could go wrong", "Blockers", "Concerns"
- FINISH: "Done", "That's all", "Nothing else", "Quit"

User request: {state['user_input']}
Return only the route.
""".strip()
        decision = await router_llm.ainvoke(prompt)
        return {
            "route": decision.route,
            "trace": [f"Supervisor -> {decision.route}"],
        }

    async def sprint_builder_node(state: PlanningState):
        feature = state["user_input"]
        plan = await builder_llm.ainvoke(
            f"""
Break this feature into 3 to 5 sprint-ready tasks.
Use realistic assignees like Backend Dev, Frontend Dev, QA Engineer, DevOps Engineer, Product Analyst.
Keep story points between 1 and 8 when possible.

Feature: {feature}
"""
        )

        tool_calls = []
        created = []
        for task in plan.tasks:
            args = {
                "title": task.title,
                "assignee": task.assignee,
                "story_points": task.story_points,
            }
            tool_calls.append(
                f"add_task(title={task.title}, assignee={task.assignee}, story_points={task.story_points})"
            )
            await mcp_client.call("add_task", args)
            created.append(f"{task.title} ({task.story_points} SP)")

        result = f"Created {len(created)} tasks for [{plan.feature}]: " + ", ".join(
            f"[{item}]" for item in created
        )
        return {
            "worker_result": result,
            "trace": ["SPRINT_BUILDER completed"],
            "tool_calls": tool_calls,
        }

    async def capacity_checker_node(state: PlanningState):
        tool_calls = ["check_capacity(velocity=40)", "get_backlog()"]
        capacity_text = await mcp_client.call("check_capacity", {"velocity": 40})
        backlog_text = await mcp_client.call("get_backlog")
        tasks = parse_backlog(backlog_text)

        recommendation = "Sprint has room for additional items"
        if "Over capacity" in capacity_text:
            candidates = [t for t in tasks if t["status"] != "done"]
            if candidates:
                candidates.sort(
                    key=lambda t: (t["story_points"], t["risk_level"] == "low"),
                    reverse=True,
                )
                recommendation = f"Recommend descoping {candidates[0]['title']}"

        return {
            "worker_result": f"{capacity_text} {recommendation}",
            "trace": ["CAPACITY_CHECKER completed"],
            "tool_calls": tool_calls,
        }

    async def risk_assessor_node(state: PlanningState):
        tool_calls = ["get_backlog()", "get_risk_summary()"]
        backlog_text = await mcp_client.call("get_backlog")
        risk_text = await mcp_client.call("get_risk_summary")

        analysis = await llm.ainvoke(
            f"""
You are a sprint risk assessor.

Backlog:
{backlog_text}

Risk summary:
{risk_text}

Identify 2 to 3 specific sprint risks.
Rules:
- Each risk must name a specific task.
- Mention story points/status/assignee/risk level when relevant.
- Explain why it is risky in one sentence.
- Use numbered lines only.
"""
        )

        return {
            "worker_result": analysis.content.strip(),
            "trace": ["RISK_ASSESSOR completed"],
            "tool_calls": tool_calls,
        }

    async def finish_node(state: PlanningState):
        final = state.get("worker_result") or "Session finished."
        return {"final_response": final, "trace": ["END"]}

    def route_from_supervisor(state: PlanningState):
        return state["route"]

    graph = StateGraph(PlanningState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("sprint_builder", sprint_builder_node)
    graph.add_node("capacity_checker", capacity_checker_node)
    graph.add_node("risk_assessor", risk_assessor_node)
    graph.add_node("finish", finish_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "SPRINT_BUILDER": "sprint_builder",
            "CAPACITY_CHECKER": "capacity_checker",
            "RISK_ASSESSOR": "risk_assessor",
            "FINISH": "finish",
        },
    )
    graph.add_edge("sprint_builder", "supervisor")
    graph.add_edge("capacity_checker", "supervisor")
    graph.add_edge("risk_assessor", "supervisor")
    graph.add_edge("finish", END)

    return graph.compile()


# -----------------------------
# CLI Modes
# -----------------------------
async def run_single_request(app, user_input: str):
    state: PlanningState = {
        "user_input": user_input,
        "route": "",
        "worker_result": "",
        "final_response": "",
        "trace": [],
        "tool_calls": [],
    }
    return await app.ainvoke(state)


async def run_demo(app):
    print("Sprint Planning Assistant")
    print("Type a request, or 'Quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        result = await run_single_request(app, user_input)
        print(f"\nAssistant: {result['final_response']}")
        print("Routing Trace:", " -> ".join(result["trace"]))
        print("MCP Tool Calls:", ", ".join(result["tool_calls"]) or "None", "\n")
        if result["route"] == "FINISH" and user_input.lower() in {
            "done",
            "that's all",
            "nothing else",
            "quit",
        }:
            break


async def run_tests(app):
    requests = [
        "Plan user profile export feature",
        "Check capacity",
        "Any risks in this sprint?",
        "Add tasks for payment retry improvements",
        "Done",
    ]
    for i, request in enumerate(requests, start=1):
        result = await run_single_request(app, request)
        print(f"\n=== Test {i}: {request} ===")
        print(result["final_response"])
        print("Routing Trace:", " -> ".join(result["trace"]))
        print("MCP Tool Calls:", ", ".join(result["tool_calls"]) or "None")


async def run_client_mode(mode: str):
    async with SprintMCPClient() as mcp_client:
        app = build_graph(mcp_client)
        from IPython.display import Image, display

        png_bytes = app.get_graph().draw_mermaid_png()

        with open("logic.png", "wb") as f:
            f.write(png_bytes)

        print("Graph image saved as langgraph.png")
        if mode == "test":
            await run_tests(app)
        else:
            await run_demo(app)


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "demo"
    if mode == "server":
        mcp.run()
        return
    if mode in {"demo", "test", "server"}:
        asyncio.run(run_client_mode(mode))
        return
    print("Usage: python sprint_planning_assistant.py [server|demo|test]")


if __name__ == "__main__":
    main()
