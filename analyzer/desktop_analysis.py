"""GUI-independent loading, ECG analysis, metric registry, and CSV export."""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import neurokit2 as nk
import numpy as np
import numpy.typing as npt
import pandas as pd

import ecg_hrv_pantompkins_gui as legacy


FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
MetricValue = float | int | str
MethodRunner = Callable[[FloatArray, float], tuple[FloatArray, IntArray]]


@dataclass(frozen=True)
class MethodSpec:
    id: str
    label: str
    run: MethodRunner


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    section: str
    label: str
    unit: str
    precision: int


@dataclass(frozen=True)
class LoadOverrides:
    time_column: str | None = None
    ecg_column: str | None = None
    sampling_rate: float | None = None


@dataclass(frozen=True)
class RecordingPreview:
    columns: tuple[str, ...]
    time_column: str | None
    ecg_column: str | None
    inferred_sampling_rate: float | None


@dataclass(frozen=True)
class Recording:
    path: Path
    ecg: FloatArray
    sampling_rate: float
    time_column: str | None
    ecg_column: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisContext:
    raw_ecg: FloatArray
    cleaned_ecg: FloatArray
    sampling_rate: float
    r_peaks: IntArray
    raw_rr: FloatArray
    raw_rr_times: FloatArray
    valid_rr: FloatArray
    valid_rr_times: FloatArray


@dataclass(frozen=True)
class AnalysisResult:
    source_path: Path
    method_id: str
    sampling_rate: float
    values: Mapping[str, MetricValue]
    warnings: tuple[str, ...] = ()


def _run_method(ecg: FloatArray, sampling_rate: float, method: str) -> tuple[FloatArray, IntArray]:
    cleaned = np.asarray(
        nk.ecg_clean(ecg, sampling_rate=sampling_rate, method=method), dtype=np.float64
    )
    _, info = nk.ecg_peaks(
        cleaned,
        sampling_rate=sampling_rate,
        method=method,
        correct_artifacts=True,
    )
    peaks = np.asarray(info.get("ECG_R_Peaks", ()), dtype=np.int64)
    return cleaned, peaks[(peaks >= 0) & (peaks < len(cleaned))]


def run_pantompkins1985(ecg: FloatArray, sampling_rate: float) -> tuple[FloatArray, IntArray]:
    return _run_method(ecg, sampling_rate, "pantompkins1985")


def run_neurokit(ecg: FloatArray, sampling_rate: float) -> tuple[FloatArray, IntArray]:
    return _run_method(ecg, sampling_rate, "neurokit")


METHODS: dict[str, MethodSpec] = {
    spec.id: spec
    for spec in (
        MethodSpec("pantompkins1985", "Pan–Tompkins 1985", run_pantompkins1985),
        MethodSpec("neurokit", "NeuroKit", run_neurokit),
    )
}


def _p(key: str, section: str, label: str, unit: str = "", precision: int = 2) -> ParameterSpec:
    return ParameterSpec(key, section, label, unit, precision)


PARAMETERS: dict[str, ParameterSpec] = {
    spec.key: spec
    for spec in (
        _p("duration_sec", "Recording quality", "Duration", "s"),
        _p("ecg_method", "Recording quality", "ECG method", precision=0),
        _p("sampling_rate_Hz", "Recording quality", "Sampling rate", "Hz"),
        _p("r_peak_count", "Recording quality", "R peaks", "count", 0),
        _p("rr_count_raw", "Recording quality", "RR intervals (raw)", "count", 0),
        _p("rr_count_valid", "Recording quality", "RR intervals (valid)", "count", 0),
        _p("rr_removed_count", "Recording quality", "RR intervals removed", "count", 0),
        _p("rr_removed_percent", "Recording quality", "RR intervals removed", "%"),
        _p("mean_r_peak_amplitude_cleaned", "Recording quality", "Mean cleaned R-peak amplitude", "signal units", 4),
        _p("std_r_peak_amplitude_cleaned", "Recording quality", "R-peak amplitude SD", "signal units", 4),
        _p("Mean_RR_ms", "Time domain", "Mean RR", "ms"),
        _p("Median_RR_ms", "Time domain", "Median RR", "ms"),
        _p("Mean_HR_bpm", "Time domain", "Mean heart rate", "bpm"),
        _p("Mean_inst_HR_bpm", "Time domain", "Mean instantaneous heart rate", "bpm"),
        _p("Min_HR_bpm", "Time domain", "Minimum heart rate", "bpm"),
        _p("Max_HR_bpm", "Time domain", "Maximum heart rate", "bpm"),
        _p("HR_range_bpm", "Time domain", "Heart-rate range", "bpm"),
        _p("SDNN_ms", "Time domain", "SDNN", "ms"),
        _p("RMSSD_ms", "Time domain", "RMSSD", "ms"),
        _p("SDSD_ms", "Time domain", "SDSD", "ms"),
        _p("NN50", "Time domain", "NN50", "count", 0),
        _p("pNN50_percent", "Time domain", "pNN50", "%"),
        _p("CVRR", "Time domain", "CVRR", precision=4),
        _p("RR_IQR_ms", "Time domain", "RR interquartile range", "ms"),
        _p("VLF_power_ms2", "Frequency domain", "VLF power", "ms²"),
        _p("LF_power_ms2", "Frequency domain", "LF power", "ms²"),
        _p("HF_power_ms2", "Frequency domain", "HF power", "ms²"),
        _p("Total_power_ms2", "Frequency domain", "Total power", "ms²"),
        _p("LF_HF_ratio", "Frequency domain", "LF/HF ratio", precision=3),
        _p("LFnu_percent", "Frequency domain", "LF normalized power", "%"),
        _p("HFnu_percent", "Frequency domain", "HF normalized power", "%"),
        _p("LF_peak_Hz", "Frequency domain", "LF peak", "Hz", 3),
        _p("HF_peak_Hz", "Frequency domain", "HF peak", "Hz", 3),
        _p("SD1_ms", "Nonlinear HRV", "SD1", "ms"),
        _p("SD2_ms", "Nonlinear HRV", "SD2", "ms"),
        _p("SD1_SD2_ratio", "Nonlinear HRV", "SD1/SD2 ratio", precision=3),
        _p("ApEn", "Nonlinear HRV", "Approximate entropy", precision=4),
        _p("SampEn", "Nonlinear HRV", "Sample entropy", precision=4),
        _p("Exploratory_EDR_rate_Hz", "Auxiliary ECG / EDR", "Exploratory EDR rate", "Hz", 3),
        _p("Exploratory_EDR_rate_bpm", "Auxiliary ECG / EDR", "Exploratory EDR rate", "bpm"),
        _p("Exploratory_EDR_variability_sec", "Auxiliary ECG / EDR", "Exploratory EDR variability", "s", 3),
        _p("EECG_mean", "Auxiliary ECG / EDR", "Mean ECG envelope", "signal units", 4),
        _p("EECG_std", "Auxiliary ECG / EDR", "ECG envelope SD", "signal units", 4),
        _p("mean_RR_decrease_ms", "Auxiliary ECG / EDR", "Mean RR decrease", "ms"),
        _p("mean_RR_increase_ms", "Auxiliary ECG / EDR", "Mean RR increase", "ms"),
    )
}


def _validate_path(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"File does not exist: {path}")
    lower_name = path.name.lower()
    if not (lower_name.endswith(".csv") or lower_name.endswith(".csv.gz")):
        raise ValueError("Select a .csv or .csv.gz recording.")


def _read_csv(path: Path, nrows: int | None = None) -> pd.DataFrame:
    _validate_path(path)
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", nrows=nrows)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Could not read CSV: {exc}") from exc
    if not len(frame.columns):
        raise ValueError("CSV has no columns.")
    return frame


def _detect_column(columns: tuple[str, ...], candidates: tuple[str, ...]) -> str | None:
    normalized = {column.strip().lower(): column for column in columns}
    return next((normalized[name] for name in candidates if name in normalized), None)


def _numeric_time(frame: pd.DataFrame, column: str) -> FloatArray:
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=np.float64)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError(f"Time column '{column}' must contain finite numeric values.")
    differences = np.diff(values)
    if not np.all(differences > 0):
        raise ValueError(f"Time column '{column}' must be strictly increasing.")
    return differences


def inspect_recording(path: str | Path) -> RecordingPreview:
    source = Path(path)
    frame = _read_csv(source, nrows=10_000)
    columns = tuple(str(column) for column in frame.columns)
    time_column = _detect_column(columns, ("sec", "time"))
    ecg_column = _detect_column(columns, ("ch1", "ecg"))
    sampling_rate = None
    if time_column is not None and len(frame) >= 2:
        differences = _numeric_time(frame, time_column)
        sampling_rate = 1.0 / float(np.median(differences))
    return RecordingPreview(columns, time_column, ecg_column, sampling_rate)


def load_recording(
    path: str | Path, overrides: LoadOverrides | None = None
) -> Recording:
    source = Path(path)
    frame = _read_csv(source)
    if frame.empty:
        raise ValueError("CSV contains no samples.")
    columns = tuple(str(column) for column in frame.columns)
    choices = overrides or LoadOverrides()
    time_column = (
        _detect_column(columns, ("sec", "time"))
        if choices.time_column is None
        else choices.time_column or None
    )
    ecg_column = choices.ecg_column or _detect_column(columns, ("ch1", "ecg"))

    for role, column in (("time", time_column), ("ECG", ecg_column)):
        if column is not None and column not in frame.columns:
            raise ValueError(f"Selected {role} column '{column}' was not found.")
    if ecg_column is None:
        raise ValueError("No ECG column detected; select a CH1 or ECG column.")

    inferred_rate = None
    if time_column is not None:
        inferred_rate = 1.0 / float(np.median(_numeric_time(frame, time_column)))
    sampling_rate = choices.sampling_rate if choices.sampling_rate is not None else inferred_rate
    if sampling_rate is None or not math.isfinite(sampling_rate) or sampling_rate <= 0:
        raise ValueError("Sampling rate must be a positive finite number.")

    numeric = pd.to_numeric(frame[ecg_column], errors="coerce").to_numpy(dtype=np.float64)
    finite_count = int(np.isfinite(numeric).sum())
    if finite_count == 0:
        raise ValueError(f"ECG column '{ecg_column}' contains no numeric samples.")
    warnings: list[str] = []
    if finite_count != len(numeric):
        warnings.append(f"Interpolated {len(numeric) - finite_count} missing or nonnumeric ECG samples.")
    ecg = np.asarray(legacy.sanitize_ecg(numeric), dtype=np.float64)
    minimum_samples = math.ceil(5 * sampling_rate)
    if len(ecg) < minimum_samples:
        raise ValueError(f"Recording must contain at least 5 seconds ({minimum_samples} samples).")
    return Recording(source, ecg, sampling_rate, time_column, ecg_column, tuple(warnings))


def _quality_features(context: AnalysisContext, method_id: str) -> dict[str, MetricValue]:
    raw_count = len(context.raw_rr)
    removed_count = raw_count - len(context.valid_rr)
    values: dict[str, MetricValue] = {
        "duration_sec": len(context.raw_ecg) / context.sampling_rate,
        "ecg_method": method_id,
        "sampling_rate_Hz": context.sampling_rate,
        "r_peak_count": len(context.r_peaks),
        "rr_count_raw": raw_count,
        "rr_count_valid": len(context.valid_rr),
        "rr_removed_count": removed_count,
        "rr_removed_percent": removed_count / raw_count * 100 if raw_count else np.nan,
    }
    if len(context.r_peaks):
        amplitudes = context.cleaned_ecg[context.r_peaks]
        values["mean_r_peak_amplitude_cleaned"] = float(np.mean(amplitudes))
        values["std_r_peak_amplitude_cleaned"] = (
            float(np.std(amplitudes, ddof=1)) if len(amplitudes) > 1 else np.nan
        )
    return values


def _time_features(context: AnalysisContext) -> dict[str, MetricValue]:
    return dict(legacy.time_domain_hrv(context.valid_rr))


def _frequency_features(context: AnalysisContext) -> dict[str, MetricValue]:
    return dict(legacy.frequency_domain_hrv(context.valid_rr, context.valid_rr_times, interp_fs=4.0))


def _nonlinear_features(context: AnalysisContext) -> dict[str, MetricValue]:
    return {
        **legacy.poincare_hrv(context.valid_rr),
        **legacy.nonlinear_hrv(context.valid_rr),
    }


def _auxiliary_features(context: AnalysisContext) -> dict[str, MetricValue]:
    edr_rate, edr_variability = legacy.compute_exploratory_edr(
        context.cleaned_ecg, context.r_peaks, context.r_peaks / context.sampling_rate
    )
    envelope_mean, envelope_std = legacy.compute_eecg(context.cleaned_ecg)
    rr_decrease, rr_increase = legacy.acceleration_deceleration_capacity_simple(context.valid_rr)
    return {
        "Exploratory_EDR_rate_Hz": edr_rate,
        "Exploratory_EDR_rate_bpm": edr_rate * 60 if not np.isnan(edr_rate) else np.nan,
        "Exploratory_EDR_variability_sec": edr_variability,
        "EECG_mean": envelope_mean,
        "EECG_std": envelope_std,
        "mean_RR_decrease_ms": rr_decrease * 1000 if not np.isnan(rr_decrease) else np.nan,
        "mean_RR_increase_ms": rr_increase * 1000 if not np.isnan(rr_increase) else np.nan,
    }


FEATURE_CALCULATORS: tuple[
    Callable[[AnalysisContext], dict[str, MetricValue]], ...
] = (_time_features, _frequency_features, _nonlinear_features, _auxiliary_features)


def analyze_recording(recording: Recording, method_id: str) -> AnalysisResult:
    try:
        method = METHODS[method_id]
    except KeyError as exc:
        raise ValueError(f"Unknown analysis method: {method_id}") from exc
    cleaned, r_peaks = method.run(recording.ecg, recording.sampling_rate)
    raw_rr, _, raw_rr_times = legacy.compute_rr_intervals(r_peaks, fs=recording.sampling_rate)
    valid_rr, valid_rr_times, _ = legacy.filter_rr_intervals(raw_rr, raw_rr_times)
    context = AnalysisContext(
        recording.ecg,
        cleaned,
        recording.sampling_rate,
        r_peaks,
        np.asarray(raw_rr, dtype=np.float64),
        np.asarray(raw_rr_times, dtype=np.float64),
        np.asarray(valid_rr, dtype=np.float64),
        np.asarray(valid_rr_times, dtype=np.float64),
    )
    values: dict[str, MetricValue] = dict(legacy.safe_nan_features())
    values.update(_quality_features(context, method_id))
    if len(valid_rr) >= 3:
        for calculate in FEATURE_CALCULATORS:
            values.update(calculate(context))
    warnings = list(recording.warnings)
    if len(valid_rr) < 3:
        warnings.append("Too few valid RR intervals for HRV calculation.")
    elif len(raw_rr) and len(valid_rr) / len(raw_rr) < 0.8:
        warnings.append("More than 20% of RR intervals were removed as artifacts.")
    return AnalysisResult(recording.path, method_id, recording.sampling_rate, values, tuple(warnings))


def render_metric(value: MetricValue | None, precision: int) -> str:
    if value is None or (isinstance(value, (float, np.floating)) and not math.isfinite(float(value))):
        return "—"
    if isinstance(value, str):
        return value
    return f"{float(value):.{precision}f}"


def export_result(result: AnalysisResult, path: str | Path) -> Path:
    destination = Path(path)
    row: dict[str, MetricValue | None] = {
        "source_filename": result.source_path.name,
        "selected_method": result.method_id,
        "effective_sampling_rate_Hz": result.sampling_rate,
    }
    row.update({key: result.values.get(key) for key in PARAMETERS})
    clean_row = {
        key: "" if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)) else value
        for key, value in row.items()
    }
    try:
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(clean_row))
            writer.writeheader()
            writer.writerow(clean_row)
    except OSError as exc:
        raise ValueError(f"Could not export CSV: {exc}") from exc
    return destination
