from __future__ import annotations

import csv
import gzip
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication

import desktop_analysis as analysis
from desktop_report import export_pdf_report
from desktop_app import AnalysisWorker


class RecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_csv(self, name: str, header: str, rows: list[str]) -> Path:
        path = self.root / name
        text = header + "\n" + "\n".join(rows) + "\n"
        if name.endswith(".gz"):
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def test_biopac_bom_detection_and_250_hz_inference(self) -> None:
        rows = [f"{index / 250:.3f},{math.sin(index / 20):.5f}" for index in range(1250)]
        path = self.write_csv("recording.csv", "\ufeffsec,CH1", rows)
        preview = analysis.inspect_recording(path)
        recording = analysis.load_recording(path)
        self.assertEqual(preview.time_column, "sec")
        self.assertEqual(preview.ecg_column, "CH1")
        self.assertAlmostEqual(recording.sampling_rate, 250.0, places=6)

    def test_manual_columns_and_sampling_rate_override(self) -> None:
        rows = [f"{index / 20:.2f},{index}" for index in range(120)]
        path = self.write_csv("custom.csv", "clock,lead", rows)
        recording = analysis.load_recording(
            path, analysis.LoadOverrides("clock", "lead", 20.0)
        )
        self.assertEqual(recording.time_column, "clock")
        self.assertEqual(recording.ecg_column, "lead")
        self.assertEqual(recording.sampling_rate, 20.0)

    def test_csv_gz(self) -> None:
        rows = [f"{index / 10:.1f},{index}" for index in range(60)]
        recording = analysis.load_recording(self.write_csv("recording.csv.gz", "time,ECG", rows))
        self.assertEqual(len(recording.ecg), 60)
        self.assertAlmostEqual(recording.sampling_rate, 10.0)

    def test_invalid_inputs(self) -> None:
        cases: list[tuple[str, str, list[str], analysis.LoadOverrides | None]] = [
            ("empty.csv", "sec,CH1", [], None),
            ("nonnumeric.csv", "sec,CH1", [f"{index / 10},x" for index in range(60)], None),
            ("nonmonotonic.csv", "sec,CH1", ["0,1", "1,2", "1,3"] + [f"{index},1" for index in range(3, 60)], analysis.LoadOverrides(sampling_rate=10)),
            ("missing.csv", "seconds,lead", [f"{index},1" for index in range(60)], analysis.LoadOverrides(sampling_rate=10)),
            ("short.csv", "sec,CH1", [f"{index / 250},1" for index in range(20)], None),
        ]
        for name, header, rows, overrides in cases:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    analysis.load_recording(self.write_csv(name, header, rows), overrides)
        invalid = self.root / "recording.txt"
        invalid.write_text("sec,CH1\n0,1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            analysis.load_recording(invalid)
        valid = self.write_csv(
            "zero-rate.csv", "sec,CH1", [f"{index / 10},1" for index in range(60)]
        )
        with self.assertRaises(ValueError):
            analysis.load_recording(valid, analysis.LoadOverrides(sampling_rate=0))


class MethodTests(unittest.TestCase):
    def test_method_runners_pass_explicit_method_ids(self) -> None:
        class FakeNeuroKit:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, bool | None]] = []

            def ecg_clean(self, ecg: np.ndarray, *, sampling_rate: float, method: str) -> np.ndarray:
                self.calls.append(("clean", method, None))
                return ecg

            def ecg_peaks(
                self,
                ecg: np.ndarray,
                *,
                sampling_rate: float,
                method: str,
                correct_artifacts: bool,
            ) -> tuple[dict[str, object], dict[str, list[int]]]:
                self.calls.append(("peaks", method, correct_artifacts))
                return {}, {"ECG_R_Peaks": [1, 3]}

        fake = FakeNeuroKit()
        with patch.object(analysis, "nk", fake):
            analysis.run_pantompkins1985(np.zeros(10), 250)
            analysis.run_neurokit(np.zeros(10), 250)
        self.assertEqual(
            fake.calls,
            [
                ("clean", "pantompkins1985", None),
                ("peaks", "pantompkins1985", True),
                ("clean", "neurokit", None),
                ("peaks", "neurokit", True),
            ],
        )

    def test_registry_result_export_and_unavailable_rendering(self) -> None:
        recording = analysis.Recording(
            Path("source.csv"), np.zeros(1_000), 100.0, "sec", "CH1"
        )

        def runner(ecg: np.ndarray, sampling_rate: float) -> tuple[np.ndarray, np.ndarray]:
            return ecg, np.arange(100, 1_000, 100, dtype=np.int64)

        spec = analysis.MethodSpec("test", "Test", runner)
        with patch.dict(analysis.METHODS, {"test": spec}):
            result = analysis.analyze_recording(recording, "test")
        self.assertEqual(set(analysis.PARAMETERS), set(analysis.legacy.safe_nan_features()))
        self.assertEqual(set(analysis.PARAMETERS), set(result.values))
        self.assertIsNotNone(result.context)
        self.assertEqual(analysis.render_metric(float("nan"), 2), "—")
        self.assertEqual(analysis.render_metric(float("inf"), 2), "—")

        with tempfile.TemporaryDirectory() as directory:
            destination = analysis.export_result(result, Path(directory) / "result.csv")
            with destination.open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
        self.assertEqual(row["source_filename"], "source.csv")
        self.assertEqual(row["selected_method"], "test")
        self.assertTrue(set(analysis.PARAMETERS).issubset(row))


class ReportTests(unittest.TestCase):
    def test_pdf_export_with_analysis_context(self) -> None:
        rr = 0.8 + 0.05 * np.sin(np.linspace(0, 12 * np.pi, 100))
        times = np.cumsum(rr)
        context = analysis.AnalysisContext(
            np.zeros(10_000),
            np.zeros(10_000),
            100.0,
            np.arange(100, 10_000, 100, dtype=np.int64),
            rr,
            times,
            rr,
            times,
        )
        values = dict(analysis.legacy.safe_nan_features())
        values.update(
            {
                "duration_sec": 100.0,
                "sampling_rate_Hz": 100.0,
                "r_peak_count": 99,
                "rr_count_raw": 100,
                "rr_count_valid": 100,
                "rr_removed_percent": 0.0,
                **analysis._time_features(context),
                **analysis._frequency_features(context),
                **analysis._nonlinear_features(context),
            }
        )
        result = analysis.AnalysisResult(
            Path("synthetic.csv"), "pantompkins1985", 100.0, values, context=context
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = export_pdf_report(result, Path(directory) / "report.pdf")
            data = destination.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertGreater(len(data), 10_000)

    def test_pdf_export_handles_missing_and_insufficient_data(self) -> None:
        result = analysis.AnalysisResult(
            Path("short.csv"),
            "unknown",
            1.0,
            {"duration_sec": float("nan")},
            ("Too few valid RR intervals for HRV calculation.",),
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = export_pdf_report(result, Path(directory) / "short.pdf")
            data = destination.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertGreater(len(data), 1_000)


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_worker_delivers_completion_and_errors(self) -> None:
        recording = analysis.Recording(Path("source.csv"), np.zeros(10), 1, None, "ECG")
        result = analysis.AnalysisResult(Path("source.csv"), "test", 1, {})
        completed: list[object] = []
        failed: list[str] = []
        worker = AnalysisWorker(recording, "test", lambda _recording, _method: result)
        worker.completed.connect(completed.append)
        worker.failed.connect(failed.append)
        worker.run()
        self.assertEqual(completed, [result])
        self.assertEqual(failed, [])

        def fail(_recording: analysis.Recording, _method: str) -> analysis.AnalysisResult:
            raise RuntimeError("worker error")

        error_worker = AnalysisWorker(recording, "test", fail)
        error_worker.failed.connect(failed.append)
        error_worker.run()
        self.assertEqual(failed, ["worker error"])


if __name__ == "__main__":
    unittest.main()
