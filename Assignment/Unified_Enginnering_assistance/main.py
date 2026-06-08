
# filename: main.py
from __future__ import annotations

from Multi_Agent_System_Engineering_Assignment.Assignment.Unified_Enginnering_assistance.agent import build_graph, run_turn


REQUIRED_TEST_QUERIES = [
    "What is the difference between microservices and a monolith?",
    "Which of our tasks are currently blocked?",
    "What have I asked you so far?",
    "Based on our conversation, are there DevOps best practices I should apply to the blocked tasks?",
]

OPTIONAL_FINISH_QUERY = "Thanks"


def print_turn(index: int, query: str, state: dict) -> None:
    print(f"\n--- Turn {index} ---")
    print(f"User: {query}")
    print(f"Route: {state['route']}")
    print(f"Assistant: {state['worker_result']}")


def run_required_demo() -> None:
    graph = build_graph()
    thread_id = "assignment-thread-001"

    print(f"Using thread_id: {thread_id}")

    for i, query in enumerate(REQUIRED_TEST_QUERIES, start=1):
        state = run_turn(graph, query, thread_id)
        print_turn(i, query, state)

    finish_state = run_turn(graph, OPTIONAL_FINISH_QUERY, thread_id)
    print_turn(len(REQUIRED_TEST_QUERIES) + 1, OPTIONAL_FINISH_QUERY, finish_state)


def interactive_chat() -> None:
    graph = build_graph()
    thread_id = "interactive-thread-001"

    print(f"Interactive mode started with thread_id: {thread_id}")
    while True:
        query = input("\nYou: ").strip()
        if not query:
            continue

        state = run_turn(graph, query, thread_id)
        print(f"Route: {state['route']}")
        print(f"Assistant: {state['worker_result']}")

        if state["route"] == "FINISH":
            break


if __name__ == "__main__":
    run_required_demo()
    # Uncomment this if you also want manual testing:
    # interactive_chat()
