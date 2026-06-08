
import json
import os
import re
from operator import add
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

THREAD_ID = "shift-2024-11-15"
TEAM_ROSTER = ["Ava Patel", "Noah Kim", "Mia Chen"]


class MainState(TypedDict, total=False):
    raw_incident: dict[str, Any]
    incident_id: str
    severity: Literal["critical", "high", "medium", "low"]
    service: str
    error: str
    affected_users: int
    region: str
    incident_history: Annotated[list[str], add]
    cross_reference: str
    current_output: list[str]
    current_eta: str
    next_route: str
    critical_count: int


class EscalationState(TypedDict, total=False):
    incident_id: str
    severity: str
    service: str
    error: str
    affected_users: int
    region: str
    critical_count: int
    root_cause: str
    remediation: str
    pagerduty_alert: str


def build_llm() -> ChatOpenAI | None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return None
    model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return ChatOpenAI(model=model_name, temperature=0)


LLM = build_llm()


def load_incident(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def parse_history_line(line: str) -> dict[str, Any] | None:
    pattern = r"^(INC-\d+): (.+?) — (.+) \((\d+) users affected\)$"
    match = re.match(pattern, line)
    if not match:
        return None
    return {
        "incident_id": match.group(1),
        "service": match.group(2),
        "error": match.group(3),
        "affected_users": int(match.group(4)),
    }


def build_cross_reference(
    incident_history: list[str], service: str
) -> str:
    matches = []
    for line in incident_history:
        parsed = parse_history_line(line)
        if parsed and parsed["service"] == service:
            matches.append(parsed)

    if not matches:
        return ""

    previous = matches[-1]
    this_count = len(matches) + 1
    return (
        f"Note: This is the {ordinal(this_count)} {service} incident "
        f"this shift. {previous['incident_id']} involved "
        f"{previous['error']} — check if root cause is related."
    )


def watch_phrase(error: str) -> str:
    lowered = error.lower()
    if "503" in lowered:
        return "elevated 503"
    return lowered


def extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


def high_severity_fallback(
    service: str, error: str
) -> tuple[list[tuple[int, str]], int]:
    lowered = error.lower()

    if service == "user-auth" and "key rotation" in lowered:
        steps = [
            (
                15,
                "Roll back the key rotation job and restart the auth "
                "service.",
            ),
            (
                30,
                "Re-run key rotation using the verified config from "
                "last week.",
            ),
            (
                45,
                "Validate JWT sign and verify across all active sessions.",
            ),
        ]
        return steps, 90

    steps = [
        (
            10,
            f"Freeze new changes on {service} and capture logs for "
            f"'{error}'.",
        ),
        (
            20,
            "Revert the most recent risky config or deployment tied to "
            "the alert window.",
        ),
        (
            30,
            "Run smoke validation on the affected user path and confirm "
            "error recovery in dashboards.",
        ),
    ]
    return steps, 60


def build_high_response(
    incident: dict[str, Any], cross_reference: str
) -> tuple[str, str]:
    steps, etr_minutes = high_severity_fallback(
        incident["service"], incident["error"]
    )

    if LLM:
        prompt = f"""
Return ONLY valid JSON.

Schema:
{{
  "steps": [
    {{"minutes": 15, "action": "action text"}},
    {{"minutes": 30, "action": "action text"}},
    {{"minutes": 45, "action": "action text"}}
  ],
  "etr_minutes": 90
}}

Rules:
- exactly 3 steps
- concrete operational actions only
- no markdown
- base it only on this incident
- do not include the cross-reference note in the JSON

Incident:
{json.dumps(incident)}
"""
        try:
            raw = LLM.invoke(prompt).content
            parsed = extract_json_object(raw)
            candidate_steps = parsed.get("steps", [])
            candidate_etr = int(parsed.get("etr_minutes", 0))
            if len(candidate_steps) == 3 and candidate_etr > 0:
                steps = [
                    (int(item["minutes"]), item["action"].strip())
                    for item in candidate_steps
                ]
                etr_minutes = candidate_etr
        except Exception:
            pass

    plan = " ".join(
        [
            f"Step {index} ({minutes} min): {action}"
            for index, (minutes, action) in enumerate(steps, start=1)
        ]
    )
    plan += f" Estimated time to resolution: {etr_minutes} min."
    if cross_reference:
        plan += f" {cross_reference}"
    return plan, f"{etr_minutes} min"


def root_cause_hypothesis(incident: dict[str, Any]) -> str:
    fallback = (
        f"Request pressure likely exhausted a shared backend resource for "
        f"{incident['service']} in {incident['region']}, causing "
        f"'{incident['error']}'."
    )

    if not LLM:
        return fallback

    prompt = f"""
Write exactly one sentence.
Use only the incident data below.
Do not invent facts.
Do not include labels, bullets, or markdown.

Incident:
{json.dumps(incident)}
"""
    try:
        text = LLM.invoke(prompt).content.strip()
        return text.rstrip(".") + "."
    except Exception:
        return fallback


def build_root_cause_text(incident: dict[str, Any]) -> str:
    hypothesis = root_cause_hypothesis(incident)
    evidence = [
        (
            f"- affected_users={incident['affected_users']}, which shows "
            f"material impact rather than an isolated user complaint."
        ),
        (
            f"- error='{incident['error']}', which directly indicates the "
            f"failing component or failure mode."
        ),
        (
            f"- region='{incident['region']}', which suggests the blast "
            f"radius is concentrated in that deployment region."
        ),
    ]
    return "Most likely cause: " + hypothesis + "\nEvidence:\n" + "\n".join(
        evidence
    )


def build_remediation_text(incident: dict[str, Any]) -> str:
    service = incident["service"]
    error = incident["error"].lower()
    region = incident["region"]

    if service == "payment-gateway" and "connection pool" in error:
        steps = [
            (
                "Step 1 [5 min]: Check pg-pool connection saturation on "
                f"{region} primary — run: psql -c "
                "\"SELECT count(*) FROM pg_stat_activity;\""
            ),
            (
                "Step 2 [10 min]: Identify and terminate stale sessions "
                "blocking free connections — run: psql -c "
                "\"SELECT pid, state FROM pg_stat_activity WHERE state "
                "!= 'active';\""
            ),
            (
                "Step 3 [15 min]: Restart only the payment-gateway pods "
                "with the highest DB wait time to recycle pooled "
                "connections safely."
            ),
            (
                "Step 4 [20 min]: Temporarily raise the pool cap and "
                "application timeout for the ap-south-1 deployment using "
                "the emergency config profile."
            ),
            (
                "Step 5 [15 min]: Validate recovery by checking 5xx rate, "
                "checkout latency, and fresh DB connection counts for the "
                "next 10 minutes."
            ),
        ]
        return "\n".join(steps)

    steps = [
        (
            "Step 1 [5 min]: Capture the failing service logs and current "
            "deployment version from the affected region."
        ),
        (
            "Step 2 [10 min]: Pause further releases or automation jobs "
            "touching the impacted service."
        ),
        (
            "Step 3 [15 min]: Roll back the most recent config or code "
            "change associated with the incident window."
        ),
        (
            "Step 4 [20 min]: Re-run a targeted health check against the "
            "failing user path and confirm error reduction."
        ),
        (
            "Step 5 [15 min]: Monitor service metrics for 10 minutes and "
            "close the incident only after stability is sustained."
        ),
    ]
    return "\n".join(steps)


def root_cause_node(state: EscalationState) -> dict[str, Any]:
    incident = {
        "incident_id": state["incident_id"],
        "severity": state["severity"],
        "service": state["service"],
        "error": state["error"],
        "affected_users": state["affected_users"],
        "region": state["region"],
    }
    return {"root_cause": build_root_cause_text(incident)}


def remediation_node(state: EscalationState) -> dict[str, Any]:
    incident = {
        "incident_id": state["incident_id"],
        "severity": state["severity"],
        "service": state["service"],
        "error": state["error"],
        "affected_users": state["affected_users"],
        "region": state["region"],
    }
    return {"remediation": build_remediation_text(incident)}


def pagerduty_node(state: EscalationState) -> dict[str, Any]:
    assignee = TEAM_ROSTER[state.get("critical_count", 0) % len(TEAM_ROSTER)]
    alert = (
        "🚨 PAGERDUTY ALERT | "
        f"Incident: {state['incident_id']} | "
        "Severity: CRITICAL | "
        f"Service: {state['service']} | "
        f"Assigned to: {assignee} | "
        f"Runbook: https://runbooks.internal/{state['service']}/p0"
    )
    return {"pagerduty_alert": alert}


def build_escalation_app():
    graph = StateGraph(EscalationState)
    graph.add_node("root_cause_node", root_cause_node)
    graph.add_node("remediation_node", remediation_node)
    graph.add_node("pagerduty_node", pagerduty_node)
    graph.add_edge(START, "root_cause_node")
    graph.add_edge("root_cause_node", "remediation_node")
    graph.add_edge("remediation_node", "pagerduty_node")
    graph.add_edge("pagerduty_node", END)
    return graph.compile()


ESCALATION_APP = build_escalation_app()


def classifier_node(state: MainState) -> dict[str, Any]:
    incident = state["raw_incident"]
    incident_id = incident["incident_id"]
    severity = incident["severity"].lower()
    service = incident["service"]
    error = incident["error"]
    affected_users = int(incident["affected_users"])
    region = incident["region"]

    prior_history = state.get("incident_history", [])
    cross_reference = build_cross_reference(prior_history, service)
    summary = (
        f"{incident_id}: {service} — {error} "
        f"({affected_users} users affected)"
    )

    update: dict[str, Any] = {
        "incident_id": incident_id,
        "severity": severity,
        "service": service,
        "error": error,
        "affected_users": affected_users,
        "region": region,
        "incident_history": [summary],
        "cross_reference": cross_reference,
    }

    if severity == "critical":
        escalation_result = ESCALATION_APP.invoke(
            {
                "incident_id": incident_id,
                "severity": severity,
                "service": service,
                "error": error,
                "affected_users": affected_users,
                "region": region,
                "critical_count": state.get("critical_count", 0),
            }
        )
        update["current_output"] = [
            escalation_result["root_cause"],
            escalation_result["remediation"],
            escalation_result["pagerduty_alert"],
        ]
        update["current_eta"] = ""
        update["next_route"] = "notification"
        update["critical_count"] = state.get("critical_count", 0) + 1
        return update

    if severity == "high":
        update["next_route"] = "response"
        return update

    update["next_route"] = "log"
    return update


def response_node(state: MainState) -> dict[str, Any]:
    incident = {
        "incident_id": state["incident_id"],
        "severity": state["severity"],
        "service": state["service"],
        "error": state["error"],
        "affected_users": state["affected_users"],
        "region": state["region"],
    }
    plan, eta = build_high_response(incident, state.get("cross_reference", ""))
    return {"current_output": [plan], "current_eta": eta}


def log_node(state: MainState) -> dict[str, Any]:
    message = (
        f"{state['incident_id']} logged for monitoring. "
        "No immediate action required. "
        f"Added to watch list: {state['service']} "
        f"{watch_phrase(state['error'])}."
    )
    if state.get("cross_reference"):
        message += f" {state['cross_reference']}"
    return {"current_output": [message], "current_eta": ""}


def notification_node(state: MainState) -> dict[str, Any]:
    if state["severity"] == "critical":
        sentence_1 = (
            f"Incident {state['incident_id']} for {state['service']} was "
            "escalated through the critical triage sub-graph and a "
            "PagerDuty alert was issued."
        )
    elif state["severity"] == "high":
        sentence_1 = (
            f"Incident {state['incident_id']} for {state['service']} "
            "received a direct three-step response plan with an "
            f"estimated time to resolution of {state['current_eta']}."
        )
    else:
        sentence_1 = (
            f"Incident {state['incident_id']} for {state['service']} was "
            "logged for monitoring and added to the watch list."
        )

    if state.get("cross_reference"):
        sentence_2 = (
            f"The agent also cross-referenced earlier shift memory and "
            f"found a related {state['service']} incident."
        )
    else:
        sentence_2 = (
            "The shift memory has been updated so future incidents can be "
            "cross-referenced."
        )

    notification = f"{sentence_1} {sentence_2}"
    return {"current_output": state["current_output"] + [notification]}


def route_from_classifier(state: MainState) -> str:
    return state["next_route"]


def build_main_app():
    graph = StateGraph(MainState)
    graph.add_node("classifier_node", classifier_node)
    graph.add_node("response_node", response_node)
    graph.add_node("log_node", log_node)
    graph.add_node("notification_node", notification_node)

    graph.add_edge(START, "classifier_node")
    graph.add_conditional_edges(
        "classifier_node",
        route_from_classifier,
        {
            "response": "response_node",
            "log": "log_node",
            "notification": "notification_node",
        },
    )
    graph.add_edge("response_node", "notification_node")
    graph.add_edge("log_node", "notification_node")
    graph.add_edge("notification_node", END)

    return graph.compile(checkpointer=MemorySaver())


def print_memory_trace(app, config: dict[str, Any]) -> None:
    snapshot = app.get_state(config)
    history = snapshot.values.get("incident_history", [])
    print("incident_history =", history)


def run_file(app, path: str, config: dict[str, Any]) -> None:
    incident = load_incident(path)
    result = app.invoke({"raw_incident": incident}, config=config)

    print(f"\n=== {path} ===")
    for line in result["current_output"]:
        print(line)
    print_memory_trace(app, config)


def main() -> None:
    app = build_main_app()
    from IPython.display import Image, display
    png_bytes = app.get_graph().draw_mermaid_png()

    with open("logic.png", "wb") as f:
        f.write(png_bytes)
    config = {"configurable": {"thread_id": THREAD_ID}}

    for filename in [
        "incident_01.json",
        "incident_02.json",
        "incident_03.json",
    ]:
        run_file(app, filename, config)


if __name__ == "__main__":
    main()
