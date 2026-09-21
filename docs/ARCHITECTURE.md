# Architecture

## Design principle

Every agent owns one domain and one data table. **No agent reads another
agent's data directly.** If the Symptom agent needs sleep data, it asks the
Sleep agent. That single rule is what makes the system genuinely multi-agent
rather than one program with four functions in it.

## The agent contract

Every specialist implements two methods (`app/agents/base.py`):

| Method | Called by | Returns |
|---|---|---|
| `handle(query)` | The orchestrator | A full conversational reply |
| `report()` | **Other agents**, via the bus | Compact facts, as a dict |

`report()` is the inter-agent interface. It is deliberately small and
structured: facts only, no prose, so a peer can reason over it.

## The bus

`app/agents/bus.py` is the only channel between agents. It does three things:

1. **`register(agent)`** adds an agent to the mesh and injects the bus into it
2. **`request(sender, receiver, reason)`** has one agent ask another for its report
3. **`broadcast(sender, reason)`** asks every specialist at once

Every call is appended to `bus.trace` with timestamp, sender, receiver, the
stated reason, and the returned payload. The API returns that trace with each
response, and the UI renders it. Cross-agent communication is therefore
*observable* rather than merely claimed, which is what makes it demonstrable in the
video.

The orchestrator is excluded from `broadcast()` by default: it holds no domain
data, so including it would add a meaningless hop to the trace.

## Request lifecycle

```
POST /api/chat  { "message": "I keep getting a headache in the afternoon" }
   │
   ├─ 1. Bus.reset_trace()
   │
   ├─ 2. CoachAgent.handle()
   │       ├─ safety.check()            ← red flags stop here, before anything
   │       ├─ _try_log()                ← "I drank 3 glasses" handled inline
   │       ├─ _checkin()                ← "how am I doing" → broadcast to all
   │       └─ _route()                  ← keywords first, model as fallback
   │
   ├─ 3. SymptomAgent.handle()
   │       ├─ safety.check()            ← defence in depth, checked again
   │       ├─ bus.broadcast()           ← ★ the cross-agent fan-out
   │       │     ├─ → hydration.report()
   │       │     ├─ → nutrition.report()
   │       │     └─ → sleep.report()
   │       ├─ search.lookup()           ← RAG (Azure AI Search / local KB)
   │       └─ _contributing_factors()   ← correlate peer data with the symptom
   │
   └─ 4. Response: { reply, agent, data, trace, disclaimer }
```

## Why safety is checked twice

The Coach checks every incoming message, and the Symptom agent checks again.
This is intentional defence in depth: if a future change lets something reach
the Symptom agent by another path, the guardrail still holds. The check is
cheap, local and has no network dependency.

## Graceful degradation

| If this is unavailable | The app does this |
|---|---|
| Azure OpenAI | Keyword routing and templated replies |
| Azure AI Search | Keyword search over `data/health_kb/kb.json` |
| Azure Speech | Text input and output only |
| *Nothing* | The safety layer, which is pure Python and always runs |

`MOCK_MODE=true` forces all fallbacks, so the app is fully demonstrable without
any Azure credentials. This matters for rehearsal and for presentation day if
the network is unreliable.

## File map

```
app/
  config.py              env loading, one place for all settings
  main.py                FastAPI routes
  agents/
    base.py              BaseAgent + AgentReply contract
    bus.py               ★ the message bus and trace log
    coach.py             orchestrator: safety, logging, routing, check-ins
    hydration.py         water intake
    nutrition.py         meals and calories
    sleep.py             sleep hours and debt
    symptom.py           ★ cross-agent correlation + RAG
  services/
    safety.py            ★ red flags and scope guard (no network)
    search.py            RAG, Azure AI Search with a local fallback
    llm.py               Azure OpenAI wrapper
  store/
    db.py                SQLite, plain sqlite3
  web/
    index.html           single-page UI
data/health_kb/kb.json   knowledge base
tests/test_agents.py     smoke tests
scripts_demo.py          terminal walkthrough of the demo scenario
```

## Extension points

Adding a sixth agent (activity, mood, medication reminders) takes three steps:

1. Subclass `BaseAgent`, implement `handle()` and `report()`
2. Register it on the bus in `app/main.py`
3. Add its keywords to `ROUTES` in `coach.py`

It is automatically included in every `broadcast()`, so the Symptom agent starts
correlating its data with no change to the Symptom agent itself. That is the
payoff of routing everything through the bus.
