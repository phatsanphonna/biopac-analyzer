# Desktop Development Guidelines

This repository is a focused, offline PySide6 desktop ECG/HRV analyzer. Do not restore the retired browser or server implementation.

## File responsibilities

- `analyzer/ecg_hrv_pantompkins_gui.py` is the preserved scientific baseline. Keep it byte-for-byte unchanged unless a task explicitly requests a baseline change.
- `analyzer/desktop_analysis.py` is the GUI-independent adapter. Keep `METHODS`, `PARAMETERS`, `AnalysisContext`, `AnalysisResult`, `load_recording()`, `analyze_recording()`, and CSV export compatible.
- `analyzer/desktop_app.py` owns PySide6 widgets and the entry point. Long analysis must stay off the GUI thread; workers communicate with widgets only through signals.
- `analyzer/test_desktop.py` contains focused loading, method, schema, export, and worker checks.
- Preserve the tracked sample recording, existing result CSVs, PDFs, and notes.

## Conventions

- Fully annotate new Python code and prefer specific NumPy/Python types over `Any`.
- Keep scientific calculations in the adapter or baseline, not in Qt slots.
- All widget access stays on the main thread. Use the existing QObject/QThread worker pattern for expensive work.
- Keep input validation at CSV and export boundaries.
- Do not add dependencies when the standard library, NumPy, pandas, SciPy, NeuroKit2, or PySide6 already covers the need.
- Exported local reports belong at `analyzer/*_hrv.csv` and must remain untracked.

## Required verification

Run from `analyzer/` before completion:

```bash
uv lock --check
uv run python -m py_compile ecg_hrv_pantompkins_gui.py desktop_analysis.py desktop_app.py test_desktop.py
uv run mypy --ignore-missing-imports desktop_analysis.py desktop_app.py
uv run python -m unittest -v test_desktop.py
uv run python desktop_app.py --smoke-test
```

For packaging changes, also build with PyInstaller and run the generated executable with `--smoke-test`. Remove local `build/`, `dist/`, and `.spec` output afterward.
