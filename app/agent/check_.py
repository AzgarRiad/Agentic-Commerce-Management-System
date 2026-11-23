"""Quick manual test: run with `uv run python -m app.agent.check_`."""
from app.api.chat import gemini_chat


def main(user_input="What is the price of RTX 5070 ti?"):
    print(gemini_chat(user_input))


if __name__ == "__main__":
    main()
