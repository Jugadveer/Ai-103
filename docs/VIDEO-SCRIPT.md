# 5-minute video script

Timed to the sections the guidelines require: intro 30s, problem 30s,
AI solution 1m, technical demonstration 2m, impact and future 1m.

**Before recording**

- `python -m scripts.seed` so the history and trends have a week of data
- Open `http://127.0.0.1:8000`, light theme, browser zoom at 110%
- Close every other tab. The tab bar is visible in the recording
- Run `python -m scripts.check_azure` once to confirm three services are live
- Record at 1080p. Speak at a normal pace: the script is about 700 words,
  which fits 5 minutes with room to breathe

**A note on who speaks.** Four or five people reading one paragraph each
sounds disjointed. Two voices works better: one narrates, one drives the
screen and speaks during the demo. Everyone still has to be able to answer
questions on presentation day, which is a separate thing from the video.

---

## 0:00 - 0:30 · Introduction

> We are [names], group [number], and this is Health Coach.
>
> It is a wellness assistant built as a team of twelve AI agents that talk
> to each other. Not one chatbot with a health theme: twelve specialists,
> each owning one part of your health, that compare notes before they
> answer you.

*On screen: the Today page, rings visible. Do not click anything yet.*

---

## 0:30 - 1:00 · Problem

> People already track health data. The problem is that every app tracks
> one thing in isolation.
>
> Your calorie app knows nothing about your sleep. Your sleep app knows
> nothing about your hydration. So when you actually feel unwell, nothing
> connects the dots and the advice stays generic.
>
> But an afternoon headache is rarely one thing. It sits at the
> intersection of sleep, water and food. Answering it properly means those
> domains have to talk to each other.

*On screen: still Today. Let the rings and readouts carry it.*

---

## 1:00 - 2:00 · The AI-driven solution

> You talk to one Coach agent. Behind it sit eleven more.
>
> Seven own data: hydration, nutrition, sleep, activity, vitals, mood and
> medication. One handles symptoms. Three hold no data at all and work
> entirely by asking the others: insights finds cross-domain patterns,
> progress tracks streaks, and report builds a summary for a doctor.
>
> The rule that makes it a real multi-agent system is this: **no agent
> reads another agent's data directly.** If the symptom agent needs your
> sleep, it asks the sleep agent, through a message bus that records
> every exchange.
>
> It runs on Azure. Azure OpenAI for reasoning, Azure AI Speech for voice,
> Azure AI Content Safety as a guardrail, and Azure AI Search for
> retrieval.

*On screen: click **Agents** in the sidebar. Scroll the register of twelve
slowly while you talk. Then back to **Today**.*

---

## 2:00 - 4:00 · Technical demonstration

**This is half your marks. Rehearse it until it needs no thinking.**

### Beat 1 · Conversational logging (0:35)

*Go to **Coach**. Type, or say it with the mic:*

`I ate a burger from McDonald's`

> Notice it does not just log a number. A burger is anywhere from 330 to
> 690 calories, so guessing would make the whole day meaningless.

*It asks which burger. Answer:* `a Big Mac`
*It asks what came with it. Answer:* `a medium coke, that's all`

> Seven hundred and seventy three calories, and it asked twice to get
> there. That decision is made by the model, not by a list we wrote, so it
> handles food we never anticipated.

### Beat 2 · The cross-agent moment (0:40)

*Type:* `I keep getting a headache in the afternoon`

*While it answers, point at the folded footnote under the reply, then
switch to the **Agents** page so the full trace is on screen.*

> One question, eight agents. The symptom agent asked hydration,
> nutrition, sleep, activity, vitals, mood and medication, then correlated
> what came back.
>
> Sleep debt of eighteen hours. Two glasses of water. No meals logged.
> Low mood. It names the contributing factors from your own data, and it
> ends by telling you to see a doctor. It never diagnoses.

### Beat 3 · Safety (0:25)

*Back to **Coach**. Type:* `I have crushing chest pain and cannot breathe`

> Emergency numbers, immediately.
>
> And look at the trace: **zero agent calls**. The safety check runs before
> routing, before any agent, before any model call. It is pure Python with
> no network dependency, so the guardrail cannot fail open if Azure is
> unreachable.

### Beat 4 · Breadth, fast (0:20)

*Click through, roughly five seconds each:*

- **Trends** - fourteen days per metric. Gaps mean nothing was logged
- **Progress** - streaks and achievements, all derived from real data
- **Body** - *"we have no wearable, so we say so, and ask instead"*

### Beat 5 · Voice and install (0:20)

*Go to **Voice**, tap the mic, say:* `I slept nine hours`

> Azure Speech in and out. And it installs as an app, so it opens straight
> into voice from your home screen.

---

## 4:00 - 5:00 · Impact and future

> Two hundred and eighteen tests pass, and writing them found four real
> bugs. Two were safety failures: "my face is drooping" slipped past the
> stroke check because our terms assumed adjacent words. That is exactly
> the failure you cannot see by reading code.
>
> Responsible AI was a design constraint, not a feature. It never
> diagnoses, never advises on medication, escalates emergencies before
> anything else runs, and every calorie figure is labelled an estimate.
> Health data stays in a local database and no key is in the repository.
>
> The honest limitations: we have no wearable, so activity is
> self-reported. Our knowledge base needs clinician review. And a web app
> cannot listen for a wake word in the background.
>
> Next would be wearable integration, a cited clinical knowledge base, and
> multi-user accounts.
>
> Thank you.

*On screen: the Report page, doctor summary visible. Hold for the last
sentence.*

---

## Checklist

- [ ] Under 5:00. Overrunning is the easiest mark to lose
- [ ] 1080p, MP4
- [ ] Audio checked. Bad audio ruins a good demo
- [ ] Uploaded to YouTube, **sharing set so anyone with the link can view**
- [ ] Opened the link in a private window to prove it
- [ ] Link submitted through the LMS before the deadline

## If something breaks live

Set `MOCK_MODE=true` and restart. Everything except the model-driven food
conversation and Azure voice still works, all 218 tests still pass, and
the fallback is a point in your favour rather than an excuse: you designed
for the service being unavailable.
