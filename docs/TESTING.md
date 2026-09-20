# Testing

```bash
python -m pytest tests/ -q
```

**150 tests, all passing, in about 1.3 seconds.** No Azure credentials needed —
the suite runs entirely in `MOCK_MODE` against a throwaway SQLite file.

Testing, reliability and responsible AI carry 15% of the project grade, and
the safety tests below are the ones to demonstrate if asked.

## What each suite covers

| Suite | Tests | Focus |
|---|---|---|
| `test_validation.py` | 24 | Plausible ranges for every health value |
| `test_nlu.py` | 41 | Intent classification and entity extraction |
| `test_safety.py` | 29 | Emergency escalation and scope refusal |
| `test_agents.py` | 30 | Each agent's calculations in isolation |
| `test_crossagent.py` | 15 | Agent-to-agent communication |
| `test_api.py` | 11 | HTTP endpoints and boundary validation |

## The tests that matter most

**Safety must not fail open.** `test_guardrails_do_not_need_the_network`
asserts the red-flag and scope layers work with Azure switched off entirely.

**Safety must not over-block.** `test_ordinary_messages_are_not_blocked` runs
seven everyday messages ("I have a mild sore throat", "feeling stressed about
exams") and asserts none are refused. An over-cautious health app is a useless
one, so both directions are tested.

**Nothing runs after a red flag.** `test_emergency_short_circuits_before_any_peer_call`
asserts `bus.trace == []` after "chest pain and cannot breathe" — proving the
guardrail runs before routing, before peers, before any model call.

**Cross-agent communication actually happens.**
`test_symptom_queries_every_data_peer` asserts all seven data-holding agents
appear in the trace after a single symptom question.

**The system extends without editing existing agents.**
`test_adding_an_agent_extends_correlation_automatically` registers a brand-new
agent at runtime and asserts the Symptom agent starts querying it — with no
change to the Symptom agent. That is the payoff of routing through the bus.

## Bugs these tests caught during development

Recorded honestly, because "what did testing actually do for you" is a fair
question to be asked in the viva.

| Bug | Caught by | Fix |
|---|---|---|
| `ran` matched inside "d**ran**k", so drinking water logged as exercise | `test_drank_is_not_mistaken_for_ran` | Word boundaries on every exercise verb |
| "my face **is** drooping" bypassed the stroke red flag, because the term assumed adjacent words | `test_emergencies_are_escalated` | Multi-word safety terms now tolerate inserted filler words |
| "my throat **is** closing up" bypassed the anaphylaxis red flag | same | same |
| With an empty database the app claimed "you're running low on food and fluids" | `test_insights_says_so_when_there_is_nothing` | Agents now report `has_data`; no pattern is asserted without evidence |
| The doctor summary printed empty sections for domains with no data | `test_report_declines_when_data_is_thin` | Sections are gated on `has_data` |

The two safety misses are the important ones. Both were false negatives on
stroke and anaphylaxis presentations — exactly the failure mode that matters
in a health app, and neither was visible by reading the code.

## Manual verification

Beyond the automated suite, the full demo path was exercised in the browser:
load demo data → report a headache → view the agent trace → request insights →
generate the doctor summary. The trace panel showed 8 agent calls for the
symptom question and 9 for the report.

## Not covered yet

Stated plainly rather than hidden:

- No tests against live Azure services (everything runs in `MOCK_MODE`)
- No load or concurrency testing — the app is single-user by design
- No browser automation; UI checks were manual
- The knowledge base content itself is unverified placeholder text
