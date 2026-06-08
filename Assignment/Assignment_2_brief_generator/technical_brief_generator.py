
import json
import os
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class BriefState(TypedDict, total=False):
    topic: str
    facts: list[str]
    insights: list[str]
    claims: list[str]
    claim_count: int
    retry_count: int
    article: str


MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url='https://us.api.openai.com/v1')

TEST_TOPICS = {
    "1": "Event-driven architecture",
    "2": "GraphQL vs REST APIs",
}


def trace(stage: str, state: BriefState, note: str = "") -> None:
    print(
        f"[{stage}] claim_count={state.get('claim_count', 0)} "
        f"retry_count={state.get('retry_count', 0)}"
        + (f" | {note}" if note else "")
    )


def llm_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return json.loads(response.choices[0].message.content)


def clean_fact(text: str) -> str:
    text = text.strip()
    if ". " in text[:4]:
        text = text.split(". ", 1)[1].strip()
    return text


def unique_new_items(items: list[str], existing: list[str]) -> list[str]:
    seen = {x.casefold() for x in existing}
    out: list[str] = []
    for item in items:
        cleaned = clean_fact(item)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            out.append(cleaned)
            seen.add(key)
    return out


def researcher_node(state: BriefState) -> BriefState:
    retry_count = state.get("retry_count", 0)
    prior_facts = state.get("facts", [])
    prior_claim_count = state.get("claim_count", 0)

    is_retry = bool(prior_facts) and prior_claim_count < 5
    if is_retry:
        retry_count += 1

    working_state: BriefState = {**state, "retry_count": retry_count}
    trace("Researcher", working_state, f"topic={state['topic']}")

    first_pass_comparison = (
        retry_count == 0 and " vs " in state["topic"].lower() and not prior_facts
    )

    style_instruction = (
        "This is a comparison topic on pass 1. Return exactly 7 highly specific contrast "
        "fragments, not full sentences, so the quality gate can test research depth. "
        "Do not repeat prior facts."
        if first_pass_comparison
        else "Return at least 7 new, specific, numbered facts as full declarative statements. "
        "Do not repeat prior facts."
    )

    system_prompt = (
        "You are a technical researcher. Output JSON only with a single key: facts. "
        "facts must be an array of strings."
    )

    user_prompt = f"""
Topic: {state['topic']}

Existing facts to avoid repeating:
{json.dumps(prior_facts, indent=2)}

Instructions:
- {style_instruction}
- Be concrete and technically accurate.
- Avoid vague generalisations.
- On retries, add new facts only.
- Output format:
{{
  "facts": ["1. ...", "2. ..."]
}}
""".strip()

    data = llm_json(system_prompt, user_prompt)
    new_facts = unique_new_items(data.get("facts", []), prior_facts)

    if len(new_facts) < 7:
        raise ValueError("Researcher returned fewer than 7 new distinct facts.")

    return {
        "facts": prior_facts + new_facts,
        "retry_count": retry_count,
    }


def analyst_node(state: BriefState) -> BriefState:
    trace("Analyst", state, f"facts={len(state.get('facts', []))}")

    system_prompt = (
        "You are a technical analyst. Output JSON only with keys: insights, claims, claim_count. "
        "A valid claim must be a distinct, verifiable factual statement with a subject and predicate."
    )

    user_prompt = f"""
Topic: {state['topic']}

Facts:
{json.dumps(state.get('facts', []), indent=2)}

Tasks:
1. Distill the facts into 3 to 6 structured insights.
2. Identify only distinct, verifiable claims written as full factual statements.
3. Set claim_count to the number of valid claims.
4. Ignore fragments, vague statements, duplicates, or opinions.

Output format:
{{
  "insights": ["..."],
  "claims": ["..."],
  "claim_count": 0
}}
""".strip()

    data = llm_json(system_prompt, user_prompt)
    claims = data.get("claims", [])
    claim_count = int(data.get("claim_count", len(claims)))

    return {
        "insights": data.get("insights", []),
        "claims": claims,
        "claim_count": claim_count,
    }


def gate_router(state: BriefState) -> str:
    trace("Gate", state)
    if state.get("claim_count", 0) < 5 and state.get("retry_count", 0) < 2:
        print("  -> Route: Researcher")
        return "researcher"
    print("  -> Route: Writer")
    return "writer"


def writer_node(state: BriefState) -> BriefState:
    note = ""
    if state.get("claim_count", 0) < 5 and state.get("retry_count", 0) >= 2:
        note = f"Research incomplete — only {state['claim_count']} claims found."

    trace("Writer", state, note or "ready")

    system_prompt = (
        "You are a technical brief writer. Output JSON only with keys: overview, "
        "key_considerations, recommendation."
    )

    user_prompt = f"""
Topic: {state['topic']}
Claim count: {state.get('claim_count', 0)}
Note: {note if note else "None"}

Facts:
{json.dumps(state.get('facts', []), indent=2)}

Insights:
{json.dumps(state.get('insights', []), indent=2)}

Requirements:
- Overview: exactly 1 paragraph, 80 to 100 words.
- Key Considerations: 3 to 5 bullets, each a single sentence.
- Recommendation: exactly 1 paragraph, 60 to 80 words, clearly stating the author's recommendation.
- If note is present, include it as a short leading line before the brief.

Output format:
{{
  "overview": "...",
  "key_considerations": ["...", "..."],
  "recommendation": "..."
}}
""".strip()

    data = llm_json(system_prompt, user_prompt)

    parts: list[str] = []
    if note:
        parts.append(note)
    parts.append("Overview")
    parts.append(data["overview"])
    parts.append("")
    parts.append("Key Considerations")
    for item in data["key_considerations"]:
        parts.append(f"- {item}")
    parts.append("")
    parts.append("Recommendation")
    parts.append(data["recommendation"])

    return {"article": "\n".join(parts)}


def build_graph():
    graph = StateGraph(BriefState)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("writer", writer_node)

    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "analyst")
    graph.add_conditional_edges(
        "analyst",
        gate_router,
        {
            "researcher": "researcher",
            "writer": "writer",
        },
    )
    graph.add_edge("writer", END)
    return graph.compile()


def run_topic(app, topic: str) -> BriefState:
    print("\n" + "=" * 80)
    print(f"TOPIC: {topic}")
    result = app.invoke(
        {
            "topic": topic,
            "facts": [],
            "insights": [],
            "claims": [],
            "claim_count": 0,
            "retry_count": 0,
            "article": "",
        }
    )
    print("\nFINAL BRIEF\n")
    print(result["article"])
    return result


def normalize_topic(user_input: str) -> str:
    value = user_input.strip().lower()
    aliases = {
        "1": "Event-driven architecture",
        "event-driven architecture": "Event-driven architecture",
        "event driven architecture": "Event-driven architecture",
        "2": "GraphQL vs REST APIs",
        "graphql vs rest apis": "GraphQL vs REST APIs",
        "graphql vs rest api": "GraphQL vs REST APIs",
        "graphql vs rest api's": "GraphQL vs REST APIs",
        "graphql vs rest": "GraphQL vs REST APIs",
    }
    return aliases.get(value, "")


def prompt_for_topic() -> str:

    while True:
        user_input = input("\nEnter topic: ")
        topic = normalize_topic(user_input)
        if user_input:
            return user_input
        print("Invalid input. Please enter 1, 2, or one of the supported topic names.")


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("Set OPENAI_API_KEY before running this script.")

    app = build_graph()
    from IPython.display import Image, display

    png_bytes = app.get_graph().draw_mermaid_png()

    with open("logic.png", "wb") as f:
        f.write(png_bytes)

    print("Graph image saved as langgraph.png")
    while True:
        topic = input("\nEnter topic: ").strip()

        if topic.lower() == "exit":
            print("GoodBye")
            break

        run_topic(app, topic)


if __name__ == "__main__":
    main()
