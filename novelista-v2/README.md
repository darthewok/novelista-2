# Novelista v2

A stand-alone, local-first novel-writing assistant. One process serves the UI and the API on `http://127.0.0.1:8000`. No database, no CORS, no external fonts or scripts. Bring your own key.

## Run

Needs Python 3.11 or newer. Nothing else.

- Windows: double-click `start.bat` (first run installs dependencies, about a minute). `stop.bat` to quit.
- macOS: double-click `start.command`. `stop.command` to quit. If macOS refuses to open them: `chmod +x start.command stop.command`.

The browser opens on the dashboard. Open **Settings** first and pick a provider:

| Provider | Needs |
|---|---|
| Anthropic | an API key |
| OpenAI / OpenRouter / any OpenAI-compatible endpoint | an API key and base URL |
| LM Studio | LM Studio running with its server on (default `http://localhost:1234/v1`) |
| Ollama | Ollama running (default `http://localhost:11434`) |

Then set a model per task. On Anthropic the defaults are Opus 5.5 for outline, draft, revise and editor; Sonnet 5.5 for foundation, voice and seed; Haiku 5.5 for summary and canon. The "Economy" button moves the prose tasks to Sonnet.

## Workflow

Seed → Voice (three trial openings, pick one) → World → Characters → Canon → Outline → Chapters → Export.

On each chapter: **Draft**, then read the **Tells** panel (a mechanical scan for AI tells that runs after every draft and revise), then **Polish** (an editor pass on your editor model writes a revision brief and revises once), **Tighten** (cuts about 10% of words), **Revise** with your own notes, **Accept**. Every draft, revise and polish keeps the previous text under **Versions**.

Auto-polish (Settings → Quality) runs the polish pass after every draft automatically. It is off by default.

## Where things live

```
data/settings.json                  provider, keys, models, quality options
data/novels/<id>/book.json          book metadata and chapter state
data/novels/<id>/*.md               seed, voice, world, characters, canon, outline, summary
data/novels/<id>/chapters/          ch_NN.md and ch_NN.vN.md snapshots
data/novels/<id>/briefs/            revision briefs
data/novels/<id>/reports/           scanner reports (JSON)
```

Keys are stored in plain text in `data/settings.json`. Keep that folder private.

## Migrating from v1

```
python scripts/migrate_sqlite.py --db ../novelista/backend/data/novelista.db --src ../novelista/backend/data/novels --dest data/novels
```

## Developing

Backend: `cd backend && .venv\Scripts\python -m pytest`. Frontend: `cd frontend && npm install && npm run build` (the build fails if any external URL sneaks into the bundle). Commit `frontend/dist`; users never run Node.
