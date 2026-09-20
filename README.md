# Health Coach — A Multi-Agent Wellness Assistant

> **AI-103 Group Project · Chitkara University · September 2026**

<!-- TODO: fill in before submission -->
**Team:** _member 1, member 2, member 3, member 4, member 5_
**Group:** _group number_

---

## Problem statement

People already track health data — steps, meals, water, sleep — but each app
tracks one thing and advises on one thing. A calorie app knows nothing about
your sleep. A sleep app knows nothing about your hydration. So when someone
actually feels unwell, nothing connects the dots, and the advice stays generic.

Most everyday complaints — afternoon headaches, low energy, poor concentration —
are not single-cause problems. They sit at the intersection of sleep, hydration
and food. Answering them properly needs those domains to talk to each other.

## Solution overview

A team of specialist AI agents that **communicate with each other** to explain
how a person feels, using their own logged data.

The user talks (by voice or text) to a single **Coach** agent. Behind it sit
ten more: seven specialists that each own one domain, a Symptom agent, and
two meta-agents that hold no data of their own.

| Agent | Owns | Kind |
|---|---|---|
| `coach` | Conversation, safety, routing | orchestrator |
| `hydration` | Water intake | specialist |
| `nutrition` | Meals and calories | specialist |
| `sleep` | Sleep hours and debt | specialist |
| `activity` | Steps and exercise minutes | specialist |
| `vitals` | Weight, BMI, heart rate, blood pressure | specialist |
| `mood` | Daily wellbeing score and trend | specialist |
| `medication` | Adherence tracking (never dosing) | specialist |
| `symptom` | Symptom correlation + RAG | specialist |
| `insights` | Cross-domain pattern detection | meta |
| `report` | Doctor-ready health summary | meta |

When the user reports a symptom, the Symptom agent doesn't answer alone: it
queries every data-holding agent, correlates what comes back, and explains
the likely contributing factors.

**The core scenario:**

```
User:  "I keep getting a headache in the afternoon."

  coach    -> symptom      (routes the question)
  symptom  -> hydration    (2 of 8 glasses today, shortfall 6)
  symptom  -> nutrition    (1 meal, 300 kcal so far)
  symptom  -> sleep        (7 nights, averaging 5.4h, 18.3h debt)
  symptom  -> activity     (2400 steps, 35 active minutes this week)
  symptom  -> vitals       (71.5kg, BMI 23.3, HR 86bpm)
  symptom  -> mood         (4.0/10 average, trend falling)
  symptom  -> medication   (Vitamin D pending today)

Coach: "Looking at what you've logged, I can see a sleep debt of about
        18.3 hours; low fluid intake — 2 of 8 glasses today; a low calorie
        intake so far; very little movement this week; a low mood score;
        medication not yet taken today. Those are all common contributors...
        This is general information, not a diagnosis. If it persists,
        worsens, or you're worried, please see a doctor."
```

One question, eight agents, one joined-up answer. **That collaboration is the
project** — not the tracking.

Two further agents build on the same mechanism: `insights` scans every domain
for cross-domain patterns, and `report` compiles a summary the user can hand
to a real clinician.

### What it deliberately does not do

It does **not** diagnose disease or recommend medication. It is a wellness
coach that shares general information and surfaces patterns in the user's own
data. Anything that looks urgent is escalated to emergency services
immediately, before any model call is made. See
[docs/RESPONSIBLE-AI.md](docs/RESPONSIBLE-AI.md).

## Solution architecture

```
                          ┌──────────────┐
          voice / text    │              │  · safety gate (first, always)
    user ────────────────►│ Coach agent  │  · intent + entity parsing
                          │              │  · routing and delegation
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │  Agent Bus   │  every agent-to-agent message
                          │  (+ trace)   │  is recorded here
                          └──────┬───────┘
     ┌───────────┬──────────┬────┴─────┬──────────┬───────────┐
     ▼           ▼          ▼          ▼          ▼           ▼
┌─────────┐ ┌─────────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│Hydration│ │Nutrition│ │ Sleep │ │Activity│ │ Vitals │ │   Mood   │
└────┬────┘ └────┬────┘ └───┬───┘ └───┬────┘ └───┬────┘ └────┬─────┘
     │           │          │         │          │           │
     │      ┌────────────┐  │    ┌─────────┐     │           │
     │      │ Medication │  │    │ Symptom │◄────┴───────────┘
     │      └─────┬──────┘  │    └────┬────┘   asks every peer
     └────────────┴─────────┴─────────┘
                            ▼
                     ┌─────────────┐        ┌──────────┐  ┌────────┐
                     │   SQLite    │        │ Insights │  │ Report │
                     └─────────────┘        └──────────┘  └────────┘
                                             meta-agents: hold no data,
                                             query every peer instead
```

The Symptom agent never reads another agent's table directly. It asks that
agent through the bus, and the bus records the exchange. Full detail in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| API | FastAPI + Uvicorn |
| Storage | SQLite (stdlib `sqlite3`, no ORM) |
| Frontend | Plain HTML/CSS/JS, no build step |
| Tests | pytest |

### Azure AI services

| Service | Used for |
|---|---|
| **Azure AI Foundry / Azure OpenAI** | Agent reasoning and response generation |
| **Azure AI Search** | RAG index over the curated health knowledge base |
| **Azure AI Speech** | Speech-to-text input and text-to-speech replies |
| **Azure AI Content Safety** | Responsible-AI guardrail on user input |

### AI-103 concepts applied

- **Multi-agent systems** — eleven agents with distinct responsibilities
- **Cross-agent communication** — a message bus with a full, inspectable trace
- **Agent orchestration** — the Coach routes, delegates and synthesises
- **RAG** — grounded answers from a curated knowledge base
- **Tools** — agents expose `report()` as a callable capability to peers
- **Intent recognition** — deterministic entity extraction before any model call
- **Speech / multimodal** — voice in, voice out
- **Responsible AI** — safety gate, scope limits, escalation, disclaimers

## Setup instructions

```bash
git clone <repo-url>
cd AI-103
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

The app runs **without any Azure credentials** — `MOCK_MODE=true` in `.env`
uses the local knowledge base and rule-based logic. Set `MOCK_MODE=false` and
fill in the Azure keys to enable the live services.

```bash
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>. Click **Load demo data** to populate a
week of realistic logs, then ask about a headache.

To load the demo dataset from the terminal instead:

```bash
python -m scripts.seed
```

## Testing and results

```bash
python -m pytest tests/ -q
```

**150 tests, all passing.** Full breakdown in [docs/TESTING.md](docs/TESTING.md).

| Suite | Tests | Covers |
|---|---|---|
| `test_validation.py` | 24 | Plausible-range bounds on every health value |
| `test_nlu.py` | 41 | Intent classification and entity extraction |
| `test_safety.py` | 29 | Emergency escalation, scope refusal, false positives |
| `test_agents.py` | 30 | Each agent's calculations in isolation |
| `test_crossagent.py` | 15 | Agent-to-agent communication and the trace |
| `test_api.py` | 11 | Every HTTP endpoint and input validation |

The safety tests are the most important ones in the project: they assert that
emergencies escalate, that diagnosis is refused, that ordinary messages are
*not* over-blocked, and that **zero** agent calls happen after a red flag.

## Known limitations

- Single-user; no authentication or multi-user accounts
- Knowledge base is small and must be replaced with properly cited sources
- Keyword-first intent routing, with the model only as fallback
- No wearable or device integration — all data is self-reported
- Not validated by any medical professional

## Future improvements

- Cited, clinician-reviewed knowledge base
- Wearable integration for automatic sleep and activity data
- Multi-user accounts with encrypted health records
- Longitudinal trend detection across weeks rather than days
- Regional language support via Azure AI Translator

## Acknowledgements

<!-- TODO: list every third-party resource before submission — this is a
     graded requirement -->

- Azure AI services documentation — Microsoft
- FastAPI, Uvicorn, Pydantic, pytest — open-source libraries
- Health knowledge base content — _replace placeholders with cited sources_

---

**Disclaimer:** This is a student project for a university course. It is not a
medical device and must not be used for medical decisions.
