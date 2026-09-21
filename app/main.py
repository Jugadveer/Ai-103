"""
FastAPI entry point.

Run it:  uvicorn app.main:app --reload
Open  :  http://127.0.0.1:8000
"""
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.agents.activity import ActivityAgent
from app.agents.assessment import AssessmentAgent
from app.agents.bus import AgentBus
from app.agents.coach import CoachAgent
from app.agents.hydration import HydrationAgent
from app.agents.insights import InsightsAgent
from app.agents.medication import MedicationAgent
from app.agents.mood import MoodAgent
from app.agents.nutrition import NutritionAgent
from app.agents.progress import ProgressAgent
from app.agents.report import ReportAgent
from app.agents.sleep import SleepAgent
from app.agents.symptom import SymptomAgent
from app.agents.vitals import VitalsAgent
from app.core import logging as log
from app.core.errors import ValidationError
from app.core.validation import check_number
from app.services import llm as speech_llm
from app.services import speech
from app.store import db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: make sure the database and its tables exist."""
    db.init_db()

    # A fresh deployment should not greet a tester with an empty app. This
    # only fires when nothing has ever been logged, so a host with a real
    # disk seeds once and never touches the data again.
    if config.SEED_ON_EMPTY:
        from scripts.seed import is_empty, seed_demo_data
        if is_empty():
            seed_demo_data()
            log.info("seeded_on_empty")

    log.info("startup", mock_mode=config.MOCK_MODE,
             agents=len(bus.agents),
             storage="persistent" if config.STORAGE_PERSISTENT else "ephemeral")
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
    ProgressAgent,     # ---- meta-agents, hold no data ----
    AssessmentAgent,
    InsightsAgent,
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


# Styles, script and icons. Mounted under /static so it cannot shadow /api.
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    """
    Served from the root on purpose: a service worker can only control the
    paths at or below its own URL, so one at /static/sw.js could not manage
    the app shell.
    """
    return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_mode": config.MOCK_MODE,
        "agents": list(bus.agents),
        # Honest about the host. On a serverless platform the container is
        # discarded between requests, so anything saved may not survive.
        "storage": "persistent" if config.STORAGE_PERSISTENT else "ephemeral",
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


@app.get("/api/history")
def history(days: int = 14):
    """Per-day series for every tracked metric, gaps preserved as null."""
    days = max(3, min(90, days))
    return db.all_series(days)


class ProfileEntry(BaseModel):
    age: int | None = None
    sex: str | None = None
    activity_level: str | None = None


@app.get("/api/profile")
def read_profile():
    from app.core.energy import ACTIVITY_LEVELS
    return {
        "profile": db.get_profile(),
        "activity_levels": {k: v[1] for k, v in ACTIVITY_LEVELS.items()},
    }


@app.post("/api/profile")
def save_profile(req: ProfileEntry):
    """Age, sex and activity level. Used only to estimate energy needs."""
    from app.core.energy import ACTIVITY_LEVELS
    errors = []
    if req.age is not None:
        try:
            db.set_profile("age", int(check_number("age", req.age)))
        except ValidationError as exc:
            errors.append(exc.user_message)
    if req.sex:
        db.set_profile("sex", req.sex.lower()[:12])
    if req.activity_level:
        if req.activity_level in ACTIVITY_LEVELS:
            db.set_profile("activity_level", req.activity_level)
        else:
            errors.append("That is not one of the activity levels.")
    return {"ok": not errors, "errors": errors, "profile": db.get_profile()}


@app.get("/api/assessment")
def assessment():
    """The whole-picture review, including the energy calculation."""
    bus.reset_trace()
    reply = bus.get("assessment").safe_handle("review")
    return {"text": reply.text, "data": reply.data, "trace": bus.trace}


@app.get("/api/progress")
def progress():
    """Daily goal rings, streaks, achievements and level."""
    return bus.get("progress").safe_report()


class QuickLog(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    value: float | None = None


QUICK_ACTIONS = {
    "water":  lambda v: db.add_water(v or 1),
    "sleep":  lambda v: db.add_sleep(v or 7),
    "steps":  lambda v: db.add_activity("steps", steps=v or 1000),
    "active": lambda v: db.add_activity("exercise", minutes=v or 15),
    "meal":   lambda v: db.add_meal("quick entry", v or 400),
    "mood":   lambda v: db.add_mood(v or 5),
}


@app.post("/api/quicklog")
def quicklog(req: QuickLog):
    """
    One-tap logging from the Today screen.

    Goes through the same validated writers the conversation uses, so an
    out-of-range value is refused here exactly as it would be in chat.
    """
    action = QUICK_ACTIONS.get(req.action)
    if action is None:
        return Response(status_code=404)
    try:
        action(req.value)
    except ValidationError as exc:
        return {"ok": False, "message": exc.user_message}
    return {"ok": True, "action": req.action}


class PhotoRequest(BaseModel):
    # A data URL from the browser. Capped so a huge upload cannot be used
    # to run up the Azure bill or exhaust memory.
    image: str = Field(min_length=32, max_length=8_000_000)


@app.post("/api/photo")
def photo(req: PhotoRequest):
    """
    Log a meal from a photograph.

    Azure OpenAI vision names what is on the plate, then the nutrition
    agent resolves it through exactly the same path as typed text, so a
    photo and a sentence get the same validation and the same follow-up
    questions.
    """
    if not req.image.startswith("data:image/"):
        return {"ok": False, "message": "That did not look like an image."}

    described = speech_llm.describe_food_photo(req.image)
    if not described:
        return {"ok": False,
                "message": "I could not read that photo. Azure vision may be "
                           "unavailable, or there may be no food in it. Tell "
                           "me what you ate instead."}

    bus.reset_trace()
    reply = bus.get("nutrition").safe_handle_photo(described)
    return {
        "ok": True,
        "saw": described,
        "reply": reply.text,
        "data": reply.data,
        "trace": bus.trace,
    }


class VitalsEntry(BaseModel):
    """
    Self-reported body measurements. The app measures none of these; they
    come from a scale, a tape measure, or a home blood-pressure monitor.
    """
    height_cm: float | None = None
    weight_kg: float | None = None
    heart_rate: float | None = None
    systolic: float | None = None
    diastolic: float | None = None


@app.post("/api/vitals")
def save_vitals(req: VitalsEntry):
    saved, errors = [], []

    def attempt(metric, value, secondary=None):
        if value is None:
            return
        try:
            db.add_vital(metric, value, secondary=secondary)
            saved.append(metric)
        except ValidationError as exc:
            errors.append(exc.user_message)

    attempt("height_cm", req.height_cm)
    attempt("weight_kg", req.weight_kg)
    attempt("heart_rate", req.heart_rate)
    if req.systolic is not None and req.diastolic is not None:
        attempt("systolic", req.systolic, secondary=req.diastolic)

    return {"ok": not errors, "saved": saved, "errors": errors,
            "vitals": bus.get("vitals").safe_report()}


@app.post("/api/seed")
def seed():
    """Load the demo dataset. Development helper, not part of the product."""
    from scripts.seed import seed_demo_data
    seed_demo_data()
    return {"status": "seeded"}
