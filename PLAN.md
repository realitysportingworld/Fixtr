# CompApp — MVP Phase & Implementation Plan

---

## Phase 1 — Backend Core
**Goal:** Full competition lifecycle (league) working via API

| # | Task | Status |
|---|------|--------|
| 1.1 | Project setup, models, DB schema | ✅ Done |
| 1.2 | Alembic migrations configured | ✅ Done |
| 1.3 | Fixture generation (round-robin + knockout) | ✅ Done |
| 1.4 | Standings calculator | ✅ Done |
| 1.5 | Auth — register, login, JWT | ✅ Done |
| 1.6 | Competition endpoints (CRUD) | ✅ Done |
| 1.7 | Team endpoints | ✅ Done |
| 1.8 | Fixture endpoints (generate + list) | ✅ Done |
| 1.9 | Result endpoints (record + update) | ✅ Done |
| 1.10 | Standings endpoint | ✅ Done |

**Exit criteria:** Full competition lifecycle testable in Swagger UI (`/docs`)

---

## Phase 2 — Mobile Foundation
**Goal:** Working mobile app connected to the backend

| # | Task | Status |
|---|------|--------|
| 2.1 | Expo project setup | ✅ Done |
| 2.2 | Navigation structure (React Navigation) | ✅ Done |
| 2.3 | Auth screens (Login / Register) | ✅ Done |
| 2.4 | Home screen — list user's competitions | ✅ Done |
| 2.5 | Create competition screen | ✅ Done |
| 2.6 | Add teams screen | ✅ Done |
| 2.7 | Fixtures screen (list + schedule) | ✅ Done |
| 2.8 | Enter result screen | ✅ Done |
| 2.9 | Standings screen | ✅ Done |

**Exit criteria:** User can create a league, add teams, play through matches, and see standings on their phone

---

## Phase 3 — Competition Formats
**Goal:** All three formats fully working

| # | Task | Status |
|---|------|--------|
| 3.1 | Knockout bracket logic + API | ✅ Done |
| 3.2 | Group Stage logic + API | ✅ Done |
| 3.3 | Bracket visualization on mobile | ✅ Done |
| 3.4 | Group → knockout transition (top N teams advance) | ✅ Done |

---

## Phase 4 — Sport Scoring
**Goal:** Sport-specific scoring rules per competition

| # | Task | Status |
|---|------|--------|
| 4.1 | Configurable scoring system (JSON config per sport) | ✅ Done |
| 4.2 | Football, Basketball, Rugby, Golf scoring rules | ✅ Done |
| 4.3 | Custom scoring builder (user-defined rules) | ✅ Done |

---

## Phase 5 — Premium + Polish
**Goal:** Monetization, sharing, production-ready

| # | Task | Status |
|---|------|--------|
| 5.1 | Participant limit gate (free tier ≤ 32 teams) | ⬜ |
| 5.2 | RevenueCat subscription integration | ⬜ |
| 5.3 | Share competition (public read-only view) | ⬜ |
| 5.4 | Push notifications (match reminders) | ⬜ |
| 5.5 | App Store + Play Store submission | ⬜ |

---

## Implementation Notes

### Stack
- **Backend:** FastAPI + PostgreSQL (SQLAlchemy ORM, Alembic migrations)
- **Mobile:** React Native + Expo
- **Auth:** JWT (python-jose + passlib/bcrypt)

### Project Structure
```
comp_app/
├── venv/                        # Python virtual environment (project root)
├── requirements.txt
├── PLAN.md                      # This file
├── .gitignore
└── backend/
    ├── .env                     # Local config (never commit)
    ├── .env.example             # Template
    ├── alembic/                 # DB migrations
    ├── alembic.ini
    └── app/
        ├── main.py              # FastAPI entry point
        ├── core/config.py       # Settings
        ├── db/base.py           # DB engine + session
        ├── models/models.py     # SQLAlchemy models
        ├── schemas/             # Pydantic request/response schemas
        ├── api/v1/endpoints/    # Route handlers
        ├── services/
        │   ├── fixture_generator.py
        │   └── standings.py
        └── utils/
```

### Running the Backend
```bash
# From project root (comp_app/)
source venv/Scripts/activate        # Windows Git Bash
# OR
.\venv\Scripts\Activate.ps1         # Windows PowerShell

cd backend
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
```

### Running Migrations
```bash
source venv/Scripts/activate
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```
