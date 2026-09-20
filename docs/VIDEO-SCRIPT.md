# 5-minute video script

Timed to the sections the guidelines require: intro 30s, problem 30s,
AI-driven solution 1m, technical demonstration 2m, impact and future 1m.

Spoken words below total roughly 690, which lands near 5:00 at a normal
pace. **The demo is the tight part.** Rehearse it until it needs no
thinking, and use the cut list at the bottom if you overrun.

---

## Before you record

```bash
python -m scripts.seed            # a week of history for the charts
python -m scripts.check_azure     # confirm three services are live
uvicorn app.main:app --reload
```

Then, once, in the app:

1. **Body** page: enter height 175, weight 70, age 21, sex, activity
   *light*, and save. Without this the Review page cannot calculate and
   will open a conversation instead of showing the numbers.
2. **Today** page: check the rings are populated.
3. Leave the app on **Today**, light theme, browser zoom 110%.
4. Close every other tab. The tab bar is in the recording.

**Who speaks.** Two voices, not five. One narrates sections 1, 2, 3 and 5;
the other drives the screen and talks through the demo. Four people reading
a paragraph each sounds disjointed. Everyone still has to answer questions
on presentation day, which is a separate thing.

---

## 0:00 - 0:30 · Introduction

> We are [names], group [number]. This is Health Coach.
>
> It is a wellness assistant built as thirteen AI agents that talk to each
> other. Not one chatbot with a health theme. Thirteen specialists, each
> owning one part of your health, that compare notes before they answer.

*On screen: Today page, rings visible. Do not click yet.*

---

## 0:30 - 1:00 · Problem

> People already track health data. The problem is that every app tracks
> one thing in isolation.
>
> Your calorie app knows nothing about your sleep. Your sleep app knows
> nothing about your hydration. So when you actually feel unwell, nothing
> connects the dots and the advice stays generic.
>
> An afternoon headache is rarely one thing. It sits at the intersection of
> sleep, water and food. Answering it properly means those domains have to
> talk to each other.

*On screen: still Today. Let the rings carry it.*

---

## 1:00 - 2:00 · The AI-driven solution

> You talk to one Coach agent. Behind it sit twelve more.
>
> Eight own data: hydration, nutrition, sleep, activity, vitals, mood,
> medication and symptoms. Four hold no data at all and work entirely by
> asking the others. Insights finds cross-domain patterns. Progress tracks
> streaks. Report builds a doctor summary. And Assessment estimates what
> you need in a day and checks what you logged against it.
>
> The rule that makes this a real multi-agent system is this: **no agent
> reads another agent's data directly.** If the symptom agent needs your
> sleep, it asks the sleep agent, through a message bus that records every
> exchange.
>
> It runs on Azure. Azure OpenAI for reasoning and for reading food photos,
> Azure AI Speech for voice, and Azure AI Content Safety as a guardrail.

*On screen: click **Agents**. Scroll the register of thirteen slowly while
you talk, then return to **Coach**.*

---

## 2:00 - 4:00 · Technical demonstration

**This is half your marks. Rehearse it.**

### Beat 1 · It asks before it guesses (0:30)

*On **Coach**, type:* `I ate a burger from McDonald's`

> It does not log a number. A burger is anywhere from 330 to 690 calories,
> so guessing would make the whole day meaningless.

*It asks which burger.* Type: `a Big Mac`
*It asks what came with it.* Type: `a medium coke, that's all`

> Seven hundred and seventy three calories, and it asked twice to get
> there. The model decides when to ask, so it handles food we never
> anticipated. You can also photograph the meal instead.

### Beat 2 · The cross-agent moment (0:35)

*Type:* `I keep getting a headache in the afternoon`

*As it answers, click **Agents** so the full trace fills the screen.*

> One question, eight agents. The symptom agent asked hydration, nutrition,
> sleep, activity, vitals, mood and medication, then correlated what came
> back.
>
> Eighteen hours of sleep debt. Two glasses of water. Low mood. It names
> the contributing factors from your own data, and it ends by telling you
> to see a doctor. It never diagnoses.

### Beat 3 · Safety (0:20)

*Back to **Coach**. Type:* `I have crushing chest pain and cannot breathe`

> Emergency numbers, immediately. And look at the trace: **zero agent
> calls**. The safety check runs before routing, before any agent, before
> any model call. It is pure Python with no network dependency, so the
> guardrail cannot fail open if Azure is unreachable.

### Beat 4 · The assessment (0:20)

*Click **Review**, then **Run the review**.*

> This one consults every agent, estimates maintenance calories from height,
> weight, age and activity, and checks intake against it.
>
> Note what it says here: intake far below requirement is read as
> **incomplete logging**, not starvation. Telling someone who forgot lunch
> that they are starving would be both wrong and alarming.

### Beat 5 · Breadth (0:15)

*Five seconds each:*

- **Trends** - fourteen days per metric, gaps where nothing was logged
- **Progress** - streaks and achievements, all from real data
- **Body** - *"no wearable, so we say so and ask instead"*

---

## 4:00 - 5:00 · Impact and future

> Two hundred and fifty three tests pass, and writing them found real bugs.
> Two were safety failures: "my face is drooping" slipped past the stroke
> check because our terms assumed adjacent words. That is exactly the
> failure you cannot see by reading code.
>
> Responsible AI was a design constraint, not a feature. It never
> diagnoses, never advises on medication, escalates emergencies before
> anything else runs, and every calorie figure is labelled an estimate.
> Health data stays in a local database and no key is in the repository.
>
> Our honest limitations: the app measures nothing. No wearable, no
> sensors. Heart rate, steps and mood are all self-reported, and we say so
> on every screen rather than implying otherwise. Our knowledge base still
> needs clinician review.
>
> Next would be wearable integration, a cited clinical knowledge base, and
> multi-user accounts.
>
> Thank you.

*On screen: **Report** page, doctor summary visible. Hold for the last line.*

---

## If you overrun, cut in this order

1. **Beat 5, breadth** - the whole thing. Saves 15s
2. **Beat 4, assessment** - down to one sentence on maintenance calories
3. The Azure sentence in section 3
4. One limitation from section 5

**Never cut Beat 2 or Beat 3.** The cross-agent trace is the project, and
the safety block is the strongest twenty seconds you have.

## If something breaks live

Set `MOCK_MODE=true` and restart. Everything except the model-driven food
conversation and Azure voice still works, all 253 tests still pass, and the
fallback is a point in your favour rather than an excuse: you designed for
the service being unavailable.

## Submission checklist

- [ ] Under 5:00. Overrunning is the easiest mark to lose
- [ ] 1080p, MP4
- [ ] Audio checked. Bad audio ruins a good demo
- [ ] Uploaded to YouTube, **sharing set so anyone with the link can view**
- [ ] Link opened in a private window to prove it works
- [ ] Link submitted through the LMS before the deadline
