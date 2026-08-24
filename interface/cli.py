import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.core.agent import handle_turn

session_id = "cli-session"

print("CometChat CLI. Type 'exit' to quit.")
while True:
    user_input = input("You: ").strip()
    if user_input.lower() in {"exit", "quit"}:
        print("Goodbye.")
        break
    result = handle_turn(session_id, user_input)
    print("\nAssistant:")
    print(result["answer"])
    if result.get("sources"):
        print("\nSources:")
        for source in result["sources"]:
            print(f"- {source['filename']}#{source['heading']}")
    else:
        print("\nSources: No sources")
    if result.get("handoff"):
        print("\nRecommending human handoff")
    print("\n---")
