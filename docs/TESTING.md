# Testing

```bash
python -m pytest tests/ -q
```

**434 tests, all passing, in about two minutes.** No Azure credentials needed,
the suite runs entirely in `MOCK_MODE` against a throwaway SQLite file.

Testing, reliability and responsible AI carry 15% of the project grade, and
the safety tests below are the ones to demonstrate if asked.

## What each suite covers

| Suite | Tests | Focus |
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

## The tests that matter most

**Safety must not fail open.** `test_guardrails_do_not_need_the_network`
asserts the red-flag and scope layers work with Azure switched off entirely.

**Safety must not over-block.** `test_ordinary_messages_are_not_blocked` runs
seven everyday messages ("I have a mild sore throat", "feeling stressed about
exams") and asserts none are refused. An over-cautious health app is a useless
one, so both directions are tested.

**Nothing runs after a red flag.** `test_emergency_short_circuits_before_any_peer_call`
asserts `bus.trace == []` after "chest pain and cannot breathe", proving the
guardrail runs before routing, before peers, before any model call.

**Cross-agent communication actually happens.**
`test_symptom_queries_every_data_peer` asserts all seven data-holding agents
appear in the trace after a single symptom question.

**A forgotten filter cannot reach main.**
`test_every_query_on_personal_data_filters_by_owner` parses every Python
file in the app, pulls out every SQL string, and fails if one touches a
table of personal data without a `user_id` condition. Behavioural tests can
only check the paths someone thought to try; a query added to a new agent
next month would pass all of them while serving the wrong person's numbers.

**An endpoint cannot be added ungated.**
`test_every_data_endpoint_requires_signing_in` walks FastAPI's own route
table and asserts every `/api` route answers 401 without a session. Anything
genuinely public has to be named in a list, so leaving a route open becomes
a visible line in a diff.

**The system extends without editing existing agents.**
`test_adding_an_agent_extends_correlation_automatically` registers a brand-new
agent at runtime and asserts the Symptom agent starts querying it, with no
change to the Symptom agent. That is the payoff of routing through the bus.

## Bugs these tests caught during development

Recorded honestly, because "what did testing actually do for you" is a fair
question to be asked in the viva.

| Bug | Caught by | Fix |
|---|---|---|
| Plural food names matched nothing, so "two rotis" logged only the dal | `test_quantities_including_plurals` | Optional plural suffix in the matcher |
| "that's all" failed to close a conversation, because the apostrophe normalised to a space | `test_closing_phrases_end_the_exchange` | Apostrophes are dropped, not spaced |
| A sentence naming only foods routed to the symptom agent, having no nutrition keyword in it | `test_offline_logs_what_it_recognises` | Routing consults the food table |
| Azure vision read a plain red square as "a sandwich and soup" | manual check during development | Photos propose and wait for confirmation; nothing is written unprompted |
| `ran` matched inside "d**ran**k", so drinking water logged as exercise | `test_drank_is_not_mistaken_for_ran` | Word boundaries on every exercise verb |
| "my face **is** drooping" bypassed the stroke red flag, because the term assumed adjacent words | `test_emergencies_are_escalated` | Multi-word safety terms now tolerate inserted filler words |
| "my throat **is** closing up" bypassed the anaphylaxis red flag | same | same |
| With an empty database the app claimed "you're running low on food and fluids" | `test_insights_says_so_when_there_is_nothing` | Agents now report `has_data`; no pattern is asserted without evidence |
| The doctor summary printed empty sections for domains with no data | `test_report_declines_when_data_is_thin` | Sections are gated on `has_data` |
| "I think I am having a heart attack" got an eight-hop correlation, because "chest pain" was on the red-flag list and "heart attack" was not | attacking the deployed app | A model triage layer that generalises, with the list kept underneath it as an offline floor |
| Asking how many mg of paracetamol to take was answered with a mental-health message | same | Azure scores that and "I don't want to be here anymore" identically, so the shape of the message picks between them, defaulting to the careful one |
| "What is my streak" made 17 agent calls and then said it had no access to the streak | same | Routing was spelled as a data request, and a meta-agent's report never reached the model |
| The headline sleep and mood insight silently vanished on 23 September | `test_the_sleep_mood_link_does_not_depend_on_todays_date` | It fired on two threshold crossings, one of which the seeded month sat 0.1 above. It measures the correlation now |
| A database written before accounts existed survived startup, because `CREATE TABLE IF NOT EXISTS` will not add a column, then failed on the first query | first run of `test_isolation.py` | Startup detects the old shape and moves the file aside rather than crashing |
| Logging sleep twice in one day added the two figures together: 4.8 hours seeded plus a 6 became 10.8 hours in bed, and the status flipped from `poor` to `ok` | preparing the demo account | Sleep and steps restate the day's figure instead of appending to it |
| "I walked 10k steps" logged ten minutes of walking, because no step rule matched `10k` and the exercise rule matched the bare 10 underneath it | `test_a_shortened_count_is_not_read_as_exercise_minutes` | A lone `k` is expanded to a thousand before any rule runs; `kg`, `km` and `kcal` keep theirs |
| "10,000 steps" logged zero steps, the number rule having matched the `000` after the comma | `test_a_thousands_separator_is_not_read_as_zero` | Thousands separators are stripped between digits |

The two safety misses are the important ones. Both were false negatives on
stroke and anaphylaxis presentations, which is exactly the failure mode that matters
in a health app, and neither was visible by reading the code.

## Manual verification

Beyond the automated suite, the full demo path was exercised in the browser:
load demo data → report a headache → view the agent trace → request insights →
generate the doctor summary. The trace panel showed 8 agent calls for the
symptom question and 9 for the report.

## Not covered yet

Stated plainly rather than hidden:

- No tests against live Azure services (everything runs in `MOCK_MODE`)
- The suite runs against SQLite only. The Postgres path shares the same SQL
  and is exercised by hand, not by CI
- No load or concurrency testing
- No browser automation; UI checks were manual
- The knowledge base content itself is unverified placeholder text
