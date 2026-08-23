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
