# Baby Intake Dashboard

A lightweight Flask + SQLite dashboard to log baby feeding intake, compare trends, and track weight.

## Features

- Mobile-friendly dashboard UI
- Language switcher (Dutch default, English optional)
- Read-only view for everyone
- Password login for data entry and delete actions
- Intake input form with defaults:
  - Date in `DD-MM` (pre-filled with current date)
  - Time in `HH:MM` (pre-filled with current time)
  - Intake amount in ml
  - Optional remark
- Weight input form:
  - Date in `DD-MM`
  - Weight in grams
  - Optional remark
- Charts:
  - **Daily totals** with chart type toggle (**bar** default / line)
  - **Intake over time** with day overlay compare and view toggle (**cumulative** default / individual)
  - **Weight trend** as line chart across days
- SQLite persistence (stored on disk)
- Docker / Portainer friendly deployment

## Quick start (Docker)

```bash
docker compose up -d --build
```

Open:

```text
http://<your-host>:8080
```

## Configuration

Set environment variables in `docker-compose.yml` or via Portainer stack config:

- `SECRET_KEY`: long random secret
- `ADMIN_PASSWORD`: your dashboard password
- `DB_PATH` (optional): default `/data/babylog.db`
- `TRANSLATIONS_FILE` (optional): default `translations.json`

## Data storage

SQLite database file is persisted at `/data/babylog.db`.

## Portainer deployment flow

1. Push this repository to GitHub.
2. In Portainer: **Stacks → Add stack → Repository**.
3. Select repository and branch.
4. Configure env vars and volume mapping.
5. Deploy stack.

## API

- `GET /api/data` returns intake and weight chart data in JSON.
