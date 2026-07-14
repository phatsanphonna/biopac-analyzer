# BIOPAC Analyzer

A physiological signal analysis dashboard that extracts Heart Rate Variability (HRV) indices (both Time-Domain and Frequency-Domain) and estimates respiration rates from BIOPAC CSV files. 

---

## Project Directory Structure
```text
biopac-analyzer/
├── analyzer/                  # Python FastAPI Backend
│   ├── server.py              # Main API server & Static file mounting
│   ├── ECG_resp.py            # ECG-Derived Respiration (EDR) calculations
│   ├── HRV_parameters.py       # Custom HRV features parser (R-peak, time/freq metrics)
│   ├── RSA.py                 # Respiratory Sinus Arrhythmia coupling calculations
│   ├── pyproject.toml         # Python project dependency configuration
│   └── uv.lock                # Python lockfile
│
└── frontend/                  # React + TypeScript Frontend
    ├── src/
    │   ├── components/react/  # Single-responsibility visual components
    │   ├── lib/               # Local JS/TS signal engine fallback logic
    │   └── App.tsx            # App router, uploader, & state coordinators
    ├── vite.config.ts         # Vite configuration with API developer proxies
    ├── package.json           # Node configuration
    └── pnpm-lock.yaml         # Node lockfile
```

---

## Prerequisites
Ensure the following tools are installed on your machine:
- **Node.js** (v18+) & **pnpm** (preferred package manager)
- **Python** (3.10+) & **uv** (for fast Python package installation and environment isolation)

---

## How to Build & Run

### 1. Developer Mode (Separate Servers with Hot-Reload)
Runs frontend hot-reloading on port `5173` and proxies all API requests transparently to the backend on port `8000`.

1. **Start the Python Backend Server**:
   ```bash
   cd analyzer
   uv run python server.py
   ```
   *This will resolve environment dependencies automatically and start the server at `http://localhost:8000`.*

2. **Start the React Frontend Dev Server**:
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```
   *This starts the hot-reloading dev environment at `http://localhost:5173`.*

---

### 2. Production Mode (Unified Single-Port Server)
Compiles frontend assets into static files and serves them directly from FastAPI on port `8000`.

1. **Build the Frontend Assets**:
   ```bash
   cd frontend
   pnpm install
   pnpm build
   ```
   *This compiles the React files into static assets under `frontend/dist/`.*

2. **Run the FastAPI Server**:
   ```bash
   cd analyzer
   uv run python server.py
   ```

3. **Verify**:
   Open [http://localhost:8000](http://localhost:8000) in your browser. The entire application (both UI and API endpoints) will run on port `8000`.
