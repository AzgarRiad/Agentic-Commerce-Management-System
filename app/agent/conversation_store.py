import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONVERSATION_FILE = BASE_DIR / "data" / "conversation.json"


def load_conversation() -> list:
    """Load the saved messages, or an empty list if there are none."""
    try:
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    # An old Gemini-format file (messages with "parts") can't be used. Start fresh.
    if not isinstance(data, list) or any("parts" in m for m in data):
        return []

    return data


def save_conversation(messages: list) -> None:
    """Save the messages to disk."""
    CONVERSATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)