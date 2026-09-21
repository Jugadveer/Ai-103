# Deployment

The app is a stateful FastAPI service backed by SQLite. That one fact
decides everything below.

## Why Vercel is only a preview

Vercel runs serverless functions. Two consequences:

1. **The filesystem is read-only** except `/tmp`. `sqlite3.connect()` on a
   normal path fails on the first write, which is why every data agent
   returned `{"error": true}` and `POST /api/quicklog` returned a 500.
2. **The container is discarded between requests.** Even writing to `/tmp`,
   data disappears unpredictably, and two people using it at the same time
   may be served by different containers holding different data.

There is deliberately **no `vercel.json`**. One was added and it broke the
whole deployment with a 500: the `builds`/`routes` format is the legacy
config and it overrides Vercel's own detection, which was working.
Vercel's current Python support expects the ASGI app under `api/`, which
would mean restructuring the project for a preview that cannot hold data
anyway. Not worth it.

Instead the app detects the read-only disk at startup and falls back to
`/tmp` by itself, so no host configuration is needed. The interface then
shows a banner saying data will not be kept, because silently losing what
someone logged is worse than telling them.

**Use Vercel to show the app exists. Do not use it to test with.**

## Render, for testing with the team

Render runs it as an ordinary container with a mounted disk, so data is
still there when a tester comes back. `render.yaml` is committed.

1. Sign in at render.com with GitHub and pick this repository
2. Render reads `render.yaml`; accept the free plan
3. Add the Azure variables in the dashboard (they are marked `sync: false`
   in the file precisely so they are never committed):
   `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
   `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`,
   `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`,
   `AZURE_CONTENT_SAFETY_ENDPOINT`, `AZURE_CONTENT_SAFETY_KEY`
4. Deploy, then check `/api/health` reads `"storage": "persistent"`

Note the free plan sleeps after inactivity, so the first request after a
quiet spell takes a few seconds.

## Locally, which is what the video should use

```bash
pip install -r requirements.txt
python -m scripts.seed
uvicorn app.main:app --reload
```

Everything works, nothing sleeps, and no network round-trip sits between a
click and the answer.

## Checking a deployment

```bash
curl https://<your-host>/api/health
```

```json
{
  "status": "ok",
  "storage": "persistent",
  "agents": ["coach", "..."],
  "azure": { "openai": true, "speech": true, "content_safety": true }
}
```

- `storage: ephemeral` means data will not survive
- any `azure` flag `false` means that variable is missing on the host
- the app still runs with all of them false, on local rules and data

## Keys

`.env` is git-ignored and must stay that way. Keys live in the host's own
environment settings. `render.yaml` deliberately declares them without
values.
