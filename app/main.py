"""
FastAPI entry point.

Run it:  uvicorn app.main:app --reload
Open  :  http://127.0.0.1:8000
"""
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app import config
from app.agents.activity import ActivityAgent
from app.agents.bus import AgentBus
from app.agents.coach import CoachAgent
from app.agents.hydration import HydrationAgent
from app.agents.insights import InsightsAgent
from app.agents.medication import MedicationAgent
from app.agents.mood import MoodAgent
from app.agents.nutrition import NutritionAgent
from app.agents.report import ReportAgent
from app.agents.sleep import SleepAgent
from app.agents.symptom import SymptomAgent
from app.agents.vitals import VitalsAgent
from app.core import logging as log
from app.services import speech
from app.store import db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: make sure the database and its tables exist."""
    db.init_db()
    log.info("startup", mock_mode=config.MOCK_MODE, agents=len(bus.agents))
    yield


app = FastAPI(
    title="Health Coach - AI-103 Multi-Agent Project",
    lifespan=lifespan,
)

AGENT_CLASSES = (
    CoachAgent,        # orchestrator
    HydrationAgent,    # ---- data-holding specialists ----
    NutritionAgent,
    SleepAgent,
    ActivityAgent,
    VitalsAgent,
    MoodAgent,
    MedicationAgent,
    SymptomAgent,
    InsightsAgent,     # ---- meta-agents, hold no data ----
    ReportAgent,
)


def build_bus() -> AgentBus:
    """Construct the agent mesh. Shared by the API and the tests."""
    bus = AgentBus()
    for cls in AGENT_CLASSES:
        bus.register(cls())
    return bus


bus = build_bus()
WEB_DIR = pathlib.Path(__file__).parent / "web"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_mode": config.MOCK_MODE,
        "agents": list(bus.agents),
        "azure": {
            "openai": bool(config.AZURE_OPENAI_API_KEY),
            "search": bool(config.AZURE_SEARCH_API_KEY),
            "speech": bool(config.AZURE_SPEECH_KEY),
            "content_safety": bool(config.AZURE_CONTENT_SAFETY_KEY),
        },
    }


@app.get("/api/agents")
def agents():
    """Every registered agent and what it is responsible for."""
    return [
        {"name": name, "description": agent.description}
        for name, agent in bus.agents.items()
    ]


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Main endpoint. Returns the reply plus the full agent-to-agent trace."""
    bus.reset_trace()
    reply = bus.get("coach").safe_handle(req.message)
    return {
        "reply": reply.text,
        "agent": reply.agent,
        "data": reply.data,
        "trace": bus.trace,
        "disclaimer": config.DISCLAIMER,
    }


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


@app.post("/api/speak")
def speak(req: SpeakRequest):
    """
    Azure AI Speech text-to-speech. Returns WAV audio.

    A 503 here is not an error state - it tells the page that Speech is not
    configured, and the page falls back to the browser's own voice.
    """
    audio = speech.synthesize_bytes(req.text)
    if audio is None:
        return Response(status_code=503)
    return Response(content=audio, media_type="audio/wav")


@app.get("/api/dashboard")
def dashboard():
    """Every agent's current report - used by the UI panels."""
    return {name: agent.safe_report() for name, agent in bus.agents.items()}


@app.post("/api/seed")
def seed():
    """Load the demo dataset. Development helper, not part of the product."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    return {"status": "seeded"}
