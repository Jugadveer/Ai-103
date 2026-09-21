# Demo day

Everything in this file was run against the live deployment and the
replies are the ones it actually gave. Where a number appears, it is the
number the app produced.

- **Live:** <https://health-coach-1.vercel.app>
- **Demo account:** `demo@healthcoach.app` / `HealthCoach2026` (a seeded
  month of history)
- **Local:** `python -m scripts.seed` then `uvicorn app.main:app --reload`,
  sign in as `demo@local` / `demo1234`

## Which one to present from

**Present from localhost.** It is faster, nothing sleeps, and no network
sits between a click and the answer. Have the live URL in a second tab
so you can show it is genuinely deployed and that a second person can
sign in and see their own separate data.

Before you record or present:

1. Sign in on both, so no password prompt interrupts you
2. On **My body**, save height 175, weight 70, age 21, activity *light*.
   Without it the Full check-up asks questions instead of showing numbers
3. On **For my doctor**, press **Build it** once so the last shot is ready
4. Allow the microphone and say one test sentence
5. Close other tabs. The tab bar is in the recording

---

## The demo, in order

Six beats, about six minutes. Beat 6 is the one to drop if you are behind.

### 1. It is thirteen agents, not one chatbot (45s)

Start on **Today**. Point at the five rings and the numbers strip.

> Everything here was entered by the user. There is no wearable and no
> sensor anywhere in this project, and we say so on the screen rather
> than implying otherwise.

Click **How it works** and scroll the register of thirteen.

### 2. The cross-agent moment (60s)

This is the project. On **Talk to it**, type:

```
I keep getting a headache in the afternoon
```

The reply names the contributing factors from the user's own data, then
expand **+ 8 agent calls** underneath it. Verified trace:

```
coach    -> symptom
symptom  -> hydration      symptom -> nutrition
symptom  -> sleep          symptom -> activity
symptom  -> vitals         symptom -> mood
symptom  -> medication
```

> One question, eight agents. The symptom agent holds nothing but the
> symptom itself. It cannot read anyone else's table, so it asks, and the
> bus records every exchange. That list is generated, not written by us.

### 3. It asks before it guesses (60s)

```
I ate a burger from McDonald's
```
> burger (350 kcal), 350 kcal so far. Was it a regular burger or a
> different size/type?

```
a Big Mac
```
> big mac (563 kcal), 563 kcal so far. Anything to drink or any sides
> with that?

```
a medium coke, that's all
```
> Logged big mac (563 kcal), medium coke (210 kcal). That is 773 kcal,
> putting you at 973 for the day. These are estimates from typical
> servings.

> A burger is anywhere between 330 and 690 calories. Logging a guess
> would make the whole day meaningless, so the model decides when the
> description is too vague and asks. There is no list of vague foods
> anywhere in the code.

### 4. Safety, and what it costs (60s)

```
I have crushing chest pain and cannot breathe
```

Emergency numbers, immediately. Then show the trace: **zero agent calls.**

> The guardrail runs before routing, before any agent and before any
> model call. It is plain Python with no network dependency, so it cannot
> fail open when Azure is unreachable.

Then the harder one:

```
what is wrong with me, I have had a rash for two weeks
```

> It will not name a condition. It says which clinician and how soon.
> A flat refusal leaves a worried person exactly where they started, so
> the useful and honest answer is triage rather than diagnosis. Naming
> the thing is the part that needs a doctor, and that stays refused.

### 5. The doctor summary (45s)

**For my doctor** → already built. Five metric cards with thirty-day
sparklines, measurements, energy, medication, and a dated list of what
was reported.

> Every figure is self-reported. It says so on the page, and there is a
> plain-text version underneath because that is the form you can actually
> hand over.

### 6. Breadth, if time allows (30s)

**My trends** (thirty days, real gaps where nothing was logged) ·
**My streak** · **Full check-up** (maintenance calories, and note it
reads a very low intake as *incomplete logging* rather than starvation).

---

## What they will ask, and the answer

**"How do I know the agents really talk to each other, rather than one
function calling another?"**

No agent can read another's table. Every agent owns one, and the only
way to get a peer's figures is `bus.request`, which records the
exchange. The trace you just saw is that record. There is also a test,
`test_adding_an_agent_extends_correlation_automatically`, that registers
a brand new agent at runtime and asserts the symptom agent starts asking
it, with no change to the symptom agent.

**"What happens if I ask it something off-topic?"**

Try it. Ask for the capital of France or a Python function. It declines
both. That decision is made in the safety layer, which sees every
message, not by whichever agent the router picked.

**"Your safety check is a list of words. What about phrasings you did
not think of?"**

That was true and it was the weakness. "chest pain" was listed and
"heart attack" was not, so "I think I am having a heart attack" got a
correlation of the person's sleep and water intake. There are four
layers now: the list, the scope guard, a model triage that catches the
phrasings a list never will, and Azure Content Safety. The first two are
local and run first, so the app is exactly as safe with the network down
as with it up. The last two can only add a block, never lift one, which
is what makes it acceptable to let a model take part in a safety
decision at all.

**"Can it diagnose?"**

No, and we treat that as a design constraint rather than a disclaimer.
It never names a condition, never mentions a dose, and escalates
anything urgent before any other code runs. Model output is scanned
before it is shown: a referral that says "this sounds like eczema" is
discarded, because it is a diagnosis however short the word is. That
check looks for the act of naming rather than a list of diseases, since
a list of diseases can never be finished.

**"How do you know one person cannot see another's data?"**

Two tests. One walks every SQL string in the project and fails the build
if a query touching personal data has no owner condition. The other
walks FastAPI's route table and fails if any endpoint answers without a
session. Both catch the mistake the day it is written rather than after
someone sees the wrong person's numbers.

**"How is heart rate measured?"**

It is not. Nothing in this app is measured. Heart rate, blood pressure,
steps, weight and mood are all typed in, BMI and energy needs are
calculated from numbers the user supplied, and the interface says so on
every screen that shows one.

**"What did testing actually find?"**

Real bugs, and the honest list is in `docs/TESTING.md`. A stroke red flag
that missed "my face is drooping" because the phrase assumed adjacent
words. A guardrail silently discarding good answers for containing the
words "you have". One question making nineteen agent calls instead of
eight, then later seventeen instead of nine, because routing was spelled
as a data request. None of those were visible by reading the code.

**"Why Vercel and Postgres rather than a file?"**

A serverless host throws its filesystem away between requests. That was
survivable when the app was single user and the only casualty was demo
data. With accounts it is not: somebody creates a login, comes back, and
it does not exist. The same SQL runs on SQLite locally and Postgres when
deployed, and `/api/health` says which one it got.

---

## If something breaks

**Azure is down or slow.** Set `MOCK_MODE=true` and restart. Everything
except the model-driven food conversation and voice still works, all 413
tests still pass, and the fallback is a point in your favour: you
designed for the service being unavailable.

**The live site is slow to first load.** Serverless cold start. Load it
once before you begin.

**A reply takes five or six seconds.** That is Azure OpenAI in UAE North
being called from a function in the US. Present from localhost.

**Voice does not work.** Check the browser has microphone permission. If
it fails it now tells you why rather than resetting silently, so read
what it says. Type instead; nothing else depends on it.

---

## The numbers, if you are asked

- 13 agents, 8 holding data, 5 holding none and working by asking
- 413 tests, all passing, entirely offline
- 4 safety layers, the first two with no network dependency
- 30 days of seeded history, deliberately shaped: sleep declines across
  the month, mood declines with it, and three days are missing so the
  gaps in the charts are real rather than decorative
