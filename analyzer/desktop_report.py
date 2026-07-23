"""One-page PDF summary for desktop ECG/HRV analysis results."""

from __future__ import annotations

import math
import textwrap
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Bbox
from scipy.interpolate import interp1d
from scipy.signal import detrend, welch

from desktop_analysis import METHODS, PARAMETERS, AnalysisContext, AnalysisResult, MetricValue


FloatArray = npt.NDArray[np.float64]
BLUE = "#175C83"
LIGHT_BLUE = "#EAF3F7"
ORANGE = "#D9772B"
GRAY = "#68737D"


def _text(value: MetricValue | None, precision: int = 2) -> str:
    if value is None or (
        isinstance(value, (float, np.floating)) and not math.isfinite(float(value))
    ):
        return "-"
    if isinstance(value, str):
        return value.replace("–", "-").replace("—", "-")
    return f"{float(value):.{precision}f}"


def _metric(result: AnalysisResult, key: str) -> str:
    spec = PARAMETERS[key]
    return _text(result.values.get(key), spec.precision)


def _metric_with_unit(result: AnalysisResult, key: str, unit: str) -> str:
    value = _metric(result, key)
    return value if value == "-" else f"{value} {unit}"


def _rr_data(context: AnalysisContext | None) -> tuple[FloatArray, FloatArray]:
    if context is None:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)
    size = min(len(context.valid_rr), len(context.valid_rr_times))
    rr = np.asarray(context.valid_rr[:size], dtype=np.float64)
    times = np.asarray(context.valid_rr_times[:size], dtype=np.float64)
    valid = np.isfinite(rr) & np.isfinite(times)
    return rr[valid], times[valid]


def _style_chart(axis: Axes) -> None:
    axis.tick_params(labelsize=6.5, colors=GRAY)
    axis.grid(True, color="#DCE3E8", linewidth=0.5, alpha=0.8)
    for spine in axis.spines.values():
        spine.set_color("#B8C3CA")


def _unavailable(axis: Axes, title: str) -> None:
    axis.set_title(title, loc="left", fontsize=9, fontweight="bold", color=BLUE)
    axis.text(
        0.5,
        0.5,
        "Insufficient data",
        ha="center",
        va="center",
        color=GRAY,
        fontsize=8,
        transform=axis.transAxes,
    )
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color("#DCE3E8")


def _draw_tachogram(
    upper: Axes, lower: Axes, rr: FloatArray, times: FloatArray
) -> None:
    if not len(rr):
        _unavailable(upper, "RR tachogram")
        _unavailable(lower, "Detrended RR")
        return
    minutes = (times - times[0]) / 60
    rr_ms = rr * 1_000
    upper.plot(minutes, rr_ms, color=BLUE, linewidth=0.8)
    upper.scatter(minutes, rr_ms, color=BLUE, s=3)
    upper.set_title("RR tachogram", loc="left", fontsize=9, fontweight="bold", color=BLUE)
    upper.set_ylabel("RR (ms)", fontsize=7)
    upper.tick_params(labelbottom=False)
    _style_chart(upper)

    trend = detrend(rr_ms, type="linear") if len(rr_ms) >= 2 else rr_ms - rr_ms.mean()
    lower.axhline(0, color="#AAB4BB", linewidth=0.6)
    lower.plot(minutes, trend, color=ORANGE, linewidth=0.8)
    lower.text(
        0.99,
        0.88,
        "Detrended RR",
        ha="right",
        va="top",
        fontsize=6.5,
        color=ORANGE,
        transform=lower.transAxes,
    )
    lower.set_ylabel("Delta (ms)", fontsize=7)
    lower.set_xlabel("Time (min)", fontsize=7)
    _style_chart(lower)


def _draw_histogram(axis: Axes, rr: FloatArray) -> None:
    if not len(rr):
        _unavailable(axis, "RR distribution")
        return
    bins = min(20, max(5, int(math.sqrt(len(rr)))))
    axis.hist(rr * 1_000, bins=bins, color=BLUE, edgecolor="white", linewidth=0.5)
    axis.set_title("RR distribution", loc="left", fontsize=9, fontweight="bold", color=BLUE)
    axis.set_xlabel("RR interval (ms)", fontsize=7)
    axis.set_ylabel("Count", fontsize=7)
    _style_chart(axis)


def _spectrum(rr: FloatArray, times: FloatArray) -> tuple[FloatArray, FloatArray] | None:
    if len(rr) < 10 or times[-1] - times[0] < 30:
        return None
    order = np.argsort(times)
    unique_times, indices = np.unique(times[order], return_index=True)
    rr_ms = rr[order][indices] * 1_000
    if len(rr_ms) < 10:
        return None
    samples = np.arange(unique_times[0], unique_times[-1], 0.25)
    if len(samples) < 16:
        return None
    interpolated = interp1d(
        unique_times,
        rr_ms,
        kind="cubic" if len(rr_ms) >= 4 else "linear",
        bounds_error=False,
        fill_value="extrapolate",
    )(samples)
    interpolated = detrend(interpolated, type="linear")
    segment = min(len(interpolated), 1_200)
    if segment < 16:
        return None
    frequencies, power = welch(
        interpolated,
        fs=4.0,
        nperseg=segment,
        noverlap=segment // 2,
        detrend=False,
    )
    selected = (frequencies >= 0.0033) & (frequencies <= 0.4)
    return (
        np.asarray(frequencies[selected], dtype=np.float64),
        np.asarray(power[selected], dtype=np.float64),
    )


def _draw_spectrum(axis: Axes, rr: FloatArray, times: FloatArray) -> None:
    spectrum = _spectrum(rr, times) if len(rr) else None
    if spectrum is None:
        _unavailable(axis, "Welch power spectrum")
        return
    frequencies, power = spectrum
    bands = (
        (0.0033, 0.04, "#DDEBF2", "VLF"),
        (0.04, 0.15, "#DCEEDC", "LF"),
        (0.15, 0.4, "#FBE7D6", "HF"),
    )
    for start, end, color, label in bands:
        axis.axvspan(start, end, color=color, alpha=0.9)
        axis.text(
            (start + end) / 2,
            0.96,
            label,
            ha="center",
            va="top",
            fontsize=6.5,
            color=GRAY,
            transform=axis.get_xaxis_transform(),
        )
    axis.plot(frequencies, power, color=BLUE, linewidth=0.9)
    axis.set_xlim(0.0033, 0.4)
    axis.set_title("Welch power spectrum", loc="left", fontsize=9, fontweight="bold", color=BLUE)
    axis.set_xlabel("Frequency (Hz)", fontsize=7)
    axis.set_ylabel("Power (ms^2/Hz)", fontsize=7)
    _style_chart(axis)


def _draw_poincare(axis: Axes, result: AnalysisResult, rr: FloatArray) -> None:
    if len(rr) < 2:
        _unavailable(axis, "Poincare plot")
        return
    first, second = rr[:-1] * 1_000, rr[1:] * 1_000
    axis.scatter(first, second, s=7, color=BLUE, alpha=0.6, edgecolors="none")
    low = float(min(first.min(), second.min()))
    high = float(max(first.max(), second.max()))
    padding = max((high - low) * 0.08, 10)
    axis.plot([low - padding, high + padding], [low - padding, high + padding], "--", color=GRAY, linewidth=0.6)
    center = np.array([first.mean(), second.mean()])
    for key, direction, color in (
        ("SD1_ms", np.array([-1.0, 1.0]) / math.sqrt(2), ORANGE),
        ("SD2_ms", np.array([1.0, 1.0]) / math.sqrt(2), BLUE),
    ):
        value = result.values.get(key)
        if isinstance(value, (int, float, np.integer, np.floating)) and math.isfinite(float(value)):
            vector = direction * float(value)
            endpoints = np.vstack((center - vector, center + vector))
            axis.plot(endpoints[:, 0], endpoints[:, 1], color=color, linewidth=1.2, label=key[:-3])
    if axis.get_legend_handles_labels()[0]:
        axis.legend(loc="lower right", fontsize=6, frameon=False)
    axis.set_xlim(low - padding, high + padding)
    axis.set_ylim(low - padding, high + padding)
    axis.set_aspect("equal", adjustable="box")
    axis.set_title("Poincare plot", loc="left", fontsize=9, fontweight="bold", color=BLUE)
    axis.set_xlabel("RR[n] (ms)", fontsize=7)
    axis.set_ylabel("RR[n+1] (ms)", fontsize=7)
    _style_chart(axis)


def _draw_table(
    axis: Axes,
    title: str,
    result: AnalysisResult,
    rows: tuple[tuple[str, str], ...],
) -> None:
    axis.axis("off")
    axis.set_title(title, loc="left", fontsize=9, fontweight="bold", color=BLUE, pad=4)
    content = [
        (label, _metric(result, key), PARAMETERS[key].unit.replace("²", "^2"))
        for key, label in rows
    ]
    table = axis.table(
        cellText=content,
        colWidths=(0.58, 0.24, 0.18),
        cellLoc="left",
        bbox=Bbox.from_bounds(0, 0, 1, 0.9),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6.5)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#DCE3E8")
        cell.set_linewidth(0.5)
        cell.set_facecolor(LIGHT_BLUE if row % 2 == 0 else "white")
        if column == 1:
            cell.get_text().set_horizontalalignment("right")
            cell.get_text().set_fontweight("bold")
        if column == 2:
            cell.get_text().set_color(GRAY)


def _draw_header(axis: Axes, result: AnalysisResult) -> None:
    axis.axis("off")
    axis.add_patch(
        FancyBboxPatch(
            (0, 0),
            1,
            1,
            boxstyle="round,pad=0.012",
            facecolor=LIGHT_BLUE,
            edgecolor="#C7DDE8",
            linewidth=0.8,
            transform=axis.transAxes,
        )
    )
    method = METHODS[result.method_id].label if result.method_id in METHODS else result.method_id
    method = method.replace("–", "-").replace("—", "-")
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    metadata = (
        ("Recording", result.source_path.name),
        ("Method", method),
        ("Duration", _metric_with_unit(result, "duration_sec", "s")),
        ("Sampling rate", f"{_text(result.sampling_rate)} Hz"),
        ("R peaks", _metric(result, "r_peak_count")),
        ("RR raw / valid", f"{_metric(result, 'rr_count_raw')} / {_metric(result, 'rr_count_valid')}"),
        ("Artifacts removed", _metric_with_unit(result, "rr_removed_percent", "%")),
        ("Generated", generated),
    )
    axis.text(0.025, 0.82, "BIOPAC ECG / HRV ANALYSIS", fontsize=15, fontweight="bold", color=BLUE)
    for index, (label, value) in enumerate(metadata):
        column, row = divmod(index, 4)
        x = 0.025 + column * 0.49
        y = 0.61 - row * 0.14
        axis.text(x, y, f"{label}:", fontsize=6.8, fontweight="bold", color=GRAY)
        axis.text(x + 0.13, y, value, fontsize=6.8, color="#263238")
    warnings = " | ".join(result.warnings) if result.warnings else "None"
    warnings = warnings.replace("–", "-").replace("—", "-")
    axis.text(0.025, 0.055, "Warnings:", fontsize=6.8, fontweight="bold", color=GRAY)
    axis.text(
        0.11,
        0.055,
        "\n".join(textwrap.wrap(warnings, width=125)),
        fontsize=6.6,
        color="#7A3E16" if result.warnings else GRAY,
        va="bottom",
    )


def export_pdf_report(result: AnalysisResult, path: str | Path) -> Path:
    """Export a curated, one-page A4 PDF report."""
    destination = Path(path)
    figure = Figure(figsize=(8.27, 11.69), facecolor="white")
    grid = figure.add_gridspec(
        6,
        2,
        height_ratios=(1.05, 1.45, 1.45, 0.95, 0.95, 0.18),
        left=0.065,
        right=0.935,
        top=0.965,
        bottom=0.035,
        hspace=0.64,
        wspace=0.34,
    )
    _draw_header(figure.add_subplot(grid[0, :]), result)

    rr, times = _rr_data(result.context)
    tachogram_grid = grid[1, 0].subgridspec(2, 1, height_ratios=(1.45, 1), hspace=0.08)
    _draw_tachogram(
        figure.add_subplot(tachogram_grid[0]),
        figure.add_subplot(tachogram_grid[1]),
        rr,
        times,
    )
    _draw_histogram(figure.add_subplot(grid[1, 1]), rr)
    _draw_spectrum(figure.add_subplot(grid[2, 0]), rr, times)
    _draw_poincare(figure.add_subplot(grid[2, 1]), result, rr)

    tables = (
        (
            "Time domain",
            (
                ("Mean_HR_bpm", "Mean heart rate"),
                ("Mean_RR_ms", "Mean RR"),
                ("SDNN_ms", "SDNN"),
                ("RMSSD_ms", "RMSSD"),
                ("pNN50_percent", "pNN50"),
            ),
        ),
        (
            "Frequency domain",
            (
                ("VLF_power_ms2", "VLF power"),
                ("LF_power_ms2", "LF power"),
                ("HF_power_ms2", "HF power"),
                ("Total_power_ms2", "Total power"),
                ("LF_HF_ratio", "LF/HF ratio"),
            ),
        ),
        (
            "Nonlinear",
            (
                ("SD1_ms", "SD1"),
                ("SD2_ms", "SD2"),
                ("SD1_SD2_ratio", "SD1/SD2 ratio"),
                ("ApEn", "Approx. entropy"),
                ("SampEn", "Sample entropy"),
            ),
        ),
        (
            "Recording quality",
            (
                ("duration_sec", "Duration"),
                ("r_peak_count", "R peaks"),
                ("rr_count_raw", "RR intervals (raw)"),
                ("rr_count_valid", "RR intervals (valid)"),
                ("rr_removed_percent", "Artifacts removed"),
            ),
        ),
    )
    for cell, (title, rows) in zip(
        (grid[3, 0], grid[3, 1], grid[4, 0], grid[4, 1]), tables, strict=True
    ):
        _draw_table(figure.add_subplot(cell), title, result, rows)

    footer = figure.add_subplot(grid[5, :])
    footer.axis("off")
    footer.axhline(0.95, color="#C7D1D7", linewidth=0.6)
    footer.text(
        0,
        0.15,
        "Research use only - not a medical diagnosis",
        fontsize=7,
        color=GRAY,
        fontweight="bold",
    )
    footer.text(1, 0.15, "BIOPAC HRV Analyzer", ha="right", fontsize=7, color=GRAY)
    try:
        with PdfPages(destination) as pdf:
            pdf.savefig(figure)
    except OSError as exc:
        raise ValueError(f"Could not export PDF: {exc}") from exc
    return destination
