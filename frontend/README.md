# MedBox — React + Vite

A full rebuild of the original static MedBox mockup as a real, interactive
React + Vite app. It keeps the original teal/mint/lime visual identity and
voice-first concept, then gives it real state, real routing, and real data.

## Run it

Sign-in/create-account now goes through the real FastAPI backend (JWT
auth), so **both** servers must be running at the same time:

```bash
# Terminal 1 — backend (from the project root, the parent of backend/)
python run_backend.py
# or: ./run_backend.sh

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Then open the printed local URL (the frontend's dev server proxies
`/api/*` to `http://localhost:8000`, so no separate `.env` is needed
for email/password sign-in to work). `npm run build` produces a
production build in `dist/` — note that build has no dev proxy, so a
deployed build needs `VITE_API_BASE`-style config or a reverse proxy
in front of the FastAPI backend for `/api` calls to resolve.

Two ready-made accounts exist after the backend's first run (seeded by
`backend/seed.py`):
- `maya.lin@medbox.health` / `securePass123` (primary user)
- `dr.jenkins@medbox.health` / `caregiverPass123` (caregiver)

**Google sign-in** requires your own Firebase project — see
`frontend/.env.example` for the five-minute setup. Without it, the
"Continue with Google" button shows an honest error instead of
faking a login; email/password sign-in works either way.

## What's in here

- **React Router** — `/`, `/scan`, `/schedule`, `/library`, `/caregiver`,
  `/safety`, each a real page instead of a hidden modal.
- **Zustand + localStorage** — medicines, dose logs, and settings persist
  across refreshes. No backend required for the demo.
- **Voice** — `useSpeech` wraps the real `SpeechRecognition` and
  `speechSynthesis` Web APIs when the browser supports them, and falls
  back to a short simulated "listening" state otherwise.
- **Scan flow** — a simulated camera viewfinder with a scanning-line
  animation, a randomized match from a small identification database, and
  a confirm-before-save dialog, matching the product's "we never guess"
  promise.
- **Schedule** — a real 7-day strip (3 days back, today, 3 days ahead),
  per-day dose lists, and a live progress bar.
- **Library** — full CRUD: add, edit, delete, search, and filter your
  medicines, with an accessible modal form.
- **Caregiver dashboard** — a `recharts` adherence bar chart, streak and
  missed-dose stats, computed live from the dose logs.
- **Accessibility settings** — text size, high-contrast mode, and reduced
  motion, all wired to real CSS and respected by `framer-motion`.
- **Design** — Manrope + DM Mono, a deep navy/teal palette with mint/lime/
  coral accents, varied corner radii (circular orb, soft cards, pill
  chips, squared data rows) rather than one repeated shape.

## Structure

```
src/
  components/   Layout, Modal, ToastHost, VoiceOrb, DoseRing, MedicineCard, AdherenceChart, SettingsSheet
  pages/        Home, Scan, Schedule, Library, Caregiver, Safety, NotFound
  store/        useStore.js (zustand)
  hooks/        useSpeech.js
  data/         seed.js
  utils/        time.js
```
