# Health Coach

A multi-agent wellness assistant built for AI-103 at Chitkara University,
September 2026.

## Team

| Name | Roll number |
|---|---|
| Jugadveer | 2410992531 |
| Ashnoor | 2410992511 |
| Kanan | 2410992532 |
| Husan | 2410992611 |
| Kishika | 2410992540 |

## The problem

Everyone already tracks health data. The trouble is that each app tracks
one thing and then advises you on that one thing. Your calorie app has no
idea how you slept. Your sleep app has never heard of your water intake.
So when you actually feel unwell, nothing joins the dots and the advice
stays vague.

An afternoon headache is rarely caused by one thing. It usually sits
somewhere between short sleep, not enough water and a skipped lunch.
Answering it properly means those three things have to compare notes.

## What we built

You talk to one Coach agent. Behind it sit twelve more.

Eight of them own data. Four hold nothing at all and work purely by
asking the others.

| Agent | What it owns | Kind |
|---|---|---|
| `coach` | Conversation, safety, routing | orchestrator |
| `hydration` | Water intake | specialist |
| `nutrition` | Meals and calories | specialist |
| `sleep` | Sleep hours and sleep debt | specialist |
| `activity` | Steps and exercise minutes | specialist |
| `vitals` | Weight, BMI, blood pressure, heart rate | specialist |
| `mood` | Daily wellbeing score | specialist |
| `medication` | Whether it was taken, never the dose | specialist |
| `symptom` | Correlates a symptom against everything else | specialist |
| `insights` | Finds patterns across domains | meta |
| `progress` | Streaks, daily goals, achievements | meta |
| `assessment` | Energy needs and whether intake matches them | meta |
| `report` | A summary to hand a clinician | meta |

One rule makes this a real multi-agent system rather than one program
with twelve functions in it: **no agent reads another agent's data
directly.** If the symptom agent needs your sleep, it asks the sleep
agent, and the message bus records the exchange.

### The scenario worth watching

```
You:   I keep getting a headache in the afternoon.

  coach    -> symptom      routes the question
  symptom  -> hydration    2 of 8 glasses today
  symptom  -> nutrition    1 meal, 200 kcal so far
  symptom  -> sleep        5.7h average, 16.2h of debt
  symptom  -> activity     4861 steps, 140 active minutes this week
  symptom  -> vitals       71.5kg, BMI 23.3
  symptom  -> mood         3.6/10 average, falling
  symptom  -> medication   Vitamin D still pending

Coach: Looking at what you've logged, I can see a sleep debt of about
       16 hours, low fluid intake, a low calorie intake so far and a
       low mood score. Those are all common contributors to how you're
       feeling. This is general information, not a diagnosis. If it
       persists or worsens, please see a doctor.
```

One question, eight agents, one joined-up answer. That collaboration is
the project. The tracking is just what makes it possible.

### Things it does that a single tracker cannot

The `assessment` agent estimates what you need in a day from your height,
weight, age and activity level, then checks what you actually logged
against it. If your intake comes out far below your requirement it says
the day looks part-logged rather than telling you you are starving,
because someone who forgot to log lunch is far more common than someone
who genuinely ate 200 calories.

The `nutrition` agent holds a conversation. Say "I ate a burger" and it
asks which one, because the honest answer is anywhere between 330 and 690
calories and guessing would make the whole day meaningless. It also reads
a photo of your meal, though it proposes what it sees and waits for you
to confirm rather than logging it straight away.

### What it will not do

It does not diagnose anything, and it does not go near medication or
doses. Ask it to and it refuses. Anything that sounds like an emergency
is escalated before any other code runs. The reasoning behind all of that
is in [docs/RESPONSIBLE-AI.md](docs/RESPONSIBLE-AI.md).

## How it fits together

```
                          +--------------+
          voice / text    |              |  safety gate, always first
    you  ---------------->|    Coach     |  intent and entity parsing
                          |              |  routing and delegation
                          +------+-------+
                                 |
                          +------v-------+
                          |  Agent Bus   |  every message between agents
                          |  and trace   |  is recorded here
                          +------+-------+
      +----------+---------+-----+-----+---------+----------+
      v          v         v           v         v          v
 +---------++---------++-------++--------++--------++----------+
 |Hydration||Nutrition|| Sleep ||Activity|| Vitals ||   Mood   |
 +----+----++----+----++---+---++---+----++---+----++----+-----+
      |          |         |        |         |          |
      |    +------------+  |   +---------+    |          |
      |    | Medication |  |   | Symptom |<---+----------+
      |    +-----+------+  |   +----+----+  asks every peer
      +----------+---------+--------+
                           v
                    +-------------+   +----------+ +----------+ +--------+
                    |   SQLite    |   | Insights | | Progress | | Report |
                    +-------------+   +----------+ +----------+ +--------+
                                       these hold no data and query peers
```

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Accounts

Everyone signs in. A health record belongs to one person, so the app was
not much use while it held a single anonymous pile of data that anyone
opening the page could read.

Passwords are hashed with scrypt from the standard library, which is
deliberately slow and memory hard, with a fresh salt per password so one
cracked hash tells you nothing about the next. The session is a signed
cookie carrying only a user id and an expiry, marked httponly so page
scripts cannot read it and samesite so another site cannot ride on it.
Nothing about a password is stored, logged or sent anywhere.

Every table carries the owner. Rather than trusting ourselves to
remember that in each new query, `tests/test_isolation.py` reads every
SQL string in the codebase and fails the build if one touches personal
data without saying whose. `tests/test_auth.py` walks the route table and
fails if any endpoint answers without a session. Both catch the mistake
at the moment it is written rather than after someone sees the wrong
person's numbers.

## Built with

Python 3.11, FastAPI and Uvicorn. SQLite through the standard library
with no ORM, or Postgres when `DATABASE_URL` is set: identical SQL, one
small shim for the two things the dialects spell differently. The front
end is plain HTML, CSS and JavaScript with no build step, which keeps
every line readable. Tests are pytest.

### Azure services

| Service | Doing what |
|---|---|
| Azure OpenAI, via AI Foundry | Agent reasoning, health answers, meal conversations |
| Azure OpenAI vision | Reading a meal from a photograph |
| Azure AI Speech | Speech to text in, text to speech out |
| Azure AI Content Safety | A third guardrail layer on free text |
| Azure AI Search | RAG index, wired but not provisioned |

### AI-103 ideas we used

Multi-agent systems, with thirteen agents that each do one job.
Cross-agent communication through a bus that records every exchange.
Orchestration, where the Coach routes and synthesises rather than
answering. RAG for grounded health information. Tools, in that every
agent exposes `report()` for its peers to call. Intent recognition that
runs before any model call. Speech and vision for multimodal input.
Multi-turn dialogue, where the model decides a meal is too vague to log
and asks. And responsible AI throughout, which shaped more of the design
than anything else on this list.

## Running it

```bash
git clone https://github.com/Jugadveer/Ai-103.git
cd Ai-103
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m scripts.seed
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> and create an account, or sign in as
`demo@local` / `demo1234`, which is what `python -m scripts.seed` makes.

Ticking "start with a month of sample data" on the way in fills a new
account with the same demo month, so the charts have something to show
from the first screen.

It runs with no Azure credentials at all. Leave `MOCK_MODE=true` and it
falls back to local rules and a local knowledge file. Fill in the keys and
set `MOCK_MODE=false` to bring the live services in.

`python -m scripts.seed` makes a local account and writes a month of
history into it, so the charts and streaks have something to show. The
data is deliberately shaped rather than random: sleep declines across the
month, mood declines with it, and three days are missing so the gaps in
the charts are real.

Deploying it is its own subject, covered in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The short version: set
`DATABASE_URL` to a Postgres connection string and `SECRET_KEY` to a
random value. Without a database a hosted deployment loses accounts as
well as logs, and the app says so in a banner rather than letting you
find out.

## Tests

```bash
python -m pytest tests/ -q
```

434 tests, all passing, in about two minutes. No Azure needed: the
suite runs entirely offline, against a throwaway SQLite file.

| Suite | Tests | What it covers |
|---|---|---|
| `test_triage.py` | 66 | The safety layer that generalises, and its limits |
| `test_nutrition.py` | 41 | Food recognition and the meal conversation |
| `test_nlu.py` | 41 | Intent classification and entity extraction |
| `test_knowledge.py` | 41 | Health answering and its guardrail |
| `test_assessment.py` | 35 | Energy estimates and the limits it keeps to |
| `test_progress.py` | 34 | Streaks, achievements, the seeded dataset |
| `test_safety.py` | 32 | Escalation, refusal, and not over-blocking |
| `test_agents.py` | 30 | Each agent's calculations on its own |
| `test_validation.py` | 24 | Plausible ranges for every health value |
| `test_auth.py` | 24 | Sign up, sign in, sessions, and the gate |
| `test_crossagent.py` | 19 | Agents talking to each other, and the trace |
| `test_api.py` | 16 | Every endpoint, plus deployment readiness |
| `test_live_model.py` | 14 | The paths that only run when Azure is configured |
| `test_postgres.py` | 11 | That the same SQL is legal on both backends |
| `test_isolation.py` | 6 | That one account cannot see another's data |

Writing them was worth it. They caught a stroke red flag that missed
"my face is drooping" because the phrase assumed adjacent words, a
guardrail that was silently discarding good answers for containing the
words "you have", and a cascade where one question was making nineteen
agent calls instead of eight. None of those were visible by reading the
code. [docs/TESTING.md](docs/TESTING.md) lists the rest.

Two of them are less about finding a bug than about preventing a kind of
one. The isolation test reads the SQL and the auth test reads the route
table, so the mistakes they guard against fail the build the day someone
makes them.

## What it cannot do

Worth being plain about, because several of these are the reason features
are shaped the way they are.

The app measures nothing. There is no wearable and no sensor anywhere in
it. Heart rate, blood pressure, steps, weight and mood are all typed in
by you. BMI and energy needs are calculated, but only from numbers you
supplied.

Mood in particular cannot be sensed, so we ask for it on a scale with
worded anchors instead of pretending to infer it.

Calorie figures are estimates from typical serving sizes, not weighed
measurements, and the interface says so every time it shows one. Energy
needs come from the Mifflin-St Jeor equation, which is routinely out by
about ten percent and worse at the extremes of body composition.

There is no password reset and no email verification, so an account is
only as recoverable as the password you remember. The knowledge file is
small and needs proper clinical sourcing. A web app also cannot listen
for a wake word in the background, so voice still starts on a tap.

## Where we would take it next

Wearable integration so activity stops being self-reported. A knowledge
base reviewed by an actual clinician. Password reset and email
verification, and encryption of the stored records rather than only the
connection to them. Trend detection across months rather than days.
Regional language support through Azure AI Translator.

## Acknowledgements

- Azure AI services documentation, Microsoft
- FastAPI, Uvicorn, Pydantic and pytest, all open source
- Calorie reference figures from public nutrition labels and standard
  portion tables. Approximate typical servings, labelled as estimates
  throughout
- Resting metabolic rate from the Mifflin-St Jeor equation, a published
  standard, used as an estimate with a stated margin and never as a
  measurement
- Health knowledge base content still needs replacing with cited sources
- **AI-assisted development tools** were used during implementation, to
  help work through code and debugging. All code in this repository is
  understood by the team, and every part of it can be explained on
  request.

---

This is a student project. It is not a medical device and must not be
used for medical decisions.
