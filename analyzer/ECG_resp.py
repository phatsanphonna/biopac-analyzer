import os
import glob
import numpy as np
import pandas as pd
import neurokit2 as nk
import matplotlib.pyplot as plt

from scipy.interpolate import CubicSpline
from scipy.signal import butter, filtfilt, welch


# =========================
# 基本設定
# =========================
FOLDER_PATH = r"D:\115-2 data"
ECG_COL = "CH1"

FS = 250          # ECG 取樣率
EDR_FS = 8        # EDR 插值後取樣率

START_SEC = 20
DURATION_SEC = 60

# 呼吸率搜尋範圍
# 若你要包含 4 bpm 慢呼吸，不要設 5
RESP_LOW_BPM = 3
RESP_HIGH_BPM = 25

# Roberts-style 參數
HEARTBEAT_WINDOW = 32
MEDIAN_SMOOTH_WINDOW = 16
FFT_LENGTH = 512

all_results = []


# =========================
# 工具函式
# =========================
def safe_bandpass(x, fs, low_hz, high_hz, order=2):
    x = np.asarray(x, dtype=float)

    nyq = fs / 2
    low = low_hz / nyq
    high = high_hz / nyq

    if low <= 0:
        low = 0.001

    if high >= 1:
        high = 0.99

    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, x)


def filter_rpeaks_by_rr(rpeaks, fs, min_rr=0.3, max_rr=2.0):
    """
    用 RR interval 排除明顯異常 R peak。
    這不是正式 Philips ST/AR normal sinus beat classification，
    只是簡化版異常心搏排除。
    """
    rpeaks = np.asarray(rpeaks, dtype=int)

    if len(rpeaks) < 3:
        return rpeaks

    rr = np.diff(rpeaks) / fs
    valid = np.ones(len(rpeaks), dtype=bool)

    bad_rr = (rr < min_rr) | (rr > max_rr)
    valid[1:][bad_rr] = False

    return rpeaks[valid]


def estimate_rate_welch_with_confidence(signal, fs, low_bpm=3, high_bpm=25):
    """
    Welch 頻譜法估呼吸率，並回傳 confidence。
    confidence = 主峰 power / 呼吸頻帶總 power
    """
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
    """
    從多個呼吸率估計值中選出最接近的兩個，取平均當最終結果。

    values 範例：
    {
        "PeakToTrough_Welch": 5.2,
        "QRS_RMS_Welch": 5.8,
        "Roberts_RMS_FFT": 12.0
    }
    """

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
# 方法 1：QRS peak-to-trough EDR
# =========================
def calculate_edr_peak_to_trough(ecg_signal, rpeaks, fs, edr_fs=8,
                                 low_bpm=3, high_bpm=25):
    """
    你的原本方法：
    每個 R peak 附近取 QRS window，算 max-min 作為 EDR value。
    """
    if len(rpeaks) < 4:
        return None, None

    qrs_amps = []
    valid_rpeaks = []

    # R peak 前後各 80 ms
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

    # 30 秒視窗 mean ± 2SD clipping
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


# =========================
# 方法 2：QRS RMS EDR + Welch
# =========================
def calculate_edr_qrs_rms(ecg_signal, rpeaks, fs, edr_fs=8,
                          low_bpm=3, high_bpm=25):
    """
    QRS RMS 版 EDR：
    1. ECG 先做 QRS bandpass 8–40 Hz
    2. 每個 R peak 附近取 QRS window
    3. 算 RMS
    4. 16-beat rolling median 平滑
    5. cubic spline 到 8 Hz
    6. bandpass 成呼吸頻帶
    """
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

    # 16-beat moving median，減少每一下 QRS RMS 的小震盪
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


# =========================
# 方法 3：Roberts-style QRS RMS + 16-beat FFT
# =========================
def estimate_rr_roberts_style(ecg_signal, rpeaks, fs,
                              low_bpm=3, high_bpm=25,
                              heartbeat_window=16,
                              fft_length=512,
                              median_smooth_window=16):
    """
    改寫 Roberts/Kulkarni 方法給 CSV ECG 使用。

    概念：
    1. 每個 QRS complex 算 RMS
    2. 每 16 個心搏為一個 window
    3. 對 RMS 序列做 FFT
    4. 根據 median RR interval 將 cycles/beat 轉成 breaths/min
    5. 最後做 median smoothing
    """
    if len(rpeaks) < heartbeat_window + 2:
        return np.array([]), np.array([]), np.nan

    try:
        qrs_ecg = safe_bandpass(ecg_signal, fs=fs, low_hz=8, high_hz=40, order=2)
    except Exception:
        qrs_ecg = ecg_signal.copy()

    qrs_rms = []
    valid_rpeaks = []

    # Roberts 原始 QRS_INTERVAL 是 -40 到 +40 samples at 1000 Hz
    # 等於 R peak 前後各 40 ms
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

        # 對應這 16 個 beat 的 RR interval
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

        # FFT 的 x 軸是 cycles/beat
        # 呼吸 bpm 對應到 cycles/beat：
        # cycles/beat = (bpm / 60) * median_RR_sec
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

        # cycles/beat 轉回 breaths/min
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
# 主處理函式
# =========================
def process_and_plot_ecg(file_path, ecg_col="CH1", fs=250, edr_fs=8,
                         start_sec=20, duration_sec=60):

    file_name = os.path.basename(file_path)
    print(f"\n正在處理檔案: {file_name}")

    df = pd.read_csv(file_path)

    if ecg_col not in df.columns:
        print(f"找不到欄位 {ecg_col}，跳過。")
        return None

    ecg_signal = pd.to_numeric(df[ecg_col], errors="coerce").dropna().values

    if len(ecg_signal) < fs * 30:
        print("資料太短，不適合做 EDR")
        return None

    # ECG clean
    try:
        ecg_clean = nk.ecg_clean(
            ecg_signal,
            sampling_rate=fs,
            method="pantompkins1985"
        )
    except Exception:
        ecg_clean = nk.ecg_clean(
            ecg_signal,
            sampling_rate=fs,
            #method="neurokit"
        )

    # R peak detection
    try:
        _, info = nk.ecg_peaks(
            ecg_clean,
            sampling_rate=fs,
            #method="neurokit"
        )
    except Exception as e:
        print(f"R peak detection 失敗: {e}")
        return None

    rpeaks = np.asarray(info["ECG_R_Peaks"], dtype=int)
    total_peaks = len(rpeaks)

    if total_peaks < 5:
        print("R peaks 太少，跳過。")
        return None

    # HR
    rr_intervals = np.diff(rpeaks) / fs
    rr_valid = rr_intervals[(rr_intervals >= 0.3) & (rr_intervals <= 2.0)]

    hr_mean = np.nan

    if len(rr_valid) > 0:
        hr_mean = np.mean(60 / rr_valid)

    print(f"平均 HR = {hr_mean:.2f} bpm | 總 R peaks = {total_peaks}")

    # EDR 用的 R peaks
    rpeaks_for_edr = filter_rpeaks_by_rr(
        rpeaks,
        fs,
        min_rr=0.3,
        max_rr=2.0
    )

    print(f"EDR 使用 R peaks 數 = {len(rpeaks_for_edr)}")

    # 方法 1：peak-to-trough EDR
    ptt_time, ptt_edr = calculate_edr_peak_to_trough(
        ecg_clean,
        rpeaks_for_edr,
        fs,
        edr_fs=edr_fs,
        low_bpm=RESP_LOW_BPM,
        high_bpm=RESP_HIGH_BPM
    )

    ptt_welch_bpm, ptt_conf = estimate_rate_welch_with_confidence(
        ptt_edr,
        fs=edr_fs,
        low_bpm=RESP_LOW_BPM,
        high_bpm=RESP_HIGH_BPM
    )

    # 方法 2：QRS RMS EDR + Welch
    rms_time, rms_edr, rms_point_time, rms_points = calculate_edr_qrs_rms(
        ecg_clean,
        rpeaks_for_edr,
        fs,
        edr_fs=edr_fs,
        low_bpm=RESP_LOW_BPM,
        high_bpm=RESP_HIGH_BPM
    )

    rms_welch_bpm, rms_conf = estimate_rate_welch_with_confidence(
        rms_edr,
        fs=edr_fs,
        low_bpm=RESP_LOW_BPM,
        high_bpm=RESP_HIGH_BPM
    )

    # 方法 3：Roberts-style RMS + 16-beat FFT
    roberts_time, roberts_rr, roberts_final_rr = estimate_rr_roberts_style(
        ecg_clean,
        rpeaks_for_edr,
        fs,
        low_bpm=RESP_LOW_BPM,
        high_bpm=RESP_HIGH_BPM,
        heartbeat_window=HEARTBEAT_WINDOW,
        fft_length=FFT_LENGTH,
        median_smooth_window=MEDIAN_SMOOTH_WINDOW
    )
    consensus_rr, consensus_method, consensus_diff, pair_1, pair_2 = consensus_resp_rate(
    {
        "PeakToTrough_Welch": ptt_welch_bpm,
        "QRS_RMS_Welch": rms_welch_bpm,
        "Roberts_RMS_FFT": roberts_final_rr
    },
    max_pair_diff=3.0
    )

    if not np.isnan(consensus_rr):
        print(f"Final Consensus RR = {consensus_rr:.2f} bpm | {consensus_method} | diff = {consensus_diff:.2f}")
    else:
        print(f"Final Consensus RR = 無法計算 | {consensus_method} | closest diff = {consensus_diff:.2f}")

    print(f"Peak-to-trough + Welch = {ptt_welch_bpm:.2f} bpm | conf = {ptt_conf:.3f}")
    print(f"QRS RMS EDR + Welch    = {rms_welch_bpm:.2f} bpm | conf = {rms_conf:.3f}")
    print(f"Roberts-style RMS FFT  = {roberts_final_rr:.2f} bpm")

    # =========================
    # 畫圖
    # =========================
    start_idx = int(start_sec * fs)
    end_idx = int((start_sec + duration_sec) * fs)
    end_idx = min(end_idx, len(ecg_clean))

    time_axis = np.arange(start_idx, end_idx) / fs
    seg_ecg = ecg_clean[start_idx:end_idx]

    seg_rpeaks = rpeaks[
        (rpeaks >= start_idx) & (rpeaks < end_idx)
    ]

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        sharex=False
    )

    ax1, ax2, ax3 = axes

    # ECG
    ax1.plot(time_axis, seg_ecg, label="Clean ECG", color="tab:blue")

    if len(seg_rpeaks) > 0:
        ax1.scatter(
            seg_rpeaks / fs,
            ecg_clean[seg_rpeaks],
            color="red",
            marker="o",
            s=25,
            label="R peaks",
            zorder=5
        )

    hr_text = f"{hr_mean:.2f}" if not np.isnan(hr_mean) else "N/A"
    ax1.set_title(f"ECG | {file_name} | HR: {hr_text} bpm")
    ax1.set_ylabel("Amplitude")
    ax1.legend()
    ax1.grid(True)

    # RMS EDR waveform
    if rms_edr is not None:
        edr_start = np.searchsorted(rms_time, start_sec)
        edr_end = np.searchsorted(rms_time, start_sec + duration_sec)
        edr_end = min(edr_end, len(rms_edr))

        ax2.plot(
            rms_time[edr_start:edr_end],
            rms_edr[edr_start:edr_end],
            color="tab:green",
            label="QRS RMS EDR waveform"
        )

        ax2.set_title(
            f"QRS RMS EDR + Welch: {rms_welch_bpm:.2f} bpm | conf: {rms_conf:.3f}"
        )
    else:
        ax2.text(
            0.5,
            0.5,
            "QRS RMS EDR failed",
            ha="center",
            va="center",
            transform=ax2.transAxes
        )

    ax2.set_ylabel("EDR Amplitude")
    ax2.legend()
    ax2.grid(True)

    # Roberts-style time-varying RR
    if len(roberts_rr) > 0:
        idx = (roberts_time >= start_sec) & (roberts_time <= start_sec + duration_sec)

        ax3.plot(
            roberts_time[idx],
            roberts_rr[idx],
            color="tab:purple",
            marker="o",
            markersize=3,
            label="Roberts-style RR"
        )

        ax3.axhline(
            roberts_final_rr,
            linestyle="--",
            color="gray",
            label=f"Median RR: {roberts_final_rr:.2f} bpm"
        )

        ax3.set_title(f"Roberts-style QRS RMS + 16-beat FFT | Final RR: {roberts_final_rr:.2f} bpm")
    else:
        ax3.text(
            0.5,
            0.5,
            "Roberts-style RR failed",
            ha="center",
            va="center",
            transform=ax3.transAxes
        )

    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("Resp Rate (bpm)")
    ax3.legend()
    ax3.grid(True)

    plt.tight_layout()
    plt.show()

    return {
    # 給 final_results.csv 用
    "final": {
        "檔案名稱": file_name,
        "平均心率(bpm)": round(hr_mean, 2) if not np.isnan(hr_mean) else "無法計算",
        "Final_Consensus_RR(bpm)": round(consensus_rr, 2) if not np.isnan(consensus_rr) else "無法計算",
        "Consensus_Method": consensus_method,
        "Closest_Pair_Diff(bpm)": round(consensus_diff, 2) if not np.isnan(consensus_diff) else "無法計算",
        "Closest_Method_1": pair_1,
        "Closest_Method_2": pair_2
    },

    # 給 method_details.csv 用
    "details": {
        "檔案名稱": file_name,
        "平均心率(bpm)": round(hr_mean, 2) if not np.isnan(hr_mean) else "無法計算",
        "R_peaks總數量": total_peaks,
        "EDR使用R_peaks數量": len(rpeaks_for_edr),

        "PeakToTrough_Welch(bpm)": round(ptt_welch_bpm, 2) if not np.isnan(ptt_welch_bpm) else "無法計算",
        "PeakToTrough_Welch_conf": round(ptt_conf, 4) if not np.isnan(ptt_conf) else "無法計算",

        "QRS_RMS_EDR_Welch(bpm)": round(rms_welch_bpm, 2) if not np.isnan(rms_welch_bpm) else "無法計算",
        "QRS_RMS_Welch_conf": round(rms_conf, 4) if not np.isnan(rms_conf) else "無法計算",

        "Roberts_RMS_FFT_MedianRR(bpm)": round(roberts_final_rr, 2) if not np.isnan(roberts_final_rr) else "無法計算",

        "Final_Consensus_RR(bpm)": round(consensus_rr, 2) if not np.isnan(consensus_rr) else "無法計算",
        "Consensus_Method": consensus_method,
        "Closest_Pair_Diff(bpm)": round(consensus_diff, 2) if not np.isnan(consensus_diff) else "無法計算",
        "Closest_Method_1": pair_1,
        "Closest_Method_2": pair_2
    }
}



# =========================
# 批次執行
# =========================
if __name__ == "__main__":
    final_results = []
    method_details = []

    csv_files = glob.glob(os.path.join(FOLDER_PATH, "*.csv"))

    if not csv_files:
        print(f"在路徑 {FOLDER_PATH} 中找不到 CSV 檔案。")

    else:
        for file_path in csv_files:
            res = process_and_plot_ecg(
                file_path,
                ecg_col=ECG_COL,
                fs=FS,
                edr_fs=EDR_FS,
                start_sec=START_SEC,
                duration_sec=DURATION_SEC
            )

            if res:
                final_results.append(res["final"])
                method_details.append(res["details"])

        if final_results:
            final_df = pd.DataFrame(final_results)
            detail_df = pd.DataFrame(method_details)

            final_output_path = os.path.join(
                FOLDER_PATH,
                "final_respiration_results.csv"
            )

            detail_output_path = os.path.join(
                FOLDER_PATH,
                "method_details_three_estimates.csv"
            )

            final_df.to_csv(final_output_path, index=False, encoding="utf-8-sig")
            detail_df.to_csv(detail_output_path, index=False, encoding="utf-8-sig")

            print("\n[完成] 所有檔案已處理完畢！")
            print(f"最終結果 CSV 已儲存至: {final_output_path}")
            print(f"三方法詳細紀錄 CSV 已儲存至: {detail_output_path}")
