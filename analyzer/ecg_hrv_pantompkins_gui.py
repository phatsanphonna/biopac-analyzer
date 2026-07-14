import numpy as np
import pandas as pd

from scipy.signal import find_peaks, hilbert, welch, detrend
from scipy.interpolate import interp1d

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

try:
    import neurokit2 as nk
except ImportError:
    nk = None


# ===========================================================
# Configuration
# ===========================================================

ECG_METHOD = "pantompkins1985"
DEFAULT_FS = 250


# ===========================================================
# Utilities
# ===========================================================

def safe_nan_features():
    """Return all output columns with NaN values when the segment is too short or invalid."""
    keys = [
        # Segment / preprocessing / R peak QC
        "duration_sec",
        "ecg_method",
        "sampling_rate_Hz",
        "r_peak_count",
        "rr_count_raw",
        "rr_count_valid",
        "rr_removed_count",
        "rr_removed_percent",
        "mean_r_peak_amplitude_cleaned",
        "std_r_peak_amplitude_cleaned",

        # Time-domain HRV
        "Mean_RR_ms",
        "Median_RR_ms",
        "Mean_HR_bpm",
        "Mean_inst_HR_bpm",
        "Min_HR_bpm",
        "Max_HR_bpm",
        "HR_range_bpm",
        "SDNN_ms",
        "RMSSD_ms",
        "SDSD_ms",
        "NN50",
        "pNN50_percent",
        "CVRR",
        "RR_IQR_ms",

        # Frequency-domain HRV
        "VLF_power_ms2",
        "LF_power_ms2",
        "HF_power_ms2",
        "Total_power_ms2",
        "LF_HF_ratio",
        "LFnu_percent",
        "HFnu_percent",
        "LF_peak_Hz",
        "HF_peak_Hz",

        # Nonlinear / Poincare
        "SD1_ms",
        "SD2_ms",
        "SD1_SD2_ratio",
        "ApEn",
        "SampEn",

        # Exploratory auxiliary ECG features
        "Exploratory_EDR_rate_Hz",
        "Exploratory_EDR_rate_bpm",
        "Exploratory_EDR_variability_sec",
        "EECG_mean",
        "EECG_std",
        "mean_RR_decrease_ms",
        "mean_RR_increase_ms",
    ]
    return {k: np.nan for k in keys}


def sanitize_ecg(ecg):
    """
    Convert ECG to float and fill missing values without changing the signal length.
    Dropping NaN samples changes timing, so interpolation is safer for ECG/HRV.
    """
    s = pd.Series(ecg, dtype="float64")
    s = s.replace([np.inf, -np.inf], np.nan)

    if s.isna().all():
        return np.array([], dtype=float)

    s = s.interpolate(method="linear", limit_direction="both")
    s = s.ffill().bfill()
    return s.to_numpy(dtype=float)


# ===========================================================
# ECG Cleaning and R-peak detection
# ===========================================================

def clean_ecg_pantompkins(ecg, fs=DEFAULT_FS):
    """
    ECG preprocessing using the Pan-Tompkins 1985 cleaning option in NeuroKit2.
    NeuroKit2 implements this cleaning as a 5-15 Hz band-pass filter.
    """
    if nk is None:
        raise ImportError(
            "neurokit2 is not installed. Please install it with: pip install neurokit2"
        )

    ecg = sanitize_ecg(ecg)
    if len(ecg) == 0:
        return ecg, ecg

    ecg_cleaned = nk.ecg_clean(
        ecg,
        sampling_rate=fs,
        method=ECG_METHOD
    )
    return ecg, np.asarray(ecg_cleaned, dtype=float)


def detect_r_peaks_pantompkins(ecg_cleaned, fs=DEFAULT_FS, correct_artifacts=True):
    """
    Detect R peaks using the Pan-Tompkins 1985 method in NeuroKit2.

    correct_artifacts=True keeps Pan-Tompkins as the detector, then asks NeuroKit2
    to correct obvious peak artifacts before RR/HRV calculation.
    """
    if nk is None:
        raise ImportError(
            "neurokit2 is not installed. Please install it with: pip install neurokit2"
        )

    if len(ecg_cleaned) == 0:
        return np.array([], dtype=int), {}

    signals, info = nk.ecg_peaks(
        ecg_cleaned,
        sampling_rate=fs,
        #method=ECG_METHOD,
        correct_artifacts=correct_artifacts
    )

    r_peaks = np.asarray(info.get("ECG_R_Peaks", []), dtype=int)
    r_peaks = r_peaks[(r_peaks >= 0) & (r_peaks < len(ecg_cleaned))]
    return r_peaks, info


# ===========================================================
# RR interval processing
# ===========================================================

def compute_rr_intervals(r_peaks, fs=DEFAULT_FS):
    """
    Convert R-peak sample positions to RR intervals.

    Output:
        rr: RR intervals in seconds
        r_times: R-peak times in seconds
        rr_times: midpoint time of each RR interval in seconds
    """
    r_peaks = np.asarray(r_peaks, dtype=int)
    r_times = r_peaks / fs
    rr = np.diff(r_times)
    rr_times = r_times[:-1] + rr / 2
    return rr, r_times, rr_times


def filter_rr_intervals(rr, rr_times, min_rr=0.3, max_rr=2.0, use_robust_filter=True):
    """
    Filter implausible NN/RR intervals before HRV calculation.

    min_rr=0.3 and max_rr=2.0 correspond approximately to 200 bpm and 30 bpm.
    A robust MAD filter is also applied to remove extreme interval artifacts.
    """
    rr = np.asarray(rr, dtype=float)
    rr_times = np.asarray(rr_times, dtype=float)

    valid = (~np.isnan(rr)) & (~np.isnan(rr_times))
    valid &= (rr >= min_rr) & (rr <= max_rr)

    if use_robust_filter and np.sum(valid) >= 8:
        rr_candidate = rr[valid]
        med = np.median(rr_candidate)
        mad = np.median(np.abs(rr_candidate - med))

        # If MAD is too small, avoid over-removing physiologic variability.
        if mad > 0:
            robust_sd = 1.4826 * mad
            robust_limit = max(0.25, 4.0 * robust_sd)  # seconds
            robust_valid = np.abs(rr - med) <= robust_limit
            valid &= robust_valid

    rr_valid = rr[valid]
    rr_times_valid = rr_times[valid]
    return rr_valid, rr_times_valid, valid


# ===========================================================
# HRV feature calculation
# ===========================================================

def time_domain_hrv(rr):
    """Calculate time-domain HRV features from valid NN/RR intervals in seconds."""
    feat = {}
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < 3:
        return {
            "Mean_RR_ms": np.nan,
            "Median_RR_ms": np.nan,
            "Mean_HR_bpm": np.nan,
            "Mean_inst_HR_bpm": np.nan,
            "Min_HR_bpm": np.nan,
            "Max_HR_bpm": np.nan,
            "HR_range_bpm": np.nan,
            "SDNN_ms": np.nan,
            "RMSSD_ms": np.nan,
            "SDSD_ms": np.nan,
            "NN50": np.nan,
            "pNN50_percent": np.nan,
            "CVRR": np.nan,
            "RR_IQR_ms": np.nan,
        }

    diff_rr = np.diff(rr)
    diff_rr_ms = diff_rr * 1000
    inst_hr = 60 / rr

    nn50 = int(np.sum(np.abs(diff_rr_ms) > 50))
    pnn50 = nn50 / len(diff_rr_ms) * 100 if len(diff_rr_ms) > 0 else np.nan

    feat.update({
        "Mean_RR_ms": np.mean(rr) * 1000,
        "Median_RR_ms": np.median(rr) * 1000,
        "Mean_HR_bpm": 60 / np.mean(rr),
        "Mean_inst_HR_bpm": np.mean(inst_hr),
        "Min_HR_bpm": np.min(inst_hr),
        "Max_HR_bpm": np.max(inst_hr),
        "HR_range_bpm": np.ptp(inst_hr),
        "SDNN_ms": np.std(rr, ddof=1) * 1000,
        "RMSSD_ms": np.sqrt(np.mean(diff_rr ** 2)) * 1000,
        "SDSD_ms": np.std(diff_rr, ddof=1) * 1000 if len(diff_rr) > 1 else np.nan,
        "NN50": nn50,
        "pNN50_percent": pnn50,
        "CVRR": np.std(rr, ddof=1) / np.mean(rr),
        "RR_IQR_ms": (np.percentile(rr, 75) - np.percentile(rr, 25)) * 1000,
    })
    return feat


def frequency_domain_hrv(rr, rr_times, interp_fs=4.0):
    """
    Frequency-domain HRV using interpolated NN intervals and Welch PSD.

    RR is converted from seconds to milliseconds before PSD integration, so
    band powers are reported as ms^2.
    """
    nan_feat = {
        "VLF_power_ms2": np.nan,
        "LF_power_ms2": np.nan,
        "HF_power_ms2": np.nan,
        "Total_power_ms2": np.nan,
        "LF_HF_ratio": np.nan,
        "LFnu_percent": np.nan,
        "HFnu_percent": np.nan,
        "LF_peak_Hz": np.nan,
        "HF_peak_Hz": np.nan,
    }

    rr = np.asarray(rr, dtype=float)
    rr_times = np.asarray(rr_times, dtype=float)

    valid = (~np.isnan(rr)) & (~np.isnan(rr_times))
    rr = rr[valid]
    rr_times = rr_times[valid]

    # Frequency-domain HRV is unstable for very short recordings.
    if len(rr) < 10 or (rr_times[-1] - rr_times[0]) < 30:
        return nan_feat

    sort_idx = np.argsort(rr_times)
    rr_times = rr_times[sort_idx]
    rr_ms = rr[sort_idx] * 1000

    unique_times, unique_idx = np.unique(rr_times, return_index=True)
    rr_times = unique_times
    rr_ms = rr_ms[unique_idx]

    if len(rr_ms) < 10:
        return nan_feat

    t_interp = np.arange(rr_times[0], rr_times[-1], 1 / interp_fs)
    if len(t_interp) < 16:
        return nan_feat

    kind = "cubic" if len(rr_ms) >= 4 else "linear"
    interp_func = interp1d(
        rr_times,
        rr_ms,
        kind=kind,
        bounds_error=False,
        fill_value="extrapolate"
    )

    rr_interp = interp_func(t_interp)
    rr_interp = detrend(rr_interp, type="linear")

    nperseg = min(len(rr_interp), int(300 * interp_fs))
    if nperseg < 16:
        return nan_feat

    freqs, psd = welch(
        rr_interp,
        fs=interp_fs,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend=False
    )

    vlf_band = (freqs >= 0.0033) & (freqs < 0.04)
    lf_band = (freqs >= 0.04) & (freqs < 0.15)
    hf_band = (freqs >= 0.15) & (freqs < 0.40)
    total_band = (freqs >= 0.0033) & (freqs < 0.40)

    def band_power(band):
        if np.sum(band) < 2:
            return np.nan
        return np.trapezoid(psd[band], freqs[band])

    vlf = band_power(vlf_band)
    lf = band_power(lf_band)
    hf = band_power(hf_band)
    total_power = band_power(total_band)

    lf_hf = lf / hf if not np.isnan(hf) and hf > 0 else np.nan
    denom = lf + hf
    lfnu = lf / denom * 100 if not np.isnan(denom) and denom > 0 else np.nan
    hfnu = hf / denom * 100 if not np.isnan(denom) and denom > 0 else np.nan

    lf_peak = freqs[lf_band][np.argmax(psd[lf_band])] if np.sum(lf_band) >= 1 else np.nan
    hf_peak = freqs[hf_band][np.argmax(psd[hf_band])] if np.sum(hf_band) >= 1 else np.nan

    return {
        "VLF_power_ms2": vlf,
        "LF_power_ms2": lf,
        "HF_power_ms2": hf,
        "Total_power_ms2": total_power,
        "LF_HF_ratio": lf_hf,
        "LFnu_percent": lfnu,
        "HFnu_percent": hfnu,
        "LF_peak_Hz": lf_peak,
        "HF_peak_Hz": hf_peak,
    }


def poincare_hrv(rr):
    """Calculate Poincare plot features SD1 and SD2 from valid RR intervals."""
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < 3:
        return {
            "SD1_ms": np.nan,
            "SD2_ms": np.nan,
            "SD1_SD2_ratio": np.nan,
        }

    diff_rr = np.diff(rr)
    sdnn = np.std(rr, ddof=1)
    sdsd = np.std(diff_rr, ddof=1) if len(diff_rr) > 1 else np.nan

    sd1 = np.sqrt(0.5) * sdsd
    sd2_sq = 2 * (sdnn ** 2) - 0.5 * (sdsd ** 2)
    sd2 = np.sqrt(sd2_sq) if sd2_sq > 0 else np.nan

    return {
        "SD1_ms": sd1 * 1000 if not np.isnan(sd1) else np.nan,
        "SD2_ms": sd2 * 1000 if not np.isnan(sd2) else np.nan,
        "SD1_SD2_ratio": sd1 / sd2 if not np.isnan(sd1) and not np.isnan(sd2) and sd2 > 0 else np.nan,
    }


def approximate_entropy(rr, m=2, r_ratio=0.2):
    """Approximate Entropy, ApEn, calculated from RR intervals in seconds."""
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < m + 2:
        return np.nan

    r = r_ratio * np.std(rr, ddof=0)
    N = len(rr)
    if r == 0:
        return np.nan

    def _phi(order):
        x = np.array([rr[i:i + order] for i in range(N - order + 1)])
        C = np.sum(
            np.max(np.abs(x[:, None] - x[None, :]), axis=2) <= r,
            axis=1
        )
        C = C / (N - order + 1)
        C = C[C > 0]
        if len(C) == 0:
            return np.nan
        return np.mean(np.log(C))

    phi_m = _phi(m)
    phi_m1 = _phi(m + 1)

    if np.isnan(phi_m) or np.isnan(phi_m1):
        return np.nan
    return phi_m - phi_m1


def sample_entropy(rr, m=2, r_ratio=0.2):
    """Sample Entropy, SampEn, calculated from RR intervals in seconds."""
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < m + 3:
        return np.nan

    r = r_ratio * np.std(rr, ddof=0)
    N = len(rr)
    if r == 0:
        return np.nan

    def _count_matches(order):
        x = np.array([rr[i:i + order] for i in range(N - order + 1)])
        count = 0
        for i in range(len(x) - 1):
            dist = np.max(np.abs(x[i + 1:] - x[i]), axis=1)
            count += np.sum(dist <= r)
        return count

    B = _count_matches(m)
    A = _count_matches(m + 1)

    if B == 0 or A == 0:
        return np.nan
    return -np.log(A / B)


def nonlinear_hrv(rr):
    """Calculate nonlinear HRV features."""
    return {
        "ApEn": approximate_entropy(rr),
        "SampEn": sample_entropy(rr),
    }


# ===========================================================
# Auxiliary ECG-derived features
# ===========================================================

def compute_exploratory_edr(ecg_cleaned, r_peaks, r_times):
    """
    Exploratory R-amplitude-based ECG-derived respiration feature.
    This is kept only as an auxiliary feature, not a formal respiration method.
    """
    if len(r_peaks) < 3:
        return np.nan, np.nan

    r_amps = ecg_cleaned[r_peaks]
    edr = r_amps - np.mean(r_amps)

    edr_peaks, _ = find_peaks(edr, distance=3)
    if len(edr_peaks) < 2:
        return np.nan, np.nan

    intervals = np.diff(r_times[edr_peaks])
    if len(intervals) == 0 or np.mean(intervals) <= 0:
        return np.nan, np.nan

    edr_rate_hz = 1 / np.mean(intervals)
    edr_var_sec = np.std(intervals, ddof=1) if len(intervals) > 1 else np.nan
    return edr_rate_hz, edr_var_sec


def compute_eecg(ecg_cleaned):
    """ECG envelope feature using Hilbert transform. Auxiliary ECG feature, not standard HRV."""
    if len(ecg_cleaned) == 0:
        return np.nan, np.nan
    env = np.abs(hilbert(ecg_cleaned))
    return np.mean(env), np.std(env, ddof=1)


def acceleration_deceleration_capacity_simple(rr):
    """
    Simple RR increase/decrease feature.
    This is not the formal Bauer PRSA AC/DC method.
    """
    rr = np.asarray(rr, dtype=float)
    if len(rr) < 3:
        return np.nan, np.nan

    diff_rr = np.diff(rr)
    acc = diff_rr[diff_rr < 0]
    dec = diff_rr[diff_rr > 0]

    mean_rr_decrease = -np.mean(acc) if len(acc) else np.nan
    mean_rr_increase = np.mean(dec) if len(dec) else np.nan
    return mean_rr_decrease, mean_rr_increase


# ===========================================================
# Main extraction function
# ===========================================================

def extract_hrv(ecg, fs=DEFAULT_FS, correct_artifacts=True):
    """
    Whole-segment ECG HRV analysis.

    Pipeline:
        raw ECG
        -> ECG cleaning using Pan-Tompkins 1985 method
        -> R-peak detection using Pan-Tompkins 1985 method
        -> RR interval calculation
        -> RR interval artifact filtering
        -> HRV feature calculation
    """
    feat = safe_nan_features()
    feat["ecg_method"] = ECG_METHOD
    feat["sampling_rate_Hz"] = fs

    raw_ecg, ecg_cleaned = clean_ecg_pantompkins(ecg, fs=fs)
    feat["duration_sec"] = len(raw_ecg) / fs if fs else np.nan

    if len(ecg_cleaned) < int(5 * fs):
        return feat

    r_peaks, peak_info = detect_r_peaks_pantompkins(
        ecg_cleaned,
        fs=fs,
        correct_artifacts=correct_artifacts
    )

    rr_raw, r_times, rr_times = compute_rr_intervals(r_peaks, fs=fs)
    rr_valid, rr_times_valid, valid_mask = filter_rr_intervals(
        rr_raw,
        rr_times,
        min_rr=0.3,
        max_rr=2.0,
        use_robust_filter=True
    )

    feat.update({
        "r_peak_count": len(r_peaks),
        "rr_count_raw": len(rr_raw),
        "rr_count_valid": len(rr_valid),
        "rr_removed_count": len(rr_raw) - len(rr_valid),
        "rr_removed_percent": ((len(rr_raw) - len(rr_valid)) / len(rr_raw) * 100) if len(rr_raw) > 0 else np.nan,
    })

    if len(r_peaks) > 0:
        r_amp = ecg_cleaned[r_peaks]
        feat["mean_r_peak_amplitude_cleaned"] = np.mean(r_amp)
        feat["std_r_peak_amplitude_cleaned"] = np.std(r_amp, ddof=1) if len(r_amp) > 1 else np.nan

    if len(rr_valid) < 3:
        return feat

    feat.update(time_domain_hrv(rr_valid))
    feat.update(frequency_domain_hrv(rr_valid, rr_times_valid, interp_fs=4.0))
    feat.update(poincare_hrv(rr_valid))
    feat.update(nonlinear_hrv(rr_valid))

    edr_rate, edr_var = compute_exploratory_edr(ecg_cleaned, r_peaks, r_times)
    feat["Exploratory_EDR_rate_Hz"] = edr_rate
    feat["Exploratory_EDR_rate_bpm"] = edr_rate * 60 if not np.isnan(edr_rate) else np.nan
    feat["Exploratory_EDR_variability_sec"] = edr_var

    e_mean, e_std = compute_eecg(ecg_cleaned)
    feat["EECG_mean"] = e_mean
    feat["EECG_std"] = e_std

    rr_dec, rr_inc = acceleration_deceleration_capacity_simple(rr_valid)
    feat["mean_RR_decrease_ms"] = rr_dec * 1000 if not np.isnan(rr_dec) else np.nan
    feat["mean_RR_increase_ms"] = rr_inc * 1000 if not np.isnan(rr_inc) else np.nan

    return feat


# ===========================================================
# Batch / GUI helpers
# ===========================================================

def analyze_csv(path, fs=DEFAULT_FS, ecg_column="CH1"):
    df = pd.read_csv(path)

    if ecg_column not in df.columns:
        raise ValueError(f"CSV must contain '{ecg_column}' as the ECG column.")

    ecg = pd.to_numeric(df[ecg_column], errors="coerce").values
    feat = extract_hrv(ecg, fs=fs, correct_artifacts=True)

    out_df = pd.DataFrame([feat])
    out_path = path.replace(".csv", "_pantompkins1985_hrv_features.csv")
    out_df.to_csv(out_path, index=False, na_rep="NaN")
    return out_path, feat


# ===========================================================
# GUI App
# ===========================================================

class App:
    def __init__(self, root):
        root.title("ECG HRV Feature Extractor - Pan-Tompkins 1985")
        root.geometry("860x540")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="Sampling rate Hz:").pack(side="left")
        self.fs_var = tk.StringVar(value=str(DEFAULT_FS))
        ttk.Entry(top, textvariable=self.fs_var, width=8).pack(side="left", padx=6)

        ttk.Label(top, text="ECG column:").pack(side="left", padx=(16, 0))
        self.col_var = tk.StringVar(value="CH1")
        ttk.Entry(top, textvariable=self.col_var, width=10).pack(side="left", padx=6)

        ttk.Button(top, text="Select CSV", command=self.run).pack(side="left", padx=12)

        self.logbox = tk.Text(root, height=26)
        self.logbox.pack(fill="both", expand=True, padx=12, pady=8)

        self.log("Ready.")
        self.log("Pipeline: ECG clean -> Pan-Tompkins 1985 R peaks -> RR intervals -> HRV features")

    def log(self, msg):
        self.logbox.insert("end", str(msg) + "\n")
        self.logbox.see("end")

    def run(self):
        if nk is None:
            messagebox.showerror(
                "Missing package",
                "neurokit2 is not installed. Please run:\n\npip install neurokit2"
            )
            return

        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return

        try:
            fs = int(float(self.fs_var.get()))
            ecg_column = self.col_var.get().strip() or "CH1"

            out_path, feat = analyze_csv(path, fs=fs, ecg_column=ecg_column)

            self.log("\n✔ Finished ECG HRV analysis")
            self.log(f"Method: {ECG_METHOD}")
            self.log(f"Saved to: {out_path}")
            self.log("")
            self.log("Quality / count outputs:")
            self.log(f"duration_sec: {feat.get('duration_sec')}")
            self.log(f"r_peak_count: {feat.get('r_peak_count')}")
            self.log(f"rr_count_valid: {feat.get('rr_count_valid')}")
            self.log(f"rr_removed_percent: {feat.get('rr_removed_percent')}")
            self.log("")
            self.log("Main HRV outputs:")
            self.log(f"Mean_HR_bpm: {feat.get('Mean_HR_bpm')}")
            self.log(f"SDNN_ms: {feat.get('SDNN_ms')}")
            self.log(f"RMSSD_ms: {feat.get('RMSSD_ms')}")
            self.log(f"LF_power_ms2: {feat.get('LF_power_ms2')}")
            self.log(f"HF_power_ms2: {feat.get('HF_power_ms2')}")
            self.log(f"LF_HF_ratio: {feat.get('LF_HF_ratio')}")
            self.log(f"SD1_ms: {feat.get('SD1_ms')}")
            self.log(f"SD2_ms: {feat.get('SD2_ms')}")
            self.log(f"SampEn: {feat.get('SampEn')}")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log(f"✘ Error: {e}")


# ===========================================================
# Entry
# ===========================================================

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
