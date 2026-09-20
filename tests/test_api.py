"""HTTP surface. Every endpoint, plus input validation at the boundary."""


def test_health_lists_agents_and_azure_status(client):
    d = client.get("/api/health").json()
    assert d["status"] == "ok"
    assert d["mock_mode"] is True
    assert len(d["agents"]) == 11
    # Azure flags are all False until real keys are added to .env
    assert set(d["azure"]) == {"openai", "search", "speech", "content_safety"}


def test_agents_endpoint_describes_each_agent(client):
    rows = client.get("/api/agents").json()
    assert len(rows) == 11
    for row in rows:
        assert row["name"] and row["description"]


def test_index_serves_the_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Health Coach" in r.text


def test_chat_returns_reply_and_trace(client):
    r = client.post("/api/chat", json={"message": "I drank 3 glasses of water"})
    assert r.status_code == 200
    d = r.json()
    assert "Logged 3 glasses" in d["reply"]
    assert d["disclaimer"]
    assert isinstance(d["trace"], list)


def test_chat_emergency_is_blocked_over_http(client):
    d = client.post("/api/chat",
                    json={"message": "I have chest pain"}).json()
    assert d["data"]["blocked"] is True
    assert d["trace"] == []


def test_chat_rejects_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_chat_rejects_overlong_message(client):
    r = client.post("/api/chat", json={"message": "x" * 5000})
    assert r.status_code == 422


def test_chat_rejects_malformed_body(client):
    assert client.post("/api/chat", json={}).status_code == 422


def test_dashboard_returns_every_agent_report(client):
    d = client.get("/api/dashboard").json()
    assert len(d) == 11
    assert "glasses_today" in d["hydration"]
    assert "avg_hours" in d["sleep"]


def test_seed_then_full_demo_flow(client):
    """The exact sequence used in the demo video."""
    assert client.post("/api/seed").json()["status"] == "seeded"

    d = client.post("/api/chat",
                    json={"message": "I keep getting a headache in the afternoon"}
                    ).json()
    contacted = {h["to"] for h in d["trace"]}
    assert {"hydration", "sleep", "nutrition", "mood"}.issubset(contacted)
    assert "not a diagnosis" in d["reply"]

    insights = client.post("/api/chat",
                           json={"message": "show me the patterns"}).json()
    assert insights["data"]["patterns"]

    report = client.post("/api/chat",
                         json={"message": "make a summary for my doctor"}).json()
    assert "HEALTH SUMMARY" in report["reply"]


def test_invalid_value_is_rejected_with_a_readable_message(client):
    d = client.post("/api/chat",
                    json={"message": "I slept 500 hours"}).json()
    assert d["data"].get("rejected") is True
    assert "0.5" in d["reply"] and "18" in d["reply"]


def test_speak_endpoint_degrades_cleanly_without_speech(client):
    """
    In MOCK_MODE there is no Speech key, so /api/speak must return 503 -
    the signal the page uses to fall back to the browser's own voice.
    """
    r = client.post("/api/speak", json={"text": "hello"})
    assert r.status_code == 503


def test_speak_validates_input(client):
    assert client.post("/api/speak", json={"text": ""}).status_code == 422
    assert client.post("/api/speak", json={"text": "x" * 4000}).status_code == 422
