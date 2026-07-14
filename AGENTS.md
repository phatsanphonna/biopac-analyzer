# Developer Agents Directory Rules & Guidelines

This document outlines workspace conventions, module definitions, styling policies, and build verification checks for AI agents collaborating on the BIOPAC Physiological Analyzer codebase.

---

## 1. Directory Structure & File Responsibilities

- **`analyzer/` (Backend Service)**:
  - **`server.py`**: The primary FastAPI application. It is fully type-annotated (`mypy` compliant) and handles file validation, signal subsampling, and static asset serving. Keep imports clean and type annotations strict.
  - **`ECG_resp.py`**: ECG-Derived Respiration (EDR) calculations. Contains Welch PSD estimators and bandpass filters. Keep consensus calculations decoupled from router logic.
  - **`HRV_parameters.py`**: Core research script. It is dynamically loaded by `server.py` using `importlib` spec configurations.
  - **`RSA.py`**: Respiratory Sinus Arrhythmia calculations.

- **`frontend/` (Client Interface)**:
  - **`src/App.tsx`**: Manages state, API execution, and local processing fallbacks. All API queries should target relative endpoints (e.g. `/api/analyze`) rather than hardcoded URLs.
  - **`src/components/react/`**: Single-responsibility card interfaces:
    - **`DiagnosticSummary.tsx`**: Renders Time-Domain HRV parameters. Max HR metrics and descriptive headers should not be included.
    - **`FrequencySummary.tsx`**: Renders Frequency-Domain HRV parameters. Includes the estimated `RESP` frequency in Hz.
  - **`src/lib/signalProcessor.ts`**: The client-side fallback JavaScript/TypeScript engine. It must mirror backend return schemas exactly to prevent rendering crashes if the Python server is offline.

---

## 2. Coding Conventions

### Backend (Python)
- **Typing**: Keep all python functions and variables fully type-annotated. Avoid returning generic `Any` when a specific type (e.g., `np.ndarray`, `Dict[str, float]`) is available.
- **Dynamic Imports**: Use `importlib.util` for files containing spaces or special characters in their filenames.
- **Safe Floats**: Always wrap values returned in JSON responses in `safe_float` to sanitize `NaN`/`Inf` float errors before sending them to the client.

### Frontend (React + TypeScript)
- **Styling**: Use Vanilla CSS / Tailwind CSS matching existing cards patterns. Do not introduce bloated custom layout libraries.
- **No Placeholder Components**: Avoid rendering unused charts, navigation bars, or badge icons.
- **Relative Fetching**: All requests to the backend must use relative paths (e.g. `/api/...`). Vite is configured to proxy local requests from port `5173` to `8000` during development.

---

## 3. Verification & Compliance Checks

Before marking any task as complete, you must run and verify:

1. **Backend Syntax Check**:
   ```bash
   uv run python -m py_compile server.py
   ```
2. **Backend Type Integrity**:
   ```bash
   uv run mypy --ignore-missing-imports server.py
   ```
   *Mypy must return `Success: no issues found`.*
3. **Frontend Compilation**:
   ```bash
   pnpm --filter frontend build
   ```
   *The compilation must run to completion and output assets inside `frontend/dist/` without type errors.*
