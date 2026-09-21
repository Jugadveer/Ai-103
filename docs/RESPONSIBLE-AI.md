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

- Health data lives in the app's own database, SQLite locally or Postgres
  on a hosted deployment. Nothing is uploaded to a third party beyond the
  Azure API calls needed to generate a response.
- **Accounts collect a name, an email and a password, and nothing else.**
  No phone number, no address, no date of birth. The name is used to greet
  you and the email to sign you in.
- The password is hashed with scrypt and a per-password salt. The plain
  password is never stored, never logged, and never appears in an error
  message. There is no route, admin or otherwise, that can read one back.
- **One account cannot see another's record.** Every row carries its owner
  and every query filters on it. That is easy to promise and easy to break
  by forgetting one query, so `tests/test_isolation.py` reads every SQL
  string in the codebase and fails the build if one touching personal data
  has no owner condition, and `tests/test_auth.py` fails the build if any
  endpoint answers without a session.
- The session cookie holds a user id and an expiry, signed. It is httponly,
  so a script on the page cannot read it, and samesite, so another site
  cannot use it. It carries no health data.
- `.env` is git-ignored; no key, token or connection string is ever committed.
  This is both a course requirement and basic practice.
- The database file (`*.db`) is git-ignored so no personal log data is pushed.

**Stated plainly:** stored records are not encrypted at rest beyond
whatever the host provides, there is no password reset, and there is no
way to export or delete an account from inside the app. Those are real
gaps for anything handling health data, and they are listed here rather
than left for someone to discover.

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
