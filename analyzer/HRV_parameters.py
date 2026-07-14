import numpy as np
import pandas as pd

from scipy.signal import find_peaks, hilbert, welch, detrend
from scipy.interpolate import interp1d

# ===========================================================
# ECG / HRV
# ===========================================================

def detect_r_peaks(ecg, fs=250):
    """
    Simple R-peak detection.
    ecg: ECG signal
    fs: sampling rate
    """
    ecg = np.asarray(ecg, dtype=float)

    peaks, _ = find_peaks(
        ecg,
        distance=int(0.3 * fs),          # minimum RR interval = 0.3 s, about 200 bpm
        prominence=np.std(ecg) * 0.5     # simple dynamic threshold
    )

    return peaks


def compute_rr_intervals(r_peaks, fs):
    """
    Convert R peaks to RR intervals.
    rr unit: seconds
    r_times unit: seconds
    """
    r_times = r_peaks / fs
    rr = np.diff(r_times)
    return rr, r_times


def filter_rr_intervals(rr, r_times, min_rr=0.3, max_rr=2.0):
    """
    Simple RR filtering.
    Keep RR intervals between min_rr and max_rr.
    rr: seconds
    r_times: seconds
    """
    rr = np.asarray(rr, dtype=float)
    r_times = np.asarray(r_times, dtype=float)

    valid_mask = (rr >= min_rr) & (rr <= max_rr)

    rr_valid = rr[valid_mask]

    # RR interval midpoint time, used for frequency-domain interpolation
    rr_times = r_times[:-1] + rr / 2
    rr_times_valid = rr_times[valid_mask]

    return rr_valid, rr_times_valid, valid_mask


def compute_EDR(ecg, r_peaks, r_times):
    """
    Simple R-amplitude based ECG-derived respiration.
    Output:
        EDR_rate_Hz
        EDR_variability_sec

    Note:
    This is a simplified EDR method, not QRS RMS / QRS P2T formal method.
    """
    if len(r_peaks) < 3:
        return np.nan, np.nan

    r_amps = ecg[r_peaks]
    edr = r_amps - np.mean(r_amps)

    # distance=3 means at least 3 beats apart, not seconds
    edr_peaks, _ = find_peaks(edr, distance=3)

    if len(edr_peaks) < 2:
        return np.nan, np.nan

    intervals = np.diff(r_times[edr_peaks])

    if len(intervals) == 0 or np.mean(intervals) <= 0:
        return np.nan, np.nan

    edr_rate_hz = 1 / np.mean(intervals)
    edr_var_sec = np.std(intervals, ddof=1) if len(intervals) > 1 else np.nan

    return edr_rate_hz, edr_var_sec


def compute_EECG(ecg):
    """
    ECG envelope feature using Hilbert transform.
    This is not a standard HRV metric, just an auxiliary ECG feature.
    """
    env = np.abs(hilbert(ecg))
    return np.mean(env), np.std(env)


def acceleration_deceleration_capacity_simple(rr):
    """
    Simple RR increase/decrease feature.
    Note:
    This is NOT the formal Bauer PRSA AC/DC method.
    """
    diff_rr = np.diff(rr)

    acc = diff_rr[diff_rr < 0]   # RR decreases, HR accelerates
    dec = diff_rr[diff_rr > 0]   # RR increases, HR decelerates

    mean_rr_decrease = -np.mean(acc) if len(acc) else np.nan
    mean_rr_increase = np.mean(dec) if len(dec) else np.nan

    return mean_rr_decrease, mean_rr_increase


def approximate_entropy(rr, m=2, r_ratio=0.2):
    """
    Approximate Entropy, ApEn.
    rr unit: seconds
    """
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < m + 2:
        return np.nan

    r = r_ratio * np.std(rr, ddof=0)
    N = len(rr)

    if r == 0:
        return np.nan

    def _phi(m):
        x = np.array([rr[i:i + m] for i in range(N - m + 1)])
        C = np.sum(
            np.max(np.abs(x[:, None] - x[None, :]), axis=2) <= r,
            axis=1
        )
        C = C / (N - m + 1)

        # avoid log(0)
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
    """
    Sample Entropy, SampEn.
    rr unit: seconds
    """
    rr = np.asarray(rr, dtype=float)
    rr = rr[~np.isnan(rr)]

    if len(rr) < m + 3:
        return np.nan

    r = r_ratio * np.std(rr, ddof=0)
    N = len(rr)

    if r == 0:
        return np.nan

    def _count_matches(m):
        x = np.array([rr[i:i + m] for i in range(N - m + 1)])
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


def frequency_domain_hrv(rr, rr_times, interp_fs=4.0):
    """
    Frequency-domain HRV using Welch PSD.

    rr: RR intervals in seconds
    rr_times: time of each RR interval, usually midpoint time, in seconds
    interp_fs: interpolation frequency, default 4 Hz

    Output:
        LF_power_ms2
        HF_power_ms2
        LF_HF_ratio
        LFnu_percent
        HFnu_percent
        Total_power_ms2
        LF_peak_Hz
        HF_peak_Hz
    """

    rr = np.asarray(rr, dtype=float)
    rr_times = np.asarray(rr_times, dtype=float)

    valid = (~np.isnan(rr)) & (~np.isnan(rr_times))
    rr = rr[valid]
    rr_times = rr_times[valid]

    if len(rr) < 10 or len(rr_times) < 10:
        return {
            "LF_power_ms2": np.nan,
            "HF_power_ms2": np.nan,
            "LF_HF_ratio": np.nan,
            "LFnu_percent": np.nan,
            "HFnu_percent": np.nan,
            "Total_power_ms2": np.nan,
            "LF_peak_Hz": np.nan,
            "HF_peak_Hz": np.nan,
        }

    # RR convert to ms. After PSD integration, unit becomes ms^2.
    rr_ms = rr * 1000

    # sort by time
    sort_idx = np.argsort(rr_times)
    rr_times = rr_times[sort_idx]
    rr_ms = rr_ms[sort_idx]

    # remove duplicate time points
    unique_times, unique_idx = np.unique(rr_times, return_index=True)
    rr_times = unique_times
    rr_ms = rr_ms[unique_idx]

    if len(rr_ms) < 10:
        return {
            "LF_power_ms2": np.nan,
            "HF_power_ms2": np.nan,
            "LF_HF_ratio": np.nan,
            "LFnu_percent": np.nan,
            "HFnu_percent": np.nan,
            "Total_power_ms2": np.nan,
            "LF_peak_Hz": np.nan,
            "HF_peak_Hz": np.nan,
        }

    # Interpolation time base
    t_interp = np.arange(rr_times[0], rr_times[-1], 1 / interp_fs)

    if len(t_interp) < 16:
        return {
            "LF_power_ms2": np.nan,
            "HF_power_ms2": np.nan,
            "LF_HF_ratio": np.nan,
            "LFnu_percent": np.nan,
            "HFnu_percent": np.nan,
            "Total_power_ms2": np.nan,
            "LF_peak_Hz": np.nan,
            "HF_peak_Hz": np.nan,
        }

    # Use cubic interpolation if enough points, otherwise linear
    kind = "cubic" if len(rr_ms) >= 4 else "linear"

    interp_func = interp1d(
        rr_times,
        rr_ms,
        kind=kind,
        bounds_error=False,
        fill_value="extrapolate"
    )

    rr_interp = interp_func(t_interp)

    # Detrend after interpolation
    rr_interp = detrend(rr_interp, type="linear")

    # Welch window: max 300 s, similar to common HRV setting
    nperseg = min(len(rr_interp), int(300 * interp_fs))

    if nperseg < 16:
        return {
            "LF_power_ms2": np.nan,
            "HF_power_ms2": np.nan,
            "LF_HF_ratio": np.nan,
            "LFnu_percent": np.nan,
            "HFnu_percent": np.nan,
            "Total_power_ms2": np.nan,
            "LF_peak_Hz": np.nan,
            "HF_peak_Hz": np.nan,
        }

    freqs, psd = welch(
        rr_interp,
        fs=interp_fs,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend=False
    )

    # Standard HRV bands
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

    if np.sum(lf_band) >= 1:
        lf_peak = freqs[lf_band][np.argmax(psd[lf_band])]
    else:
        lf_peak = np.nan

    if np.sum(hf_band) >= 1:
        hf_peak = freqs[hf_band][np.argmax(psd[hf_band])]
    else:
        hf_peak = np.nan

    return {
        "LF_power_ms2": lf,
        "HF_power_ms2": hf,
        "LF_HF_ratio": lf_hf,
        "LFnu_percent": lfnu,
        "HFnu_percent": hfnu,
        "Total_power_ms2": total_power,
        "LF_peak_Hz": lf_peak,
        "HF_peak_Hz": hf_peak,
    }


def extract_hrv(ecg, fs=250):
    """
    Whole-segment HRV analysis.
    One CSV -> one row of features.
    """

    ecg = np.asarray(ecg, dtype=float)
    ecg = ecg[~np.isnan(ecg)]

    r_peaks = detect_r_peaks(ecg, fs)
    rr, r_times = compute_rr_intervals(r_peaks, fs)

    rr_valid, rr_times_valid, valid_mask = filter_rr_intervals(
        rr,
        r_times,
        min_rr=0.3,
        max_rr=2.0
    )

    feat = {
        "duration_sec": len(ecg) / fs,
        "r_peak_count_raw": len(r_peaks),
        "rr_count_raw": len(rr),
        "rr_count_valid": len(rr_valid),
        "rr_removed_count": len(rr) - len(rr_valid),
    }

    if len(rr_valid) < 3:
        feat.update({
            "Mean_RR_ms": np.nan,
            "Mean_HR_bpm": np.nan,
            "Mean_inst_HR_bpm": np.nan,
            "SDNN_ms": np.nan,
            "RMSSD_ms": np.nan,
            "NN50": np.nan,
            "pNN50_percent": np.nan,
            "CVRR": np.nan,
            "HR_range_bpm": np.nan,
            "EDR_rate_Hz": np.nan,
            "EDR_rate_bpm": np.nan,
            "EDR_variability_sec": np.nan,
            "EECG_mean": np.nan,
            "EECG_std": np.nan,
            "mean_RR_decrease_ms": np.nan,
            "mean_RR_increase_ms": np.nan,
            "LF_power_ms2": np.nan,
            "HF_power_ms2": np.nan,
            "LF_HF_ratio": np.nan,
            "LFnu_percent": np.nan,
            "HFnu_percent": np.nan,
            "Total_power_ms2": np.nan,
            "LF_peak_Hz": np.nan,
            "HF_peak_Hz": np.nan,
            "ApEn": np.nan,
            "SampEn": np.nan,
        })
        return feat

    diff_rr = np.diff(rr_valid)
    diff_rr_ms = diff_rr * 1000

    nn50 = np.sum(np.abs(diff_rr_ms) > 50)
    pnn50 = nn50 / len(diff_rr_ms) * 100 if len(diff_rr_ms) > 0 else np.nan

    feat.update({
        "Mean_RR_ms": np.mean(rr_valid) * 1000,
        "Mean_HR_bpm": 60 / np.mean(rr_valid),
        "Mean_inst_HR_bpm": np.mean(60 / rr_valid),
        "SDNN_ms": np.std(rr_valid, ddof=1) * 1000,
        "RMSSD_ms": np.sqrt(np.mean(diff_rr ** 2)) * 1000,
        "NN50": nn50,
        "pNN50_percent": pnn50,
        "CVRR": np.std(rr_valid, ddof=1) / np.mean(rr_valid),
        "HR_range_bpm": np.ptp(60 / rr_valid),
    })

    # Simple EDR from R-peak amplitude
    edr_rate, edr_var = compute_EDR(ecg, r_peaks, r_times)
    feat["EDR_rate_Hz"] = edr_rate
    feat["EDR_rate_bpm"] = edr_rate * 60 if not np.isnan(edr_rate) else np.nan
    feat["EDR_variability_sec"] = edr_var

    # ECG envelope features
    e_mean, e_std = compute_EECG(ecg)
    feat["EECG_mean"] = e_mean
    feat["EECG_std"] = e_std

    # Simple RR increase/decrease feature
    rr_dec, rr_inc = acceleration_deceleration_capacity_simple(rr_valid)
    feat["mean_RR_decrease_ms"] = rr_dec * 1000 if not np.isnan(rr_dec) else np.nan
    feat["mean_RR_increase_ms"] = rr_inc * 1000 if not np.isnan(rr_inc) else np.nan

    # Frequency-domain HRV
    fd_feat = frequency_domain_hrv(rr_valid, rr_times_valid, interp_fs=4.0)
    feat.update(fd_feat)

    # Nonlinear HRV
    feat["ApEn"] = approximate_entropy(rr_valid)
    feat["SampEn"] = sample_entropy(rr_valid)

    return feat


# ===========================================================
# GUI App
# ===========================================================

class App:
    def __init__(self, root):
        root.title("Whole-segment ECG HRV Feature Extractor")
        root.geometry("760x460")

        ttk.Button(root, text="Select CSV", command=self.run).pack(pady=20)

        self.logbox = tk.Text(root, height=20)
        self.logbox.pack(fill="both", expand=True)

    def log(self, msg):
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")

    def run(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return

        df = pd.read_csv(path)

        if "CH1" not in df.columns:
            messagebox.showerror("Error", "CSV must contain CH1 (ECG)")
            return

        fs = 250

        ecg = pd.to_numeric(df["CH1"], errors="coerce").dropna().values

        feat = extract_hrv(ecg, fs=fs)

        out_df = pd.DataFrame([feat])
        out_path = path.replace(".csv", "_whole_segment_hrv_features.csv")
        out_df.to_csv(out_path, index=False, na_rep="NaN")

        self.log("✔ Finished whole-segment HRV analysis")
        self.log(f"Saved to:\n{out_path}")
        self.log("")
        self.log("Main outputs:")
        self.log(f"SDNN_ms: {feat.get('SDNN_ms')}")
        self.log(f"RMSSD_ms: {feat.get('RMSSD_ms')}")
        self.log(f"LF_power_ms2: {feat.get('LF_power_ms2')}")
        self.log(f"HF_power_ms2: {feat.get('HF_power_ms2')}")
        self.log(f"LF_HF_ratio: {feat.get('LF_HF_ratio')}")
        self.log(f"LFnu_percent: {feat.get('LFnu_percent')}")
        self.log(f"HFnu_percent: {feat.get('HFnu_percent')}")
        self.log(f"SampEn: {feat.get('SampEn')}")


# ===========================================================
# Entry
# ===========================================================

if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    App(root)
    root.mainloop()
