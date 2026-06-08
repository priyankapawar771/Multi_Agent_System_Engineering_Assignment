
# filename: research_agent.py

import logging
import os
from typing import Dict, Literal

from fastapi import FastAPI, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

app = FastAPI(title="ResearchAgent", version="1.0")
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
task_store: Dict[str, dict] = {}


class Message(BaseModel):
    role: Literal["user"]
    content: str


class TaskRequest(BaseModel):
    id: str
    message: Message


class TaskResult(BaseModel):
    id: str
    status: Literal["completed"]
    output: str


AGENT_CARD = {
    "name": "ResearchAgent",
    "version": "1.0",
    "description": "A2A research agent that returns structured research on a topic.",
    "url": "http://localhost:8001",
    "skills": [
        {
            "name": "topic_research",
            "description": "Researches a topic and returns facts, trends, and a challenge.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"}
                },
                "required": ["topic"]
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "output": {"type": "string"}
                },
                "required": ["output"]
            },
        }
    ],
}


def build_research_prompt(topic: str) -> str:
    return f"""
You are a research agent.

Research the topic below and return ONLY this exact structure:

3 Key Facts:
1. ...
2. ...
3. ...

2 Current Trends:
1. ...
2. ...

1 Notable Challenge:
...

Rules:
- Keep the content concise but useful.
- Do not add markdown bolding.
- Do not add extra headings or commentary.
- The topic is: {topic}
""".strip()


@app.get("/.well-known/agent.json")
async def get_agent_card():
    return AGENT_CARD


@app.post("/tasks/send", response_model=TaskResult)
async def send_task(task: TaskRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

    logging.info(f"A2A task received: {task.id} — topic: {task.message.content}")

    response = await client.responses.create(
        model="gpt-4.1",
        input=build_research_prompt(task.message.content),
    )

    result = {
        "id": task.id,
        "status": "completed",
        "output": response.output_text.strip(),
    }
    task_store[task.id] = result
    return result


@app.get("/tasks/{task_id}", response_model=TaskResult)
async def get_task(task_id: str):
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="Task not found.")

    logging.info(f"A2A task result requested: {task_id}")
    return task_store[task_id]
