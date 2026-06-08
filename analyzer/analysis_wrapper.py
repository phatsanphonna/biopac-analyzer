import os
import io
import base64
import numpy as np
import pandas as pd
import neurokit2 as nk
import scipy
from scipy.interpolate import CubicSpline, PchipInterpolator, interp1d
from scipy.signal import butter, filtfilt, welch, find_peaks, detrend

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server
import matplotlib.pyplot as plt

# =========================
# HELPER FUNCTIONS
# =========================

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return f"data:image/png;base64,{img_str}"

def safe_bandpass(x, fs, low_hz, high_hz, order=2):
    x = np.asarray(x, dtype=float)
    nyq = fs / 2
    low = low_hz / nyq
    high = high_hz / nyq
    if low <= 0: low = 0.001
    if high >= 1: high = 0.99
    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, x)

def filter_rpeaks_by_rr(rpeaks, fs, min_rr=0.3, max_rr=2.0):
    rpeaks = np.asarray(rpeaks, dtype=int)
    if len(rpeaks) < 3:
        return rpeaks
    rr = np.diff(rpeaks) / fs
    valid = np.ones(len(rpeaks), dtype=bool)
    bad_rr = (rr < min_rr) | (rr > max_rr)
    valid[1:][bad_rr] = False
    return rpeaks[valid]

def estimate_rate_welch_with_confidence(signal, fs, low_bpm=3, high_bpm=25):
    if signal is None:
        return np.nan, np.nan
    signal = np.asarray(signal, dtype=float)
    signal = signal[~np.isnan(signal)]
    if len(signal) < fs * 30:
        return np.nan, np.nan
    signal = signal - np.mean(signal)
    if np.std(signal) == 0:
        return np.nan, np.nan
    freqs, psd = welch(
        signal,
        fs=fs,
        nperseg=min(len(signal), int(fs * 60)),
        nfft=int(fs * 200)
    )
    low_hz = low_bpm / 60
    high_hz = high_bpm / 60
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    if np.sum(mask) == 0:
        return np.nan, np.nan
    band_freqs = freqs[mask]
    band_psd = psd[mask]
    if np.sum(band_psd) <= 0:
        return np.nan, np.nan
    peak_idx = np.argmax(band_psd)
    dom_freq = band_freqs[peak_idx]
    resp_rate_bpm = dom_freq * 60
    confidence = band_psd[peak_idx] / np.sum(band_psd)
    return resp_rate_bpm, confidence

def consensus_resp_rate(values, max_pair_diff=3.0):
    valid = {}
    for k, v in values.items():
        try:
            v = float(v)
            if not np.isnan(v):
                valid[k] = v
        except:
            pass
    if len(valid) == 0:
        return np.nan, "No valid estimate", np.nan, "", ""
    if len(valid) == 1:
        name = list(valid.keys())[0]
        value = list(valid.values())[0]
        return value, f"Only {name}", np.nan, name, ""
    names = list(valid.keys())
    vals = list(valid.values())
    best_diff = np.inf
    best_pair = None
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            diff = abs(vals[i] - vals[j])
            if diff < best_diff:
                best_diff = diff
                best_pair = (names[i], names[j], vals[i], vals[j])
    name1, name2, val1, val2 = best_pair
    if best_diff <= max_pair_diff:
        final_rr = np.mean([val1, val2])
        method = f"Average of closest pair: {name1} + {name2}"
        return final_rr, method, best_diff, name1, name2
    else:
        return np.nan, "No agreement between methods", best_diff, name1, name2

# =========================
# EDR METHODS
# =========================

def calculate_edr_peak_to_trough(ecg_signal, rpeaks, fs, edr_fs=8, low_bpm=3, high_bpm=25):
    if len(rpeaks) < 4:
        return None, None
    qrs_amps = []
    valid_rpeaks = []
    window = int(0.08 * fs)
    for r in rpeaks:
        start = max(0, r - window)
        end = min(len(ecg_signal), r + window + 1)
        segment = ecg_signal[start:end]
        if len(segment) > 3:
            amplitude = np.max(segment) - np.min(segment)
            qrs_amps.append(amplitude)
            valid_rpeaks.append(r)
    qrs_amps = np.asarray(qrs_amps, dtype=float)
    valid_rpeaks = np.asarray(valid_rpeaks, dtype=int)
    if len(qrs_amps) < 4:
        return None, None
    time_peaks = valid_rpeaks / fs
    clipped_amps = qrs_amps.copy()
    total_time = len(ecg_signal) / fs
    window_sec = 30
    for start_t in np.arange(0, total_time, window_sec):
        end_t = start_t + window_sec
        idx = (time_peaks >= start_t) & (time_peaks < end_t)
        if np.sum(idx) >= 3:
            mean_val = np.mean(qrs_amps[idx])
            std_val = np.std(qrs_amps[idx])
            lower = mean_val - 2 * std_val
            upper = mean_val + 2 * std_val
            clipped_amps[idx] = np.clip(qrs_amps[idx], lower, upper)
    try:
        cs = CubicSpline(time_peaks, clipped_amps)
        time_edr = np.arange(time_peaks[0], time_peaks[-1], 1 / edr_fs)
        edr_interpolated = cs(time_edr)
    except Exception:
        return None, None
    if len(edr_interpolated) < edr_fs * 30:
        return None, None
    try:
        edr_filtered = safe_bandpass(
            edr_interpolated,
            fs=edr_fs,
            low_hz=low_bpm / 60,
            high_hz=high_bpm / 60,
            order=3
        )
    except Exception:
        return None, None
    return time_edr, edr_filtered

def calculate_edr_qrs_rms(ecg_signal, rpeaks, fs, edr_fs=8, low_bpm=3, high_bpm=25):
    if len(rpeaks) < 20:
        return None, None, None, None
    try:
        qrs_ecg = safe_bandpass(ecg_signal, fs=fs, low_hz=8, high_hz=40, order=2)
    except Exception:
        qrs_ecg = ecg_signal.copy()
    qrs_rms = []
    valid_rpeaks = []
    pre = int(0.04 * fs)
    post = int(0.04 * fs)
    for r in rpeaks:
        start = r - pre
        end = r + post + 1
        if start < 0 or end > len(qrs_ecg):
            continue
        segment = qrs_ecg[start:end]
        segment = segment - np.mean(segment)
        rms = np.sqrt(np.mean(segment ** 2))
        qrs_rms.append(rms)
        valid_rpeaks.append(r)
    qrs_rms = np.asarray(qrs_rms, dtype=float)
    valid_rpeaks = np.asarray(valid_rpeaks, dtype=int)
    if len(qrs_rms) < 20:
        return None, None, None, None
    time_peaks = valid_rpeaks / fs
    qrs_rms_smooth = pd.Series(qrs_rms).rolling(
        window=16,
        center=True,
        min_periods=4
    ).median().to_numpy()
    valid = ~np.isnan(qrs_rms_smooth)
    time_peaks = time_peaks[valid]
    qrs_rms_smooth = qrs_rms_smooth[valid]
    if len(qrs_rms_smooth) < 4:
        return None, None, None, None
    try:
        cs = CubicSpline(time_peaks, qrs_rms_smooth)
        time_edr = np.arange(time_peaks[0], time_peaks[-1], 1 / edr_fs)
        edr_interpolated = cs(time_edr)
    except Exception:
        return None, None, None, None
    if len(edr_interpolated) < edr_fs * 30:
        return None, None, None, None
    try:
        edr_filtered = safe_bandpass(
            edr_interpolated,
            fs=edr_fs,
            low_hz=low_bpm / 60,
            high_hz=high_bpm / 60,
            order=3
        )
    except Exception:
        return None, None, None, None
    return time_edr, edr_filtered, time_peaks, qrs_rms_smooth

def estimate_rr_roberts_style(ecg_signal, rpeaks, fs, low_bpm=3, high_bpm=25,
                              heartbeat_window=32, fft_length=512, median_smooth_window=16):
    if len(rpeaks) < heartbeat_window + 2:
        return np.array([]), np.array([]), np.nan
    try:
        qrs_ecg = safe_bandpass(ecg_signal, fs=fs, low_hz=8, high_hz=40, order=2)
    except Exception:
        qrs_ecg = ecg_signal.copy()
    qrs_rms = []
    valid_rpeaks = []
    pre = int(0.04 * fs)
    post = int(0.04 * fs)
    for r in rpeaks:
        start = r - pre
        end = r + post + 1
        if start < 0 or end > len(qrs_ecg):
            continue
        segment = qrs_ecg[start:end]
        segment = segment - np.mean(segment)
        rms = np.sqrt(np.mean(segment ** 2))
        qrs_rms.append(rms)
        valid_rpeaks.append(r)
    qrs_rms = np.asarray(qrs_rms, dtype=float)
    valid_rpeaks = np.asarray(valid_rpeaks, dtype=int)
    if len(qrs_rms) < heartbeat_window + 2:
        return np.array([]), np.array([]), np.nan
    freq_vector = np.linspace(0, 0.5, fft_length // 2 + 1)
    rr_times = []
    rr_estimates = []
    for i in range(heartbeat_window, len(qrs_rms)):
        section = qrs_rms[i - heartbeat_window:i]
        beat_rpeaks = valid_rpeaks[i - heartbeat_window:i]
        rr_intervals_sec = np.diff(beat_rpeaks) / fs
        if len(rr_intervals_sec) < 3:
            continue
        median_rr_sec = np.median(rr_intervals_sec)
        if median_rr_sec <= 0:
            continue
        section = section - np.mean(section)
        if np.std(section) == 0:
            continue
        spectrum = np.fft.rfft(section, n=fft_length)
        power = np.abs(spectrum) ** 2
        low_cpb = (low_bpm / 60) * median_rr_sec
        high_cpb = (high_bpm / 60) * median_rr_sec
        mask = (freq_vector >= low_cpb) & (freq_vector <= high_cpb)
        if np.sum(mask) == 0:
            continue
        band_freqs = freq_vector[mask]
        band_power = power[mask]
        if np.sum(band_power) <= 0:
            continue
        dom_cpb = band_freqs[np.argmax(band_power)]
        rr_bpm = dom_cpb * 60 / median_rr_sec
        rr_times.append(valid_rpeaks[i] / fs)
        rr_estimates.append(rr_bpm)
    rr_times = np.asarray(rr_times)
    rr_estimates = np.asarray(rr_estimates)
    if len(rr_estimates) == 0:
        return np.array([]), np.array([]), np.nan
    rr_smooth = pd.Series(rr_estimates).rolling(
        window=median_smooth_window,
        center=False,
        min_periods=1
    ).median().to_numpy()
    final_rr = np.nanmedian(rr_smooth)
    return rr_times, rr_smooth, final_rr

# =========================
# HRV COMPONENT (from HRV 參數.py)
# =========================

def approximate_entropy(rr, m=2, r_ratio=0.2):
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
        C = C[C > 0]
        if len(C) == 0:
            return np.nan
        return np.mean(np.log(C))
    phi_m = _phi(m)
    phi_m1 = _phi(m + 1)
    if np.isnan(phi_m) or np.isnan(phi_m1):
        return np.nan
    return float(phi_m - phi_m1)

def sample_entropy(rr, m=2, r_ratio=0.2):
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
    return float(-np.log(A / B))

def frequency_domain_hrv(rr, rr_times, interp_fs=4.0):
    rr = np.asarray(rr, dtype=float)
    rr_times = np.asarray(rr_times, dtype=float)
    valid = (~np.isnan(rr)) & (~np.isnan(rr_times))
    rr = rr[valid]
    rr_times = rr_times[valid]
    
    empty_res = {
        "LF_power_ms2": np.nan, "HF_power_ms2": np.nan, "LF_HF_ratio": np.nan,
        "LFnu_percent": np.nan, "HFnu_percent": np.nan, "Total_power_ms2": np.nan,
        "LF_peak_Hz": np.nan, "HF_peak_Hz": np.nan, "freqs": [], "psd": []
    }
    
    if len(rr) < 10 or len(rr_times) < 10:
        return empty_res
    rr_ms = rr * 1000
    sort_idx = np.argsort(rr_times)
    rr_times = rr_times[sort_idx]
    rr_ms = rr_ms[sort_idx]
    unique_times, unique_idx = np.unique(rr_times, return_index=True)
    rr_times = unique_times
    rr_ms = rr_ms[unique_idx]
    if len(rr_ms) < 10:
        return empty_res
    t_interp = np.arange(rr_times[0], rr_times[-1], 1 / interp_fs)
    if len(t_interp) < 16:
        return empty_res
    kind = "cubic" if len(rr_ms) >= 4 else "linear"
    interp_func = interp1d(rr_times, rr_ms, kind=kind, bounds_error=False, fill_value="extrapolate")
    rr_interp = interp_func(t_interp)
    rr_interp = detrend(rr_interp, type="linear")
    nperseg = min(len(rr_interp), int(300 * interp_fs))
    if nperseg < 16:
        return empty_res
    freqs, psd = welch(rr_interp, fs=interp_fs, nperseg=nperseg, noverlap=nperseg // 2, detrend=False)
    
    vlf_band = (freqs >= 0.0033) & (freqs < 0.04)
    lf_band = (freqs >= 0.04) & (freqs < 0.15)
    hf_band = (freqs >= 0.15) & (freqs < 0.40)
    total_band = (freqs >= 0.0033) & (freqs < 0.40)
    
    def band_power(band):
        if np.sum(band) < 2: return np.nan
        return float(np.trapezoid(psd[band], freqs[band]))
        
    vlf = band_power(vlf_band)
    lf = band_power(lf_band)
    hf = band_power(hf_band)
    total_power = band_power(total_band)
    lf_hf = lf / hf if not np.isnan(hf) and hf > 0 else np.nan
    denom = lf + hf
    lfnu = lf / denom * 100 if not np.isnan(denom) and denom > 0 else np.nan
    hfnu = hf / denom * 100 if not np.isnan(denom) and denom > 0 else np.nan
    lf_peak = float(freqs[lf_band][np.argmax(psd[lf_band])]) if np.sum(lf_band) >= 1 else np.nan
    hf_peak = float(freqs[hf_band][np.argmax(psd[hf_band])]) if np.sum(hf_band) >= 1 else np.nan
    
    return {
        "LF_power_ms2": lf, "HF_power_ms2": hf, "LF_HF_ratio": lf_hf,
        "LFnu_percent": lfnu, "HFnu_percent": hfnu, "Total_power_ms2": total_power,
        "LF_peak_Hz": lf_peak, "HF_peak_Hz": hf_peak,
        "freqs": freqs.tolist(), "psd": psd.tolist()
    }

# =========================
# MAIN ENTRY POINT
# =========================

def analyze_biopac_file(file_path, time_col="sec", ecg_col="CH1", resp_col="CH2", fs=250):
    if not os.path.exists(file_path):
        return {"error": f"File not found at path: {file_path}"}
        
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return {"error": f"Failed to read CSV file: {str(e)}"}
        
    # Check columns
    available_cols = df.columns.tolist()
    if time_col not in df.columns:
        # Try finding case-insensitive match
        match = [c for c in available_cols if c.lower() == time_col.lower()]
        if match: time_col = match[0]
        else: return {"error": f"Time column '{time_col}' not found. Available: {available_cols}"}
        
    if ecg_col not in df.columns:
        match = [c for c in available_cols if c.lower() == ecg_col.lower()]
        if match: ecg_col = match[0]
        else: return {"error": f"ECG column '{ecg_col}' not found. Available: {available_cols}"}
        
    has_resp = resp_col in df.columns
    if not has_resp:
        match = [c for c in available_cols if c.lower() == resp_col.lower()]
        if match:
            resp_col = match[0]
            has_resp = True
            
    # Parse to numeric and drop NaN
    cols_to_use = [time_col, ecg_col]
    if has_resp:
        cols_to_use.append(resp_col)
        
    df_clean = df[cols_to_use].copy()
    for col in cols_to_use:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
    df_clean = df_clean.dropna()
    
    time_s = df_clean[time_col].values
    ecg_signal = df_clean[ecg_col].values
    
    duration_sec = len(df_clean) / fs
    if duration_sec < 30:
        return {"error": f"File duration ({duration_sec:.1f}s) is too short. Minimum duration is 30 seconds."}
        
    # --- ECG Clean & Peak Detection ---
    try:
        ecg_clean = nk.ecg_clean(ecg_signal, sampling_rate=fs, method="pantompkins1985")
    except Exception:
        ecg_clean = nk.ecg_clean(ecg_signal, sampling_rate=fs)
        
    try:
        _, info = nk.ecg_peaks(ecg_clean, sampling_rate=fs)
        rpeaks = np.asarray(info["ECG_R_Peaks"], dtype=int)
    except Exception as e:
        return {"error": f"Failed to detect ECG R-peaks: {str(e)}"}
        
    total_peaks = len(rpeaks)
    if total_peaks < 5:
        return {"error": f"Too few R-peaks detected ({total_peaks}). ECG quality might be poor."}
        
    # --- R-Peak RR Interval Calculations ---
    r_times = time_s[rpeaks]
    rr_s = np.diff(r_times)
    rr_ms = rr_s * 1000.0
    rr_times_mid = r_times[:-1] + rr_s / 2
    
    # Filter RR intervals for HRV/RSA
    valid_rr_mask = (rr_ms >= 300) & (rr_ms <= 2000)
    rr_ms_valid = rr_ms[valid_rr_mask]
    rr_s_valid = rr_s[valid_rr_mask]
    rr_times_valid = rr_times_mid[valid_rr_mask]
    
    if len(rr_ms_valid) < 5:
        return {"error": "Too few valid heartbeat intervals after filtering noise."}
        
    mean_rr = float(np.mean(rr_ms_valid))
    mean_hr = float(60000.0 / mean_rr)
    min_hr = float(60000.0 / np.max(rr_ms_valid))
    max_hr = float(60000.0 / np.min(rr_ms_valid))
    sdnn = float(np.std(rr_ms_valid, ddof=1))
    
    diff_rr = np.diff(rr_s_valid)
    diff_rr_ms = diff_rr * 1000.0
    rmssd = float(np.sqrt(np.mean(diff_rr ** 2)) * 1000.0)
    nn50 = int(np.sum(np.abs(diff_rr_ms) > 50))
    pnn50 = float(nn50 / len(diff_rr_ms) * 100) if len(diff_rr_ms) > 0 else np.nan
    cvrr = float(sdnn / mean_rr)
    
    # --- Poincaré Calculations ---
    # SD1 and SD2 ellipse parameters
    sdsd = np.std(diff_rr_ms, ddof=1)
    sd1 = float(np.sqrt(0.5 * (sdsd ** 2)))
    sd2 = float(np.sqrt(2 * (sdnn ** 2) - 0.5 * (sdsd ** 2)))
    sd2_sd1 = float(sd2 / sd1) if sd1 > 0 else np.nan
    
    # --- Nonlinear HRV ---
    apen = approximate_entropy(rr_s_valid)
    sampen = sample_entropy(rr_s_valid)
    
    # --- Frequency HRV ---
    fd_metrics = frequency_domain_hrv(rr_s_valid, rr_times_valid, interp_fs=4.0)
    
    # --- EDR (ECG-Derived Respiration) Consensus ---
    rpeaks_filtered = filter_rpeaks_by_rr(rpeaks, fs, min_rr=0.3, max_rr=2.0)
    
    # Method 1
    _, ptt_edr = calculate_edr_peak_to_trough(ecg_clean, rpeaks_filtered, fs)
    ptt_bpm, ptt_conf = estimate_rate_welch_with_confidence(ptt_edr, fs=8)
    
    # Method 2
    _, rms_edr, _, _ = calculate_edr_qrs_rms(ecg_clean, rpeaks_filtered, fs)
    rms_bpm, rms_conf = estimate_rate_welch_with_confidence(rms_edr, fs=8)
    
    # Method 3
    _, _, roberts_final_rr = estimate_rr_roberts_style(ecg_clean, rpeaks_filtered, fs)
    
    # Consensus
    consensus_rr, consensus_method, consensus_diff, _, _ = consensus_resp_rate({
        "PeakToTrough_Welch": ptt_bpm,
        "QRS_RMS_Welch": rms_bpm,
        "Roberts_RMS_FFT": roberts_final_rr
    })
    
    # --- Respiration Band Processing (if available) ---
    actual_resp_rate = np.nan
    resp_peaks = []
    resp_clean = None
    if has_resp:
        resp_signal = df_clean[resp_col].values
        try:
            resp_clean = nk.rsp_clean(resp_signal, sampling_rate=fs)
            signals_rsp, info_rsp = nk.rsp_peaks(resp_clean, sampling_rate=fs, method="biosppy")
            resp_peaks = np.where(signals_rsp["RSP_Peaks"].values == 1)[0].astype(int)
            if len(resp_peaks) >= 2:
                intervals = np.diff(time_s[resp_peaks])
                actual_resp_rate = float(60.0 / np.mean(intervals))
        except Exception:
            pass
            
    # --- RSA (Respiratory Sinus Arrhythmia) ---
    rsa_metrics = []
    avg_rsa_ms = np.nan
    avg_rsa_bpm = np.nan
    if has_resp and len(resp_peaks) >= 2 and len(rr_ms_valid) >= 5:
        for i in range(len(resp_peaks) - 1):
            t0 = time_s[resp_peaks[i]]
            t1 = time_s[resp_peaks[i+1]]
            in_cycle = (rr_times_valid >= t0) & (rr_times_valid < t1)
            if np.sum(in_cycle) >= 2:
                cycle_rr = rr_ms_valid[in_cycle]
                c_min = float(np.min(cycle_rr))
                c_max = float(np.max(cycle_rr))
                c_rsa_ms = c_max - c_min
                c_rsa_bpm = (60000.0 / c_min) - (60000.0 / c_max)
                rsa_metrics.append({
                    "start_s": float(t0),
                    "end_s": float(t1),
                    "rsa_ms": c_rsa_ms,
                    "rsa_bpm": c_rsa_bpm
                })
        if rsa_metrics:
            avg_rsa_ms = float(np.mean([m["rsa_ms"] for m in rsa_metrics]))
            avg_rsa_bpm = float(np.mean([m["rsa_bpm"] for m in rsa_metrics]))

    # --- PNS / SNS INDEX CALCULATION (Kubios Emulation) ---
    # These indices emulate the balance. 0 represents average normal.
    # PNS is active with high RMSSD, high SD1, low heart rate (high Mean RR).
    # We standardize based on standard HRV population norms:
    # PNS = (Mean_RR_ms - 900)/100 + (RMSSD_ms - 42)/10 + (SD1_ms - 30)/8
    # SNS = (Mean_HR_bpm - 72)/10 + (Stress_Index - 9)/3 - (SD2_ms - 65)/15
    
    # Stress Index = 1 / (AMo * 2 * dX) -> Emulated standard index
    # We approximate it simply: Stress Index = 1000 / (SDNN_ms / 2)
    stress_index = float(1000.0 / (sdnn if sdnn > 0 else 1.0))
    pns_val = ((mean_rr - 800) / 150) + ((rmssd - 30) / 20) + ((sd1 - 25) / 15)
    sns_val = ((mean_hr - 75) / 15) + ((stress_index - 15) / 10) - ((sd2 - 55) / 25)
    
    pns_index = max(-5.0, min(5.0, float(pns_val)))
    sns_index = max(-5.0, min(5.0, float(sns_val)))

    # =========================
    # VISUALIZATION GENERATION
    # =========================
    plots = {}
    
    # Chart 1: ECG clean segment (first 10 seconds for clean preview)
    try:
        fig, ax = plt.subplots(figsize=(10, 2.5))
        plot_len = min(len(ecg_clean), fs * 10)
        ax.plot(time_s[:plot_len], ecg_clean[:plot_len], color="tab:blue", label="Cleaned ECG")
        visible_peaks = rpeaks[rpeaks < plot_len]
        if len(visible_peaks) > 0:
            ax.scatter(time_s[visible_peaks], ecg_clean[visible_peaks], color="red", zorder=5, label="R Peaks")
        ax.set_title("ECG Signal Preview (First 10s)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")
        plots["ecg_preview"] = fig_to_base64(fig)
    except Exception:
        plots["ecg_preview"] = None

    # Chart 2: Poincaré Plot
    try:
        fig, ax = plt.subplots(figsize=(5, 5))
        x = rr_ms_valid[:-1]
        y = rr_ms_valid[1:]
        ax.scatter(x, y, color="tab:blue", alpha=0.6, s=15, edgecolors='none')
        
        # Draw SD1 and SD2 lines
        center_x = np.mean(x)
        center_y = np.mean(y)
        
        # Diagonal line identity
        lims = [min(np.min(x), np.min(y)) - 50, max(np.max(x), np.max(y)) + 50]
        ax.plot(lims, lims, '--', color='gray', alpha=0.5)
        
        # SD1 axis (perpendicular to identity)
        ax.arrow(center_x, center_y, -sd1 / np.sqrt(2), sd1 / np.sqrt(2), 
                 color='red', width=3, head_width=15, label=f"SD1: {sd1:.1f} ms")
        # SD2 axis (along identity)
        ax.arrow(center_x, center_y, sd2 / np.sqrt(2), sd2 / np.sqrt(2), 
                 color='green', width=3, head_width=15, label=f"SD2: {sd2:.1f} ms")
        
        ax.set_title("Poincaré Plot")
        ax.set_xlabel("RR_n (ms)")
        ax.set_ylabel("RR_n+1 (ms)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left")
        plots["poincare"] = fig_to_base64(fig)
    except Exception:
        plots["poincare"] = None

    # Chart 3: FFT spectrum
    try:
        if not np.isnan(fd_metrics["LF_power_ms2"]):
            fig, ax = plt.subplots(figsize=(6, 3.5))
            f = np.array(fd_metrics["freqs"])
            p = np.array(fd_metrics["psd"])
            
            # Mask bands
            vlf_m = (f >= 0.0033) & (f < 0.04)
            lf_m = (f >= 0.04) & (f < 0.15)
            hf_m = (f >= 0.15) & (f < 0.40)
            
            ax.fill_between(f[vlf_m], p[vlf_m], color='lightgray', alpha=0.5, label='VLF')
            ax.fill_between(f[lf_m], p[lf_m], color='orange', alpha=0.5, label='LF')
            ax.fill_between(f[hf_m], p[hf_m], color='green', alpha=0.5, label='HF')
            
            ax.plot(f[f <= 0.5], p[f <= 0.5], color='black', linewidth=1)
            ax.set_title("HRV Power Spectral Density (PSD)")
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel("Power (ms²/Hz)")
            ax.set_xlim([0, 0.5])
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right")
            plots["fft_spectrum"] = fig_to_base64(fig)
        else:
            plots["fft_spectrum"] = None
    except Exception:
        plots["fft_spectrum"] = None

    # Chart 4: RSA Heart Rate and Respiration Overlay (first 60s)
    try:
        if has_resp and resp_clean is not None:
            fig, ax1 = plt.subplots(figsize=(10, 3.5))
            duration = min(60.0, duration_sec)
            
            # 1. Plot Instantaneous Heart Rate
            beat_times = r_times[1:]
            valid_mask_hr = (beat_times <= duration)
            instant_hr = 60.0 / rr_s
            
            t_interp = np.arange(0, duration, 0.1)
            interp = PchipInterpolator(beat_times[valid_mask_hr], instant_hr[valid_mask_hr])
            hr_smooth = interp(t_interp)
            
            ax1.plot(t_interp, hr_smooth, color="tab:red", label="Heart Rate (bpm)", linewidth=1.5)
            ax1.scatter(beat_times[valid_mask_hr], instant_hr[valid_mask_hr], color="tab:red", s=10)
            ax1.set_xlabel("Time (s)")
            ax1.set_ylabel("Heart Rate (bpm)", color="tab:red")
            ax1.tick_params(axis='y', labelcolor="tab:red")
            
            # 2. Respiration curve overlay
            ax2 = ax1.twinx()
            resp_slice = resp_clean[time_s <= duration]
            time_slice = time_s[time_s <= duration]
            ax2.plot(time_slice, resp_slice, color="tab:blue", alpha=0.4, label="Respiration", linewidth=1)
            ax2.set_ylabel("Respiration Amplitude", color="tab:blue")
            ax2.tick_params(axis='y', labelcolor="tab:blue")
            
            # Add breath peak markers
            cycle_peaks = resp_peaks[time_s[resp_peaks] <= duration]
            if len(cycle_peaks) > 0:
                ax2.scatter(time_s[cycle_peaks], resp_clean[cycle_peaks], color="blue", marker="o", s=20, label="Breath Peak")
                
            plt.title("Heart Rate and Respiration Coordination (RSA)")
            plots["rsa_overlay"] = fig_to_base64(fig)
        else:
            plots["rsa_overlay"] = None
    except Exception:
        plots["rsa_overlay"] = None

    # Chart 5: RR Tachogram
    try:
        fig, ax = plt.subplots(figsize=(10, 2.5))
        ax.plot(rr_times_valid, rr_ms_valid, color="tab:purple", linewidth=1.2, label="RR intervals")
        ax.set_title("RR Tachogram (Heartbeat Intervals)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Interval (ms)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        plots["rr_tachogram"] = fig_to_base64(fig)
    except Exception:
        plots["rr_tachogram"] = None

    # --- Assemble final JSON payload ---
    results = {
        "duration_sec": float(duration_sec),
        "total_beats": int(total_peaks),
        "mapped_columns": {
            "time": time_col,
            "ecg": ecg_col,
            "resp": resp_col if has_resp else None
        },
        "time_domain": {
            "mean_rr_ms": round(mean_rr, 1),
            "mean_hr_bpm": round(mean_hr, 1),
            "min_hr_bpm": round(min_hr, 1),
            "max_hr_bpm": round(max_hr, 1),
            "sdnn_ms": round(sdnn, 1),
            "rmssd_ms": round(rmssd, 1),
            "nn50_beats": nn50,
            "pnn50_percent": round(pnn50, 2) if not np.isnan(pnn50) else None,
            "cvrr": round(cvrr, 4),
            "stress_index": round(stress_index, 1)
        },
        "frequency_domain": {
            "lf_power_ms2": round(fd_metrics["LF_power_ms2"], 1) if not np.isnan(fd_metrics["LF_power_ms2"]) else None,
            "hf_power_ms2": round(fd_metrics["HF_power_ms2"], 1) if not np.isnan(fd_metrics["HF_power_ms2"]) else None,
            "lf_hf_ratio": round(fd_metrics["LF_HF_ratio"], 3) if not np.isnan(fd_metrics["LF_HF_ratio"]) else None,
            "lfnu_percent": round(fd_metrics["LFnu_percent"], 2) if not np.isnan(fd_metrics["LFnu_percent"]) else None,
            "hfnu_percent": round(fd_metrics["HFnu_percent"], 2) if not np.isnan(fd_metrics["HFnu_percent"]) else None,
            "total_power_ms2": round(fd_metrics["Total_power_ms2"], 1) if not np.isnan(fd_metrics["Total_power_ms2"]) else None,
            "lf_peak_hz": round(fd_metrics["LF_peak_Hz"], 3) if not np.isnan(fd_metrics["LF_peak_Hz"]) else None,
            "hf_peak_hz": round(fd_metrics["HF_peak_Hz"], 3) if not np.isnan(fd_metrics["HF_peak_Hz"]) else None
        },
        "nonlinear": {
            "sd1_ms": round(sd1, 1),
            "sd2_ms": round(sd2, 1),
            "sd2_sd1_ratio": round(sd2_sd1, 3) if not np.isnan(sd2_sd1) else None,
            "approx_entropy": round(apen, 4) if not np.isnan(apen) else None,
            "sample_entropy": round(sampen, 4) if not np.isnan(sampen) else None
        },
        "respiration": {
            "consensus_edr_bpm": round(consensus_rr, 1) if not np.isnan(consensus_rr) else None,
            "consensus_method": consensus_method,
            "consensus_diff_bpm": round(consensus_diff, 1) if not np.isnan(consensus_diff) else None,
            "measured_resp_bpm": round(actual_resp_rate, 1) if not np.isnan(actual_resp_rate) else None,
            "has_respiration_signal": has_resp
        },
        "rsa": {
            "avg_rsa_ms": round(avg_rsa_ms, 1) if not np.isnan(avg_rsa_ms) else None,
            "avg_rsa_bpm": round(avg_rsa_bpm, 1) if not np.isnan(avg_rsa_bpm) else None,
            "cycles_detected": len(rsa_metrics)
        },
        "ans_indices": {
            "pns_index": round(pns_index, 2),
            "sns_index": round(sns_index, 2)
        },
        "charts": plots
    }
    return results


def analyze_biopac_path(path, time_col="sec", ecg_col="CH1", resp_col="CH2", fs=250):
    """
    Accepts either a single CSV file path or a folder path containing CSV files.
    If it's a folder, it processes all CSV files inside it and returns a dictionary
    mapping filenames to their analysis results.
    If it's a single file, it returns the analysis results for that file.
    """
    if not os.path.exists(path):
        return {"error": f"Path not found: {path}"}
        
    if os.path.isdir(path):
        import glob
        csv_files = glob.glob(os.path.join(path, "*.csv"))
        if not csv_files:
            return {"error": f"No CSV files found in directory: {path}"}
        
        results = {}
        for f in csv_files:
            file_name = os.path.basename(f)
            results[file_name] = analyze_biopac_file(
                file_path=f,
                time_col=time_col,
                ecg_col=ecg_col,
                resp_col=resp_col,
                fs=fs
            )
        return {"type": "directory", "results": results}
    else:
        result = analyze_biopac_file(
            file_path=path,
            time_col=time_col,
            ecg_col=ecg_col,
            resp_col=resp_col,
            fs=fs
        )
        return {"type": "file", "result": result}

