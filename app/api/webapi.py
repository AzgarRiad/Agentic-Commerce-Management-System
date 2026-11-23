"""FastAPI app exposing the chat agent over HTTP."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from fastapi.staticfiles import StaticFiles

from app.api.chat import gemini_chat
from app.api.dashboardapi import router as dashboard_router
from app.agent.competitor_price_search import router as competitor_router

app = FastAPI()
app.include_router(dashboard_router)
app.include_router(competitor_router)

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "acms-plain"          # admin dashboard at /
MESSENGER_DIR = ROOT_DIR / "messanger_demo"    # chat mock at /messenger

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

@app.get("/intro")
def chat_bot_demo():
    """Kept from the original code as a quick manual smoke-test endpoint
    (hardcoded message, GET so you can hit it from a browser)."""
    try:
        return {"reply": gemini_chat("Hey")}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.post("/chat")
def chat_bot(request: ChatRequest):
    """Real endpoint: POST {"message": "..."} and get the agent's reply.
    Added because a hardcoded GET endpoint isn't usable for a real chatbot."""
    try:
        return {"reply": gemini_chat(request.message)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Serve both frontends from the same origin as the API (order matters).
app.mount("/messenger", StaticFiles(directory=MESSENGER_DIR, html=True), name="messenger")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
