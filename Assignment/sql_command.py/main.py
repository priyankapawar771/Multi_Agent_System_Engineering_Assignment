
import argparse

from dotenv import load_dotenv

from agent import SQLAnalyticsAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Natural-language SQL analytics agent with validation loop."
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Natural-language analytics question.",
    )
    parser.add_argument(
        "--db",
        default="project_analytics.db",
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the generation/validation trace.",
    )
    parser.add_argument(
        "--simulate-invalid-first-try",
        action="store_true",
        help="Force one invalid first attempt for README/demo purposes.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    question = args.question
    if not question:
        question = input("Enter your question: ").strip()

    agent = SQLAnalyticsAgent(db_path=args.db)
    response = agent.answer(
        question=question,
        verbose=args.verbose,
        simulate_invalid_first_try=args.simulate_invalid_first_try,
    )
    print(response)


if __name__ == "__main__":
    main()
