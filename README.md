# 🎼 Orchestra

A durable workflow orchestrator you run, not just a tool you configure. Define a DAG of tasks, hand it to Orchestra, and it schedules, retries, and — if a worker or server crashes mid-task — resumes exactly where things left off. No duplicate side effects, no lost work, no manual cleanup.

![Orchestra Score View](https://img.shields.io/badge/Orchestra-Durable%20DAG%20Engine-C9A24B?style=for-the-badge)
![Vercel Ready](https://img.shields.io/badge/Vercel-Free%20Tier%20Ready-000000?style=for-the-badge&logo=vercel)
![Python FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![React Flow](https://img.shields.io/badge/React%20Flow-Score%20View-6FA287?style=for-the-badge)
![Postgres](https://img.shields.io/badge/Postgres-SKIP%20LOCKED-4169E1?style=for-the-badge&logo=postgresql)

---

## 💡 Why Orchestra?

Job postings ask for *"distributed task processing," "idempotency," "DAG execution,"* and *"crash recovery"* as if they were simple checkboxes. Almost nobody has actually built the engine behind those words — they've configured Celery, or written a cron job, and called it done. 

**Orchestra is the engine itself**: the scheduler, the durable state store, the retry policy, and the recovery logic, watched live as it runs on a musical staff dashboard.

---

## ✨ Key Features

- 🎼 **The Score View**: Renders the DAG as a 5-line musical staff. Tasks are rendered as circular musical notes (`brass` = active, `sage` = succeeded, `brick` = failed with a hairline crack), connected by curved slur arcs.
- ⚡ **Baton Sweep**: A live vertical baton line sweeps across the staff driven by real-time state events.
- 🔒 **Exactly-Once Task Claiming**: Powered by Postgres `SELECT ... FOR UPDATE SKIP LOCKED` — two workers or serverless invocations never race or double-claim the same task.
- 🛡️ **Durable State Machine**: Every state transition (`pending → claimed → running → checkpointing → succeeded | failed`) is persisted to Postgres before any side-effect is allowed to matter.
- 🔄 **Idempotent Step Checkpointing**: Tasks record intermediate step checkpoints. If killed mid-task, Orchestra resumes from the last recorded checkpoint rather than re-running from step zero.
- 🎞️ **Deterministic Replay Debugger**: Scrub backward and forward through a finished run step-by-step to inspect exact inputs, outputs, and intermediate states.
- 🔀 **Score Diffing**: Compare two runs of the same workflow side-by-side to highlight structural and output differences.
- ⚡ **Rehearsal (Chaos) Mode**: One-click chaos toggle to expire worker leases live on command to demonstrate crash recovery.
- 📜 **Tamper-Evident Audit Log**: Every state transition is appended to a SHA-256 hash-chain table where each row's hash incorporates the previous row's hash.

---

## 🛠️ Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **API & Scheduler** | FastAPI (Python) | Async-native, typed, seamless serverless support on Vercel |
| **Durable State** | Postgres (Supabase / Neon / Local) | `SELECT ... FOR UPDATE SKIP LOCKED` for zero-overhead task locking |
| **Realtime Updates** | WebSockets + HTTP Polling Fallback | Live events when self-hosted; automatic polling fallback on Vercel Serverless |
| **Frontend** | React + Vite + React Flow | Custom canvas rendering with concert-hall visual theme |
| **Design System** | Concert-Hall Dark Theme | Named palette (`ink`, `wine`, `ivory`, `brass`, `sage`, `brick`) with `Fraunces` & `IBM Plex Mono` fonts |
| **Hosting** | Vercel (Free Tier Ready) | Hosts both Frontend (SPA) & Backend (Serverless Functions) in a single repo |

---

## 🌐 Repository Recommendation: Public or Private?

> [!IMPORTANT]
> ### Recommended: **PUBLIC Repository**
> **Why?** Orchestra is designed as a high-caliber portfolio project to demonstrate your deep understanding of distributed systems, durable state machines, crash recovery, and rich frontend architecture to recruiters, team leads, and interviewers.
> 
> **Security Checklist for Public Repositories:**
> 1. Never commit `.env` files containing real database passwords or JWT secrets.
> 2. Keep `.env.example` committed with placeholder values.
> 3. Configure production secrets directly in your Vercel Environment Variables dashboard.

---

## 🚀 One-Click Deployment on Vercel (Free Tier)

Orchestra is pre-configured to host **both Frontend and FastAPI Backend on Vercel's Free Tier** using a cloud Postgres database (such as Supabase or Neon).

### Step 1: Set up a Free Cloud Postgres Database
1. Create a free Postgres database on **[Supabase](https://supabase.com)** or **[Neon](https://neon.tech)**.
2. Copy your connection URI (e.g. `postgresql://postgres:password@ep-xyz.us-east-1.aws.neon.tech/neondb?sslmode=require`).

### Step 2: Push Repository to GitHub
```bash
git init
git add .
git commit -m "Initial Orchestra release"
git branch -M main
git remote add origin https://github.com/your-username/orchestra.git
git push -u origin main
```

### Step 3: Deploy to Vercel
1. Log in to [Vercel](https://vercel.com) and click **"Add New Project"**.
2. Select your `orchestra` GitHub repository.
3. Under **Environment Variables**, add:
   - `DATABASE_URL`: Your Supabase/Neon asyncpg URL (e.g., `postgresql+asyncpg://postgres:...@.../postgres?sslmode=require`)
   - `DATABASE_URL_SYNC`: Your Supabase/Neon psycopg2 URL (e.g., `postgresql+psycopg2://postgres:...@.../postgres?sslmode=require`)
   - `JWT_SECRET`: A long random secret string (e.g., `super-secret-jwt-key-production-12345`)
   - `ENVIRONMENT`: `production`
4. Click **Deploy**. Vercel will automatically build the React frontend and deploy the FastAPI serverless functions!

### Step 4: Run Initial Database Migration
From your local terminal, run Alembic against your cloud database:
```bash
cd backend
DATABASE_URL="postgresql+asyncpg://user:pass@host/db" uv run alembic upgrade head
```

---

## 💻 Local Development Setup

### Prerequisites
- Python 3.11+ & `uv` (or `pip`)
- Node.js 18+ & `npm`
- Docker & Docker Compose (for local Postgres)

### 1. Clone & Environment
```bash
git clone https://github.com/your-username/orchestra.git
cd orchestra
cp backend/.env.example backend/.env
```

### 2. Start Local Postgres Database
```bash
docker compose up -d db
```

### 3. Run Backend Migrations & API
```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn orchestra.api:app --reload
```

### 4. Start Worker Process (in a new terminal)
```bash
cd backend
uv run orchestra-worker
```

### 5. Start Frontend (in a new terminal)
```bash
cd frontend
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser!

---

## 🔑 Demo Credentials

| Role | Username | Password | Capabilities |
|---|---|---|---|
| **Admin** | `admin` | `admin123` | Full access, version publishing, chaos controls |
| **Operator** | `operator` | `op123` | Trigger runs, retry/skip tasks, pause/resume |
| **Viewer** | `viewer` | `view123` | Read-only Score View & Replay Debugger |

---

## 📄 License

MIT License. Designed with ❤️ for engineers who appreciate durable systems.
