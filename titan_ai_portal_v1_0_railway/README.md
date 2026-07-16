# Titan AI Portal v1.0 — Railway Edition

A GitHub-ready, Railway-ready web app for converting Ghana draughts videos into board positions, move lists and Titan training data.

## Included

- Password-protected admin portal
- Video upload and YouTube URL input
- Automatic board-corner detection with manual correction
- Mobile calibration interface
- Background video analysis
- Persistent SQLite job history
- Downloadable JSON, CSV and screenshots
- Docker and Railway deployment configuration
- Health check endpoint
- Configurable upload limit
- Persistent-data support through a Railway volume

## Deploy to Railway

### 1. Create a GitHub repository

Create an empty repository named:

```text
titan-ai-portal
```

Upload every file from this folder to the repository root.

### 2. Deploy from Railway

In Railway:

1. Select **GitHub Repository**.
2. Choose `titan-ai-portal`.
3. Railway will detect `railway.json` and the `Dockerfile`.
4. Add these variables:

```text
ADMIN_PASSWORD=choose-a-password
SESSION_SECRET=choose-a-long-random-secret
DATA_DIR=/data
MAX_UPLOAD_MB=500
```

### 3. Add persistent storage

In the Railway service:

1. Add a **Volume**.
2. Mount it at:

```text
/data
```

This preserves jobs and the SQLite database between deployments.

### 4. Generate a public domain

Open the service's **Networking** section and generate a Railway domain.

### Important

Video analysis is CPU-heavy. A trial or free allowance may work for short tests, but long matches can exhaust credits or memory. This version does not falsely claim perfect automatic recognition: it attempts automatic board detection, then lets you correct the corners and choose both marble colours.

## Local run

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.
