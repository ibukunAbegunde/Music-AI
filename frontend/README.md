# Music AI — frontend

Local React + TypeScript + Vite UI for the Phase-adjacent studio surfaces (brief canvas, role-locks, A/B candidates, versions, jobs, settings).

## Requirements

- Node 20+ (22 OK)
- Backend API on `http://127.0.0.1:8000` (Vite proxies `/api`)

## Run

```bash
# terminal 1 — API (repo root)
source .venv/bin/activate   # or: uv venv && uv pip install -e ".[dev]"
music-ai-api
# equivalent: uvicorn backend.app.main:app --reload --port 8000

# terminal 2 — UI
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Build

```bash
npm run build
npm run preview
```

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Workspace — brief canvas, compose/revise, role-locks, version timeline |
| `/references` | Reference import / demo fixture pipeline |
| `/candidates` | Multi-candidate A/B + musical diff |
| `/jobs` | Job history stub |
| `/settings` | Local settings + doctor (read-only) |

UI primitives follow a shadcn-style pattern (`Button`, `Input`, `Badge`, CVA variants) under `src/components/ui/`.
