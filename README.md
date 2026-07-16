# BIOPAC HRV Analyzer

Offline PySide6 desktop software for analyzing ECG recordings exported from BIOPAC as `.csv` or `.csv.gz` files. It supports Pan–Tompkins 1985 and NeuroKit ECG pipelines, displays HRV metrics, and exports one-row CSV reports.

## Run

Install [Python 3.10+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/), then:

```bash
cd analyzer
uv sync --all-groups
uv run python desktop_app.py
```

Choose a recording, confirm the detected time/ECG columns and sampling rate, select a method, and analyze. Exported reports default to `analyzer/<recording>_hrv.csv`.

## Project layout

- `analyzer/desktop_analysis.py` — GUI-independent loading, analysis, metric registry, and CSV export.
- `analyzer/desktop_app.py` — PySide6 application and background analysis worker.
- `analyzer/ecg_hrv_pantompkins_gui.py` — preserved scientific baseline; do not modify during desktop maintenance.
- `analyzer/test_desktop.py` — focused desktop unit tests.
- `analyzer/LB-0411-01.csv` — tracked BIOPAC sample recording.
- `.github/workflows/desktop-build.yml` — Windows x64 and Apple Silicon builds.
- `report.pdf`, `s13428-020-01392-6.pdf`, and `notes.txt` — retained research material.

## Verify

Run from `analyzer/`:

```bash
uv lock --check
uv run python -m py_compile ecg_hrv_pantompkins_gui.py desktop_analysis.py desktop_app.py test_desktop.py
uv run mypy --ignore-missing-imports desktop_analysis.py desktop_app.py
uv run python -m unittest -v test_desktop.py
uv run python desktop_app.py --smoke-test
```

## Package

Local PyInstaller build:

```bash
cd analyzer
uv run pyinstaller --noconfirm --clean --onedir --windowed --name BIOPAC-HRV-Analyzer desktop_app.py
```

The `Desktop builds` GitHub Actions workflow produces unsigned Windows x64 and Apple Silicon ZIP artifacts. Windows may show SmartScreen; macOS may require explicit first-open approval.
