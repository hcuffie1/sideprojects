"""Interactive multi-turn shopping assistant REPL."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import agent  # noqa: E402


def main():
    print("Shopping Assistant (type 'quit' or 'exit' to stop)\n")
    state = {
        "conversation_history": [],
        "query": "",
        "parsed_constraints": [],
        "category": None,
        "candidate_products": [],
        "filtered_products": [],
        "constraint_violations": [],
        "ranked_products": [],
        "groundedness_annotations": [],
        "final_response": "",
        "agent_rationale": "",
        "trace_id": None,
        "eval_scores": None,
    }

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        state["query"] = query
        state = agent.invoke(state)
        print(f"\nAgent: {state['final_response']}\n")


if __name__ == "__main__":
    main()
