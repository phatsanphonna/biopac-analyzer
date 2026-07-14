import gzip
import io
import math
import types
from typing import Annotated, Any, Dict, List, Optional, Set
import numpy as np
import pandas as pd
import neurokit2 as nk
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import importlib.util
import sys
import os

# NumPy 2.4 removed this alias, but the supplied HRV module still uses it.
if not hasattr(np, "trapz"):
    setattr(np, "trapz", np.trapezoid)

# Dynamically import the Pan-Tompkins HRV analysis module.
hrv_module: Optional[types.ModuleType] = None
try:
    dir_path: str = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "hrv_module", os.path.join(dir_path, "ecg_hrv_pantompkins_gui.py")
    )
    if spec is not None and spec.loader is not None:
        hrv_module = importlib.util.module_from_spec(spec)
        sys.modules["hrv_module"] = hrv_module
        spec.loader.exec_module(hrv_module)
        print("Successfully imported ecg_hrv_pantompkins_gui.py dynamically.")
except Exception as e:
    print(f"Failed to dynamically import ecg_hrv_pantompkins_gui.py: {e}")

# Dynamically import "ECG_resp.py"
ecg_resp_module: Optional[types.ModuleType] = None
try:
    dir_path = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "ecg_resp_module", os.path.join(dir_path, "ECG_resp.py")
    )
    if spec is not None and spec.loader is not None:
        ecg_resp_module = importlib.util.module_from_spec(spec)
        sys.modules["ecg_resp_module"] = ecg_resp_module
        spec.loader.exec_module(ecg_resp_module)
        print("Successfully imported ECG_resp.py dynamically.")
except Exception as e:
    print(f"Failed to dynamically import ECG_resp.py: {e}")

app = FastAPI(title="BIOPAC Physiological Analysis Server")
MAX_CSV_BYTES: int = 50 * 1024 * 1024

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def safe_float(val: Any) -> float:
    """Gracefully handles NaNs/Infs for JSON compliance"""
    try:
        if val is None or math.isnan(float(val)) or math.isinf(float(val)):
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def decode_csv_upload(contents: bytes, filename: str) -> bytes:
    if filename.lower().endswith(".gz"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(contents)) as compressed:
                contents = compressed.read(MAX_CSV_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise HTTPException(status_code=400, detail="Invalid gzip file.") from exc

    if len(contents) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="Decompressed CSV is too large.")
    return contents


@app.post("/api/analyze")
async def analyze_file(file: Annotated[UploadFile, File()]) -> Dict[str, Any]:
    global hrv_module, ecg_resp_module
    if not file.filename or not file.filename.lower().endswith((".csv", ".csv.gz")):
        raise HTTPException(status_code=400, detail="Only CSV and CSV.GZ files are supported.")

    try:
        contents: bytes = decode_csv_upload(await file.read(), file.filename)
        df: pd.DataFrame = pd.read_csv(io.BytesIO(contents))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    # Column mapping logic
    cols: List[str] = [str(c).lower() for c in df.columns]

    # Locate time column
    time_col_idx: int = -1
    for i, col in enumerate(cols):
        if col in ["sec", "time", "seconds"]:
            time_col_idx = i
            break

    if time_col_idx == -1:
        raise HTTPException(
            status_code=400, detail="Could not find time column (sec/time) in CSV."
        )

    # Locate ECG column
    ecg_col_idx: int = -1
    for i, col in enumerate(cols):
        if col == "ch1" or "ecg" in col:
            ecg_col_idx = i
            break

    if ecg_col_idx == -1:
        raise HTTPException(
            status_code=400, detail="Could not find ECG column (CH1) in CSV."
        )

    # Locate Respiration column (optional, purely for plotting the raw signal)
    resp_col_idx: int = -1
    for i, col in enumerate(cols):
        if col == "ch2" or "resp" in col or "rsp" in col:
            resp_col_idx = i
            break

    # Extract raw arrays
    time_col_name: str = str(df.columns[time_col_idx])
    ecg_col_name: str = str(df.columns[ecg_col_idx])

    time_s: np.ndarray = pd.to_numeric(df[time_col_name], errors="coerce").dropna().values
    ecg_signal: np.ndarray = pd.to_numeric(df[ecg_col_name], errors="coerce").dropna().values

    # Clean up signal length matches
    min_len: int = min(len(time_s), len(ecg_signal))
    time_s = time_s[:min_len]
    ecg_signal = ecg_signal[:min_len]

    if min_len < 500:
        raise HTTPException(
            status_code=400,
            detail="Signal length is too short for physiological analysis.",
        )

    # Calculate sampling rate (FS)
    fs: int = int(round(1.0 / float(np.mean(np.diff(time_s)))))
    if fs <= 0:
        fs = 250  # fallback

    total_duration: float = float(time_s[-1] - time_s[0])

    # --- ECG Cleaning for visual chart ---
    ecg_clean: np.ndarray
    try:
        ecg_clean = nk.ecg_clean(ecg_signal, sampling_rate=fs, method="pantompkins1985")
    except Exception:
        try:
            ecg_clean = nk.ecg_clean(ecg_signal, sampling_rate=fs)
        except Exception:
            ecg_clean = ecg_signal.copy()

    # --- HRV and ECG R-Peak Detection ---
    peaks: List[int] = []
    avg_hr: float = 0.0
    mean_rr: float = 0.0
    min_hr: float = 0.0
    max_hr: float = 0.0
    sdnn: float = 0.0
    rmssd: float = 0.0
    pnn50: float = 0.0
    avg_resp_rate: float = 0.0
    lf: float = 0.0
    hf: float = 0.0
    lf_hf: float = 0.0
    lfnu: float = 0.0
    hfnu: float = 0.0
    total_power: float = 0.0
    resp_hz: float = 0.0
    instantaneous_hr: List[Dict[str, float]] = []

    if hrv_module is not None:
        try:
            # 1. Run the official extract_hrv routine
            feat: Dict[str, Any] = hrv_module.extract_hrv(ecg_signal, fs=fs)
            avg_hr = safe_float(feat.get("Mean_HR_bpm"))
            mean_rr = safe_float(feat.get("Mean_RR_ms"))
            sdnn = safe_float(feat.get("SDNN_ms"))
            rmssd = safe_float(feat.get("RMSSD_ms"))
            pnn50 = safe_float(feat.get("pNN50_percent"))

            # Detect R-peaks early so they are available for EDR respiration calculations
            peaks_arr: np.ndarray
            peaks_arr, _ = hrv_module.detect_r_peaks_pantompkins(ecg_clean, fs)
            peaks = [int(p) for p in peaks_arr]

            # Respiration Rate & RESP (Hz) using EDR consensus if CH2 is present
            resp_hz = 0.0
            avg_resp_rate = 0.0
            if resp_col_idx != -1:
                if ecg_resp_module is not None:
                    try:
                        # Extract R-peaks for EDR consensus calculation
                        rpeaks_for_edr: List[int] = ecg_resp_module.filter_rpeaks_by_rr(
                            peaks, fs, min_rr=0.3, max_rr=2.0
                        )

                        # 1. Peak-to-Trough EDR
                        ptt_time: np.ndarray
                        ptt_edr: np.ndarray
                        ptt_time, ptt_edr = ecg_resp_module.calculate_edr_peak_to_trough(
                            ecg_clean,
                            rpeaks_for_edr,
                            fs,
                            edr_fs=8,
                            low_bpm=3,
                            high_bpm=25,
                        )
                        ptt_welch_bpm: float
                        ptt_conf: float
                        ptt_welch_bpm, ptt_conf = ecg_resp_module.estimate_rate_welch_with_confidence(
                            ptt_edr, fs=8, low_bpm=3, high_bpm=25
                        )

                        # 2. QRS RMS EDR
                        rms_time: np.ndarray
                        rms_edr: np.ndarray
                        rms_point_time: np.ndarray
                        rms_points: np.ndarray
                        rms_time, rms_edr, rms_point_time, rms_points = ecg_resp_module.calculate_edr_qrs_rms(
                            ecg_clean,
                            rpeaks_for_edr,
                            fs,
                            edr_fs=8,
                            low_bpm=3,
                            high_bpm=25,
                        )
                        rms_welch_bpm: float
                        rms_conf: float
                        rms_welch_bpm, rms_conf = ecg_resp_module.estimate_rate_welch_with_confidence(
                            rms_edr, fs=8, low_bpm=3, high_bpm=25
                        )

                        # 3. Roberts-style EDR
                        roberts_time: np.ndarray
                        roberts_rr: np.ndarray
                        roberts_final_rr: float
                        roberts_time, roberts_rr, roberts_final_rr = ecg_resp_module.estimate_rr_roberts_style(
                            ecg_clean,
                            rpeaks_for_edr,
                            fs,
                            low_bpm=3,
                            high_bpm=25,
                            heartbeat_window=32,
                            median_smooth_window=16,
                            fft_length=512,
                        )

                        # Calculate consensus respiration rate
                        consensus_rr: float
                        consensus_method: Any
                        consensus_diff: float
                        pair_1: Any
                        pair_2: Any
                        (
                            consensus_rr,
                            consensus_method,
                            consensus_diff,
                            pair_1,
                            pair_2,
                        ) = ecg_resp_module.consensus_resp_rate(
                            {
                                "PeakToTrough_Welch": ptt_welch_bpm,
                                "QRS_RMS_Welch": rms_welch_bpm,
                                "Roberts_RMS_FFT": roberts_final_rr,
                            },
                            max_pair_diff=3.0,
                        )

                        if not np.isnan(consensus_rr):
                            avg_resp_rate = float(consensus_rr)
                        else:
                            # fallback to first non-NaN EDR estimate
                            valid_vals: List[float] = [
                                v
                                for v in [
                                    ptt_welch_bpm,
                                    rms_welch_bpm,
                                    roberts_final_rr,
                                ]
                                if not np.isnan(v)
                            ]
                            avg_resp_rate = (
                                float(valid_vals[0]) if len(valid_vals) > 0 else 0.0
                            )

                        resp_hz = avg_resp_rate / 60.0
                    except Exception as e:
                        print(f"Failed to calculate EDR consensus: {e}")
                        avg_resp_rate = safe_float(feat.get("Exploratory_EDR_rate_bpm"))
                        resp_hz = avg_resp_rate / 60.0 if avg_resp_rate > 0 else 0.0
                else:
                    avg_resp_rate = safe_float(feat.get("Exploratory_EDR_rate_bpm"))
                    resp_hz = avg_resp_rate / 60.0 if avg_resp_rate > 0 else 0.0
            else:
                avg_resp_rate = 0.0
                resp_hz = 0.0

            lf = safe_float(feat.get("LF_power_ms2"))
            hf = safe_float(feat.get("HF_power_ms2"))
            lf_hf = safe_float(feat.get("LF_HF_ratio"))
            lfnu = safe_float(feat.get("LFnu_percent"))
            hfnu = safe_float(feat.get("HFnu_percent"))
            total_power = safe_float(feat.get("Total_power_ms2"))

            # 2. Get peaks and RR series for plotting
            # Get filtered RR intervals to reconstruct instantaneous heart rate timeline
            rr: np.ndarray
            rr_times: np.ndarray
            rr, _, rr_times = hrv_module.compute_rr_intervals(peaks_arr, fs)
            rr_valid: np.ndarray
            rr_times_valid: np.ndarray
            rr_valid, rr_times_valid, _ = hrv_module.filter_rr_intervals(
                rr, rr_times, min_rr=0.3, max_rr=2.0
            )

            for t_point, rr_val in zip(rr_times_valid, rr_valid):
                instantaneous_hr.append(
                    {"time": float(t_point), "hr": float(60.0 / rr_val)}
                )
        except Exception as e:
            print(
                f"Failed calling hrv_module: {e}. Falling back to standard processing."
            )
            hrv_module = None  # trigger fallback

    # Fallback to NeuroKit2 standard processing if hrv_module is missing or fails
    if hrv_module is None:
        try:
            info: Dict[str, Any]
            _, info = nk.ecg_peaks(ecg_clean, sampling_rate=fs)
            peaks = [int(p) for p in info["ECG_R_Peaks"]]
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"R-peak detection failed: {str(e)}"
            )

        if len(peaks) < 3:
            raise HTTPException(
                status_code=400, detail="Detected too few R-peaks to compute HRV."
            )

        peaks_arr = np.asarray(peaks, dtype=int)
        r_times = time_s[peaks_arr]
        rr_s: np.ndarray = np.diff(r_times)
        rr_t: np.ndarray = (r_times[:-1] + r_times[1:]) / 2.0
        rr_ms: np.ndarray = rr_s * 1000.0

        valid_mask: np.ndarray = (rr_ms >= 300) & (rr_ms <= 2000)
        rr_t_filtered: np.ndarray = rr_t[valid_mask]
        rr_ms_filtered: np.ndarray = rr_ms[valid_mask]

        if len(rr_ms_filtered) > 0:
            avg_hr = float(60000.0 / float(np.mean(rr_ms_filtered)))
            mean_rr = float(np.mean(rr_ms_filtered))
            sdnn = (
                float(np.std(rr_ms_filtered, ddof=1))
                if len(rr_ms_filtered) > 1
                else 0.0
            )
            diff_rr: np.ndarray = np.diff(rr_ms_filtered)
            if len(diff_rr) > 0:
                rmssd = float(np.sqrt(float(np.mean(diff_rr**2))))
                nn50: int = int(np.sum(np.abs(diff_rr) > 50))
                pnn50 = float((nn50 / len(diff_rr)) * 100)
            for t_point, rr_val in zip(rr_t_filtered, rr_ms_filtered):
                instantaneous_hr.append(
                    {"time": float(t_point), "hr": float(60000.0 / rr_val)}
                )

    # Compute min/max heart rate from the timeline
    if len(instantaneous_hr) > 0:
        hrs: List[float] = [pt["hr"] for pt in instantaneous_hr]
        min_hr = float(np.min(hrs))
        max_hr = float(np.max(hrs))

    # Optional respiration reading purely for visual charting
    has_resp: bool = resp_col_idx != -1
    resp_signal: Optional[np.ndarray] = None
    if has_resp:
        resp_col_name: str = str(df.columns[resp_col_idx])
        resp_signal = (
            pd.to_numeric(df[resp_col_name], errors="coerce").dropna().values[:min_len]
        )

    # --- Subsampling for UI charting ---
    target_points: int = 1500
    step: int = max(1, len(ecg_signal) // target_points)

    chart_data: List[Dict[str, Any]] = []
    peak_set: Set[int] = set(peaks)

    for i in range(0, len(ecg_signal), step):
        is_peak: bool = False
        for j in range(step):
            if i + j in peak_set:
                is_peak = True
                break

        t_val: float = float(time_s[i])
        e_val: float = float(ecg_clean[i])
        r_val: float = float(resp_signal[i]) if has_resp and resp_signal is not None else 0.0

        chart_data.append(
            {"time": t_val, "ecg": e_val, "resp": r_val, "isPeak": is_peak}
        )

    return {
        "fileName": file.filename or "unknown",
        "duration": float(total_duration),
        "sampleRate": int(fs),
        "avgHeartRate": int(round(avg_hr, 0)),
        "avgRespRate": float(round(avg_resp_rate, 0)),
        "meanRR": int(round(mean_rr, 0)),
        "minHR": int(round(min_hr, 0)),
        "maxHR": int(round(max_hr, 0)),
        "sdnn": float(round(sdnn, 1)),
        "rmssd": float(round(rmssd, 1)),
        "pnn50": float(round(pnn50, 1)),
        "rsaMs": 0.0,  # RSA is omitted for HRV-only execution
        "lf": float(round(lf, 1)),
        "hf": float(round(hf, 1)),
        "lfHf": float(round(lf_hf, 2)),
        "lfnu": float(round(lfnu, 1)),
        "hfnu": float(round(hfnu, 1)),
        "totalPower": float(round(total_power, 1)),
        "respHz": float(round(resp_hz, 3)),
        "instantaneousHR": instantaneous_hr,
        "chartData": chart_data,
    }


# Resolve the frontend/dist folder path
frontend_dist_dir: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)

# Mount the assets folder under /assets prefix if it exists
if os.path.exists(os.path.join(frontend_dist_dir, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_dir, "assets")), name="assets")

# Catch-all endpoint to serve the React frontend (index.html, favicons, static files, etc.)
@app.get("/{file_name:path}")
async def serve_frontend(file_name: str) -> Any:
    # Check if the requested file exists in frontend_dist_dir
    file_path: str = os.path.join(frontend_dist_dir, file_name)
    if file_name and os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Fallback to index.html for SPA routing
    index_path: str = os.path.join(frontend_dist_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    raise HTTPException(
        status_code=404, 
        detail="Frontend build files not found. Please run 'pnpm build' in the frontend directory."
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
