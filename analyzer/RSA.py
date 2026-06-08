import numpy as np
import pandas as pd
import neurokit2 as nk
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator


# =========================
# Peak–Trough RSA per breath cycle
# =========================
def compute_rsa_peak_trough_nk(time_s, ecg, resp, fs=250):
    """
    Returns:
      rsa_df: per-cycle RSA using breath-peak to breath-peak cycles.
      rr_t: timestamps for RR intervals, seconds
      rr_ms: RR intervals, ms
      resp_clean: cleaned respiration
      resp_peaks: respiration peak indices, samples

    Main definitions:
      RSA_ms  = RRmax_cycle_ms - RRmin_cycle_ms
      RSA_bpm = HR_max_bpm - HR_min_bpm

    Note:
      This version does NOT force inspiration / expiration labeling.
      It quantifies peak-to-trough HR fluctuation within each respiratory cycle.
    """

    time_s = np.asarray(time_s, dtype=float)
    ecg = np.asarray(ecg, dtype=float)
    resp = np.asarray(resp, dtype=float)

    # --- ECG: clean and detect R-peaks
    ecg_clean = nk.ecg_clean(ecg, sampling_rate=fs)
    signals_ecg, info_ecg = nk.ecg_peaks(ecg_clean, sampling_rate=fs)
    rpeaks = np.asarray(info_ecg["ECG_R_Peaks"], dtype=int)

    if len(rpeaks) < 3:
        return pd.DataFrame(), None, None, None, None

    # --- RR interval
    r_times = time_s[rpeaks]
    rr_s = np.diff(r_times)
    rr_t = (r_times[:-1] + r_times[1:]) / 2.0
    rr_ms = rr_s * 1000.0

    # --- Basic RR artifact filter
    # 300 ms = 200 bpm, 2000 ms = 30 bpm
    valid_rr = np.isfinite(rr_ms) & (rr_ms >= 300) & (rr_ms <= 2000)
    rr_t = rr_t[valid_rr]
    rr_ms = rr_ms[valid_rr]

    if len(rr_ms) < 3:
        return pd.DataFrame(), rr_t, rr_ms, None, None

    # --- Respiration: clean and detect peaks
    resp_clean = nk.rsp_clean(resp, sampling_rate=fs)
    signals_rsp, info_rsp = nk.rsp_peaks(
        resp_clean,
        sampling_rate=fs,
        method="biosppy"
    )

    # RSP_Peaks is a 0/1 vector aligned with samples
    resp_peaks = np.where(signals_rsp["RSP_Peaks"].values == 1)[0].astype(int)

    if len(resp_peaks) < 2:
        return pd.DataFrame(), rr_t, rr_ms, resp_clean, resp_peaks

    # --- Build respiratory cycles peak -> peak
    rows = []

    for i in range(len(resp_peaks) - 1):
        s = resp_peaks[i]
        e = resp_peaks[i + 1]

        t0 = time_s[s]
        t1 = time_s[e]
        tm = 0.5 * (t0 + t1)

        in_cycle = (rr_t >= t0) & (rr_t < t1)

        # Need at least 2 RR points to define max-min
        if np.sum(in_cycle) < 2:
            continue

        rr_cycle = rr_ms[in_cycle]

        # RR minimum means HR maximum
        rr_min_cycle = float(np.min(rr_cycle))
        rr_max_cycle = float(np.max(rr_cycle))

        hr_max_bpm = 60000.0 / rr_min_cycle
        hr_min_bpm = 60000.0 / rr_max_cycle

        rsa_ms = rr_max_cycle - rr_min_cycle
        rsa_bpm = hr_max_bpm - hr_min_bpm

        rows.append({
            "cycle_start_s": float(t0),
            "cycle_end_s": float(t1),
            "cycle_mid_s": float(tm),

            "RRmin_cycle_ms": rr_min_cycle,
            "RRmax_cycle_ms": rr_max_cycle,
            "RSA_ms": float(rsa_ms),

            "HR_max_bpm": float(hr_max_bpm),
            "HR_min_bpm": float(hr_min_bpm),
            "RSA_bpm": float(rsa_bpm),
            "HR_range_during_breath": f"{hr_max_bpm:.1f} -> {hr_min_bpm:.1f} bpm"
        })

    rsa_df = pd.DataFrame(rows)
    return rsa_df, rr_t, rr_ms, resp_clean, resp_peaks


# =========================
# Plot HR oscillation wave
# =========================
def plot_hr_rsa_wave(
    rr_t,
    rr_ms,
    time_s=None,
    resp_clean=None,
    resp_peaks=None,
    start_s=None,
    end_s=None,
    interp_fs=10,
    save_path="hr_rsa_wave.png"
):
    """
    Plot beat-to-beat HR and smoothed HR oscillation.

    It visualizes:
      - Beat-to-beat HR points
      - Smoothed HR curve
      - Respiratory cycle boundaries
      - HR max -> HR min range in each breath cycle
    """

    if rr_t is None or rr_ms is None:
        print("No RR data available for plotting.")
        return

    rr_t = np.asarray(rr_t, dtype=float)
    rr_ms = np.asarray(rr_ms, dtype=float)

    hr_bpm = 60000.0 / rr_ms

    valid = np.isfinite(rr_t) & np.isfinite(hr_bpm)
    rr_t = rr_t[valid]
    hr_bpm = hr_bpm[valid]

    if len(rr_t) < 3:
        print("Not enough RR points to plot HR wave.")
        return

    if start_s is None:
        start_s = float(rr_t[0])
    if end_s is None:
        end_s = float(rr_t[-1])

    seg = (rr_t >= start_s) & (rr_t <= end_s)
    rr_t_seg = rr_t[seg]
    hr_seg = hr_bpm[seg]

    if len(rr_t_seg) < 3:
        print("Not enough HR points in selected segment.")
        return

    # Remove duplicate time points, just in case
    unique_t, unique_idx = np.unique(rr_t_seg, return_index=True)
    rr_t_seg = unique_t
    hr_seg = hr_seg[unique_idx]

    if len(rr_t_seg) < 3:
        print("Not enough unique HR points in selected segment.")
        return

    # Smooth interpolation for visualization
    t_uniform = np.arange(start_s, end_s, 1.0 / interp_fs)

    try:
        interp = PchipInterpolator(rr_t_seg, hr_seg)
        hr_smooth = interp(t_uniform)
    except Exception as e:
        print(f"Interpolation failed: {e}")
        return

    fig, ax1 = plt.subplots(figsize=(13, 5))

    # Smooth HR wave
    ax1.plot(t_uniform, hr_smooth, label="Smoothed HR")

    # Original beat-to-beat HR
    ax1.plot(rr_t_seg, hr_seg, ".", label="Beat-to-beat HR")

    # Respiration peak lines and HR range labels
    if resp_peaks is not None and time_s is not None:
        time_s_arr = np.asarray(time_s, dtype=float)
        resp_peak_times = time_s_arr[resp_peaks]
        resp_peak_times = resp_peak_times[
            (resp_peak_times >= start_s) & (resp_peak_times <= end_s)
        ]

        for tp in resp_peak_times:
            ax1.axvline(tp, linewidth=1, alpha=0.25)

        for i in range(len(resp_peak_times) - 1):
            t0 = resp_peak_times[i]
            t1 = resp_peak_times[i + 1]
            tm = 0.5 * (t0 + t1)

            in_cycle = (rr_t_seg >= t0) & (rr_t_seg < t1)

            if np.sum(in_cycle) < 2:
                continue

            t_cycle = rr_t_seg[in_cycle]
            hr_cycle = hr_seg[in_cycle]

            idx_max = np.argmax(hr_cycle)
            idx_min = np.argmin(hr_cycle)

            t_max = t_cycle[idx_max]
            t_min = t_cycle[idx_min]

            hr_max = hr_cycle[idx_max]
            hr_min = hr_cycle[idx_min]
            rsa_bpm = hr_max - hr_min

            # Mark HR max and HR min
            ax1.plot(t_max, hr_max, "o")
            ax1.plot(t_min, hr_min, "o")

            # Vertical range marker
            ax1.vlines(tm, hr_min, hr_max, linestyles="--", alpha=0.5)

            # Text label
            ax1.text(
                tm,
                hr_max + 0.8,
                f"{hr_max:.0f}->{hr_min:.0f}\nΔ={rsa_bpm:.1f}",
                ha="center",
                va="bottom",
                fontsize=8
            )

    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Heart Rate (bpm)")
    ax1.set_title("Heart Rate Oscillation Across Respiratory Cycles")
    ax1.grid(True)

    # Optional: overlay respiration on right axis
    if resp_clean is not None and time_s is not None:
        time_s_arr = np.asarray(time_s, dtype=float)
        resp_clean_arr = np.asarray(resp_clean, dtype=float)

        resp_seg = (time_s_arr >= start_s) & (time_s_arr <= end_s)

        if np.sum(resp_seg) > 2:
            ax2 = ax1.twinx()
            ax2.plot(
                time_s_arr[resp_seg],
                resp_clean_arr[resp_seg],
                alpha=0.35,
                label="Respiration"
            )
            ax2.set_ylabel("Respiration")

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
        else:
            ax1.legend(loc="upper right")
    else:
        ax1.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()

    print(f"Saved figure: {save_path}")


# =========================
# Monitoring: Plan B 10s summary + Plan C anomaly events
# =========================
def monitor_rsa(
    rsa_df: pd.DataFrame,
    print_every_sec=10,
    roll_W=5,
    low_ms=10,
    high_ms=150,
    jump_ms=30,
    save_summary_csv="rsa_summary_10s.csv",
    save_events_csv="rsa_events.csv"
):
    """
    Monitor RSA over time.

    Plan B:
      Print and save summary every X seconds.

    Plan C:
      Detect anomaly events:
        LOW  : RSA_ms < low_ms
        HIGH : RSA_ms > high_ms
        JUMP : rolling RSA_ms changes too much
    """

    if rsa_df.empty:
        print("No RSA cycles detected.")
        return

    df = rsa_df.copy()
    df["RSA_roll_ms"] = df["RSA_ms"].rolling(roll_W).mean()

    if "RSA_bpm" in df.columns:
        df["RSA_roll_bpm"] = df["RSA_bpm"].rolling(roll_W).mean()
    else:
        df["RSA_roll_bpm"] = np.nan

    next_t = 0.0
    summary_rows = []

    prev_roll = None
    event_rows = []

    for i, row in df.iterrows():
        t0 = float(row["cycle_start_s"])
        rsa_ms = float(row["RSA_ms"])
        roll_ms = row["RSA_roll_ms"]

        if np.isnan(roll_ms):
            continue

        rsa_bpm = float(row["RSA_bpm"]) if "RSA_bpm" in row and pd.notna(row["RSA_bpm"]) else np.nan
        roll_bpm = float(row["RSA_roll_bpm"]) if pd.notna(row["RSA_roll_bpm"]) else np.nan
        hr_range = row["HR_range_during_breath"] if "HR_range_during_breath" in row else ""

        # Plan B: every X seconds summary
        if t0 >= next_t:
            print(
                f"t={t0:7.1f}s | "
                f"RSA={rsa_ms:7.1f} ms | "
                f"RSA_bpm={rsa_bpm:5.1f} bpm | "
                f"HR range={hr_range} | "
                f"roll{roll_W}={float(roll_ms):7.1f} ms"
            )

            summary_rows.append({
                "t_s": t0,
                "RSA_latest_ms": rsa_ms,
                "RSA_latest_bpm": rsa_bpm,
                "HR_range_during_breath": hr_range,
                f"RSA_roll{roll_W}_ms": float(roll_ms),
                f"RSA_roll{roll_W}_bpm": roll_bpm
            })

            next_t += print_every_sec

        # Plan C: anomaly events
        flags = []

        if rsa_ms < low_ms:
            flags.append("LOW")

        if rsa_ms > high_ms:
            flags.append("HIGH")

        if prev_roll is not None and abs(float(roll_ms) - prev_roll) > jump_ms:
            flags.append("JUMP")

        if flags:
            print(
                f"[{i:04d}] t={t0:.1f}s | "
                f"RSA={rsa_ms:.1f} ms | "
                f"RSA_bpm={rsa_bpm:.1f} bpm | "
                f"HR range={hr_range} | "
                f"roll{roll_W}={float(roll_ms):.1f} ms | "
                f"{'/'.join(flags)}"
            )

            event_rows.append({
                "idx": int(i),
                "t_s": t0,
                "RSA_ms": rsa_ms,
                "RSA_bpm": rsa_bpm,
                "HR_range_during_breath": hr_range,
                f"RSA_roll{roll_W}_ms": float(roll_ms),
                f"RSA_roll{roll_W}_bpm": roll_bpm,
                "flags": "/".join(flags)
            })

        prev_roll = float(roll_ms)

    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(save_summary_csv, index=False)
        print(f"Saved: {save_summary_csv}")

    if event_rows:
        pd.DataFrame(event_rows).to_csv(save_events_csv, index=False)
        print(f"Saved: {save_events_csv}")


# =========================
# Main
# =========================
if __name__ == "__main__":

    csv_path = r"D:\115-2 data\LB0411\LB-0411-01.csv"

    # ===== 改這裡就好 =====
    TIME_COL = "sec"
    ECG_COL = "CH1"
    RESP_COL = "CH2"
    # =====================

    df = pd.read_csv(csv_path)

    print("CSV 欄位名稱：")
    print(df.columns.tolist())

    for c in [TIME_COL, ECG_COL, RESP_COL]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[TIME_COL, ECG_COL, RESP_COL])

    time_s = df[TIME_COL].to_numpy(dtype=float)
    ecg = df[ECG_COL].to_numpy(dtype=float)
    resp = df[RESP_COL].to_numpy(dtype=float)

    fs = 250

    rsa_df, rr_t, rr_ms, resp_clean, resp_peaks = compute_rsa_peak_trough_nk(
        time_s,
        ecg,
        resp,
        fs=fs
    )

    print(f"Computed RSA cycles: {len(rsa_df)}")

    # Save per-cycle RSA
    rsa_df.to_csv("rsa_per_cycle.csv", index=False)
    print("Saved: rsa_per_cycle.csv")

    # Plan B + Plan C monitoring
    monitor_rsa(
        rsa_df,
        print_every_sec=10,
        roll_W=5,
        low_ms=10,
        high_ms=150,
        jump_ms=30,
        save_summary_csv="rsa_summary_10s.csv",
        save_events_csv="rsa_events.csv"
    )

    # =========================
    # Plot HR oscillation
    # =========================
    # 建議先畫一小段，不要一開始畫完整 5 分鐘
    # 例如 20~60 秒，會比較容易看到像弦波的 HR 上下起伏

    plot_hr_rsa_wave(
        rr_t=rr_t,
        rr_ms=rr_ms,
        time_s=time_s,
        resp_clean=resp_clean,
        resp_peaks=resp_peaks,
        start_s=40,
        end_s=120,
        interp_fs=10,
        save_path="hr_rsa_wave_20_60s.png"
    )
