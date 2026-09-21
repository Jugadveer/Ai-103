# Responsible AI

This is 15% of the project grade and, in a health application, the part that
matters most. This document records what we decided and why, so any team
member can defend it in the presentation.

## 1. The system never diagnoses

**Decision.** The app is a *wellness coach*, not a diagnostic tool. It shares
general health information and surfaces patterns in the user's own logged
data. It never names a condition, never estimates probability of a disease,
and never recommends medication or dosage.

**Why.** A student project cannot be clinically validated. Presenting output
that looks like a diagnosis could lead a real user to delay proper care.

**How it is enforced.** `app/services/safety.py` blocks out-of-scope requests
("diagnose me", "what medicine should I take", "what dose") before they reach
any model, and returns a fixed refusal explaining what the app *can* do.

## 2. Emergencies are escalated before anything else runs

**Decision.** A red-flag check runs on every message as the very first
operation, ahead of routing, ahead of any agent call and ahead of any model
call.

**Why.** If someone types "chest pain and I can't breathe", the only correct
behaviour is to tell them to get help immediately. Latency matters, and so
does not burying the message under wellness advice.

**How it is enforced.** `RED_FLAGS` in `app/services/safety.py` covers cardiac,
respiratory, neurological, bleeding, allergic and self-harm presentations. A
match returns emergency contact numbers (112 / 108 in India) and stops
processing. The test `test_emergency_short_circuits_before_peers` asserts that
**zero** agent calls happen after a red-flag match.

## 3. Transparency

- Every reply carries a disclaimer (`config.DISCLAIMER`).
- The UI shows the full agent-to-agent trace, so the user can see exactly
  which agents contributed and what data each one supplied.
- RAG answers carry their source passage, so information is attributable
  rather than asserted.

**Why.** A health assistant that cannot show its reasoning should not be
trusted with health questions.

## 4. Human oversight

The system is explicitly positioned as a step *before* seeing a clinician, not
instead of one. Every symptom reply ends by naming the conditions under which
the user should see a doctor.

## 5. Privacy and data handling

- All health data stays in a **local SQLite file**. Nothing is uploaded to a
  third party beyond the Azure API calls needed to generate a response.
- No name, email, phone number or identity data is collected.
- `.env` is git-ignored; no key, token or connection string is ever committed.
  This is both a course requirement and basic practice.
- The database file (`*.db`) is git-ignored so no personal log data is pushed.

## 6. Fairness and reliability

**Known limitation, stated honestly:** the knowledge base is small and
English-only, and thresholds (8 glasses of water, 8 hours of sleep, 2000 kcal)
are generic adult defaults. They do not adapt for age, body size, pregnancy,
climate or medical conditions. The app therefore frames findings as
*contributing factors to consider*, never as personalised medical targets.

Reliability is handled by degrading rather than failing: if Azure AI Search or
Azure OpenAI is unavailable, the app falls back to the local knowledge base and
rule-based logic instead of crashing. The safety layer is pure Python with no
network dependency, so **guardrails never fail open**.

## Presentation checklist

Be ready to answer:

- [ ] What happens if a user describes a medical emergency? *(demo it live)*
- [ ] How do you stop it giving a diagnosis?
- [ ] Where is health data stored, and who can see it?
- [ ] What happens when the Azure services are down?
- [ ] Who might this system serve badly, and why?
