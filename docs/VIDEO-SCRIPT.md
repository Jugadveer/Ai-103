# The five minute video

Final script. Every reply quoted here is one the deployed app actually
gave, so what you say matches what appears.

Timed to the sections the guidelines ask for: intro 30s, problem 30s,
AI-driven solution 1m, technical demonstration 2m, impact and future 1m.
Spoken words total about 700, which lands near 5:00 at a normal pace.

**Two voices, not five.** One narrates sections 1, 2, 3 and 5; the other
drives the screen and talks through the demo. Four people reading a
paragraph each sounds disjointed. Everyone answers questions on
presentation day regardless, which is a separate thing.

---

## Before you press record

```bash
python -m scripts.seed
python -m scripts.check_azure
uvicorn app.main:app --reload
```

`scripts.seed` makes a `demo@local` account with the password `demo1234`
and a month of history in it.

Then, once, in the app:

1. Sign in as `demo@local`, and let the browser save the password so no
   prompt interrupts the recording
2. **My body**: height 175, weight 70, age 21, sex, activity *light*, and
   save. Without this the Full check-up asks questions instead of showing
   numbers
3. **For my doctor**: press **Build it** so the closing shot is ready
4. Allow the microphone, and say one test sentence
5. Sign out again. The video opens on the sign-in screen
6. Close every other tab. The tab bar is in the recording
7. Light theme, browser zoom 110%

**Record locally, not from the hosted URL.** Nothing sleeps, and no
network sits between a click and the answer.

---

## 0:00 - 0:30 · Introduction

> We are [names], group [number]. This is Health Coach.
>
> It is a wellness assistant built as thirteen AI agents that talk to
> each other. Not one chatbot with a health theme. Thirteen specialists,
> each owning one part of your health, that compare notes before they
> answer.

*On screen: the sign-in screen. Sign in as the line is spoken, so the
demo starts from a real session rather than an app already open.*

---

## 0:30 - 1:00 · The problem

> People already track health data. The problem is that every app tracks
> one thing in isolation.
>
> Your calorie app knows nothing about your sleep. Your sleep app knows
> nothing about your hydration. So when you actually feel unwell, nothing
> connects the dots and the advice stays generic.
>
> An afternoon headache is rarely one thing. It sits at the intersection
> of sleep, water and food. Answering it properly means those domains
> have to talk to each other.

*On screen: the Today page. Let the five rings carry it.*

---

## 1:00 - 2:00 · The AI-driven solution

> You talk to one Coach agent. Behind it sit twelve more.
>
> Eight own data: hydration, nutrition, sleep, activity, vitals, mood,
> medication and symptoms. Four hold none at all and work entirely by
> asking the others, for patterns, streaks, energy needs and the doctor
> summary.
>
> The rule that makes this a real multi-agent system is this: no agent
> reads another agent's data directly. If the symptom agent needs your
> sleep, it asks the sleep agent, through a message bus that records
> every exchange.
>
> Everyone has their own account, and a test reads every line of SQL in
> the project and fails the build if one asks for health data without
> saying whose.
>
> It runs on Azure. Azure OpenAI for reasoning and for reading food
> photos, Azure AI Speech for voice, and Azure AI Content Safety as a
> guardrail.

*On screen: click **How it works**. Scroll the register of thirteen
slowly while you talk, then return to **Talk to it**.*

---

## 2:00 - 4:00 · Technical demonstration

**This is half your marks. Rehearse it.**

The six beats below add up to 2:15 against a two minute slot. That is
deliberate: Beat 6 is the buffer, so drop it the moment you are behind
and you are back on time.

### Beat 1 · It asks before it guesses (30s)

*On **Talk to it**, type:* `I ate a burger from McDonald's`

> It does not log a number. A burger is anywhere from 330 to 690
> calories, so guessing would make the whole day meaningless.

*It asks which burger.* Type: `a Big Mac`
*It asks what came with it.* Type: `a medium coke, that's all`

> Seven hundred and seventy three calories, and it asked twice to get
> there. The model decides when a description is too vague, so it handles
> food we never anticipated. There is no list of vague foods in the code.

### Beat 2 · Voice (15s)

*Tap **Tap to speak** and say:* `I slept about five hours last night`

> Recorded in the browser, transcribed by Azure AI Speech, routed to the
> sleep agent, logged. If the microphone is blocked or nothing is heard
> it says which, rather than silently resetting.

### Beat 3 · The cross-agent moment (35s)

*Type:* `I keep getting a headache in the afternoon`

*As it answers, expand **+ 8 agent calls** underneath the reply.*

> One question, eight agents. The symptom agent asked hydration,
> nutrition, sleep, activity, vitals, mood and medication, then
> correlated what came back.
>
> Sixteen hours of sleep debt, low fluid intake, low mood. It names the
> contributing factors from your own data, and ends by telling you to see
> a doctor. It never diagnoses.

*That list is generated from the bus, not written by us.*

### Beat 4 · Safety (25s)

*Type:* `I have crushing chest pain and cannot breathe`

> Emergency numbers, immediately. And look at the trace: zero agent
> calls. The safety check runs before routing, before any agent, before
> any model call. It is pure Python with no network dependency, so the
> guardrail cannot fail open if Azure is unreachable.

*Then type:* `I have had a rash for two weeks, what is wrong with me`

> It will not name a condition. It tells you which clinician and how
> soon. A flat refusal leaves a worried person exactly where they
> started, so triage is the useful and honest answer. Naming the thing is
> the part that needs a doctor, and that stays refused.

### Beat 5 · The assessment (20s)

*Click **Full check-up**, then **Run the review**.*

> This consults every agent, estimates maintenance calories, and checks
> intake against it. Note what it says: intake far below requirement is
> read as incomplete logging, not starvation. Telling someone who forgot
> lunch that they are starving would be wrong and alarming.

### Beat 6 · Breadth (10s)

*Five seconds each:*

- **My trends** - thirty days per metric, gaps where nothing was logged
- **For my doctor** - already built, cards and sparklines

---

## 4:00 - 5:00 · Impact and future

> Four hundred and thirty four tests pass, and writing them found real
> bugs.
>
> Two were safety failures. "My face is drooping" slipped past the stroke
> check because our terms assumed adjacent words. And "I think I am
> having a heart attack" was answered with a summary of the person's
> sleep and water, because "chest pain" was on our list and "heart
> attack" was not. That second one changed the design: there is a model
> triage layer now that catches the phrasings a written list never will,
> with the list kept underneath it so the app is exactly as safe with the
> network down as with it up.
>
> Responsible AI was a design constraint, not a feature. It never
> diagnoses, never advises on medication, and escalates emergencies
> before anything else runs.
>
> Our honest limitations: the app measures nothing. No wearable, no
> sensors. Heart rate, steps and mood are all self-reported, and we say
> so on every screen rather than implying otherwise. Our knowledge base
> still needs clinician review.
>
> Next would be wearable integration and a cited clinical knowledge base.
>
> Thank you.

*On screen: the **For my doctor** page, the report already built. Hold
for the last line.*

---

## If you overrun, cut in this order

1. **Beat 6, breadth** - the whole thing. Saves 10s
2. **Beat 2, voice** - saves 15s, but only if voice is being awkward
3. **Beat 5, assessment** - down to one sentence on maintenance calories
4. The Azure sentence in section 3
5. One limitation from section 5

**Never cut Beat 3 or Beat 4.** The cross-agent trace is the project, and
the safety block is the strongest twenty seconds you have.

## If something breaks live

Set `MOCK_MODE=true` and restart. Everything except the model-driven food
conversation and Azure voice still works, all 434 tests still pass, and
the fallback is a point in your favour rather than an excuse: you
designed for the service being unavailable.

## Submission checklist

- [ ] Under 5:00. Overrunning is the easiest mark to lose
- [ ] 1080p, MP4
- [ ] Audio checked. Bad audio ruins a good demo
- [ ] Uploaded to YouTube, **sharing set so anyone with the link can view**
- [ ] Link opened in a private window to prove it works
- [ ] Link submitted through the LMS before the deadline
