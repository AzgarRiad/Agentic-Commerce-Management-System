"""
Chat loop for ACMS using the OpenAI SDK.

Works with Gemini, OpenRouter and Groq. If the model requests a tool call,
the tool is executed locally and the result is sent back to the model.
This repeats until the model returns a final text response.
"""

import inspect
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from app.agent.conversation_store import load_conversation, save_conversation
from app.agent.tools import AVAILABLE_TOOLS

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# ============================================================
# PROVIDERS
# ============================================================

PROVIDERS = {
    "gemini": {
        "api_key_env": "GENAI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3.5-flash-lite",
        "parallel_tool_calls": True,
    },
    "openrouter": {
        "api_key_env": "OPENROUTER_API_KEY_1ST",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "nvidia/nemotron-3.5-super-vl:free",
        "parallel_tool_calls": True,
    },
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "openai/gpt-oss-120b",
        "parallel_tool_calls": False,
    },
}

PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # gemini, openrouter or groq
config = PROVIDERS[PROVIDER]
MODEL_NAME = config["default_model"]


def _get_client():
    """Create the client only when a chat request needs it."""
    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        raise RuntimeError(f"{config['api_key_env']} is not configured")
    return OpenAI(base_url=config["base_url"], api_key=api_key)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
# Role
You are a professional, friendly, and concise sales assistant for an online clothing store. All prices are in BDT.

# Product Information
- Use product tools to retrieve current prices, stock, sizes, and details.
- Never invent product information or availability.
- If get_product_info doesn't find a product, call get_products to find similar available products.
- Don't reveal stock quantities.
- Only describe verified clothing features, materials, sizes, and fits.

# Sales Guidelines
- Help customers find suitable clothing based on their preferences and budget.
- Ask for measurements when needed to help with sizing. Never guarantee a perfect fit.
- Suggest available alternatives when a requested product, size, or color is unavailable.
- Don't mention ordering until the customer expresses purchase interest.

# Order Policy
Before calling add_order, verify:
- Product and variant (size/color, if applicable)
- Quantity
- Customer name
- Customer phone number

- Customer information must be explicitly provided or retrieved from a trusted backend.
- Never invent or assume missing information.
- Ask only for missing information.
- Verify variant availability and never exceed available stock.
- Follow the store's confirmation policy.
- Only confirm successful orders when the tool confirms success. Never fabricate order IDs.

# Tool Usage
- Use tools for database lookups and modifications.
- If a tool fails, explain the problem. Never claim an unsuccessful operation succeeded.
"""


# ============================================================
# TOOLS
# ============================================================

# Add or remove tools here.
TOOL_NAMES = ["get_product_info", "add_order", "get_products"]
TOOL_FUNCTIONS = {name: AVAILABLE_TOOLS[name] for name in TOOL_NAMES}

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _tool_schema(name, function):
    """Build an OpenAI tool definition from a function's signature and docstring."""
    params = inspect.signature(function).parameters
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": inspect.getdoc(function) or name,
            "parameters": {
                "type": "object",
                "properties": {
                    p.name: {"type": JSON_TYPES.get(p.annotation, "string")}
                    for p in params.values()
                },
                "required": [
                    p.name for p in params.values()
                    if p.default is inspect.Parameter.empty
                ],
            },
        },
    }


TOOLS = [_tool_schema(name, fn) for name, fn in TOOL_FUNCTIONS.items()]


# ============================================================
# CHAT LOOP
# ============================================================

def gemini_chat(user_input: str) -> str:

    client = _get_client()

    # The system prompt is added every time and never saved.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += load_conversation()
    messages.append({"role": "user", "content": user_input})

    for _ in range(8):

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS,
            parallel_tool_calls=config["parallel_tool_calls"],
        )

        if not response.choices:
            raise RuntimeError("The chat provider returned an empty response")

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if message.tool_calls:

            for call in message.tool_calls:

                tool_function = TOOL_FUNCTIONS.get(call.function.name)

                if tool_function is None:
                    result = {"error": f"Unknown tool '{call.function.name}'"}
                else:
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        result = tool_function(**arguments)
                    except Exception as exc:
                        result = {"error": str(exc)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps({"result": result}, default=str),
                })

            continue

        save_conversation(messages[1:])

        return message.content or "I couldn't generate a response. Please try again."

    raise RuntimeError("The chat provider exceeded the tool-call limit")