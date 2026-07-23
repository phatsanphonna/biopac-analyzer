"""Offline PySide6 ECG/HRV desktop application."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_analysis import (
    METHODS,
    PARAMETERS,
    AnalysisResult,
    LoadOverrides,
    Recording,
    analyze_recording,
    export_result,
    inspect_recording,
    load_recording,
    render_metric,
)
from desktop_report import export_pdf_report


class AnalysisWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        recording: Recording,
        method_id: str,
        analyze: Callable[[Recording, str], AnalysisResult] = analyze_recording,
    ) -> None:
        super().__init__()
        self.recording = recording
        self.method_id = method_id
        self.analyze = analyze

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self.analyze(self.recording, self.method_id))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BIOPAC ECG / HRV Analyzer")
        self.resize(880, 680)
        self.source_path: Path | None = None
        self.result: AnalysisResult | None = None
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.tables: dict[str, QTableWidget] = {}

        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        inputs = QGroupBox("Recording and analysis settings")
        grid = QGridLayout(inputs)
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        browse = QPushButton("Choose CSV…")
        browse.clicked.connect(self.choose_file)
        grid.addWidget(QLabel("Recording"), 0, 0)
        grid.addWidget(self.file_edit, 0, 1, 1, 3)
        grid.addWidget(browse, 0, 4)

        self.time_combo = QComboBox()
        self.time_combo.setEditable(True)
        self.ecg_combo = QComboBox()
        self.ecg_combo.setEditable(True)
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.01, 100_000)
        self.rate_spin.setDecimals(4)
        self.rate_spin.setValue(250)
        self.rate_spin.setSuffix(" Hz")
        self.method_combo = QComboBox()
        for method in METHODS.values():
            self.method_combo.addItem(method.label, method.id)
        grid.addWidget(QLabel("Time column"), 1, 0)
        grid.addWidget(self.time_combo, 1, 1)
        grid.addWidget(QLabel("ECG column"), 1, 2)
        grid.addWidget(self.ecg_combo, 1, 3)
        grid.addWidget(QLabel("Sampling rate"), 2, 0)
        grid.addWidget(self.rate_spin, 2, 1)
        grid.addWidget(QLabel("Processing method"), 2, 2)
        grid.addWidget(self.method_combo, 2, 3)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.start_analysis)
        grid.addWidget(self.analyze_button, 2, 4)
        layout.addWidget(inputs)
        self.inputs = inputs

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("Choose a CSV or CSV.GZ recording to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.tabs = QTabWidget()
        self.tabs.setVisible(False)
        for section in dict.fromkeys(spec.section for spec in PARAMETERS.values()):
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(("Parameter", "Value", "Unit"))
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.tables[section] = table
            self.tabs.addTab(table, section)
        layout.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.export_button = QPushButton("Export CSV…")
        self.export_button.clicked.connect(self.export_csv)
        self.pdf_button = QPushButton("Export PDF…")
        self.pdf_button.clicked.connect(self.export_pdf)
        self.another_button = QPushButton("Analyze another file")
        self.another_button.clicked.connect(self.reset)
        actions.addWidget(self.export_button)
        actions.addWidget(self.pdf_button)
        actions.addWidget(self.another_button)
        self.actions_widget = QWidget()
        self.actions_widget.setLayout(actions)
        self.actions_widget.setVisible(False)
        layout.addWidget(self.actions_widget)

    @Slot()
    def choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose ECG recording", "", "CSV recordings (*.csv *.csv.gz)"
        )
        if not filename:
            return
        try:
            preview = inspect_recording(filename)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid recording", str(exc))
            return
        self.source_path = Path(filename)
        self.file_edit.setText(filename)
        self.time_combo.clear()
        self.time_combo.addItem("")
        self.time_combo.addItems(preview.columns)
        self.time_combo.setCurrentText(preview.time_column or "")
        self.ecg_combo.clear()
        self.ecg_combo.addItems(preview.columns)
        self.ecg_combo.setCurrentText(preview.ecg_column or "")
        if preview.inferred_sampling_rate is not None:
            self.rate_spin.setValue(preview.inferred_sampling_rate)
        self.analyze_button.setEnabled(True)
        self.status.setText("Review the detected settings, then choose Analyze.")

    @Slot()
    def start_analysis(self) -> None:
        if self.source_path is None:
            return
        try:
            recording = load_recording(
                self.source_path,
                LoadOverrides(
                    time_column=self.time_combo.currentText().strip(),
                    ecg_column=self.ecg_combo.currentText().strip(),
                    sampling_rate=self.rate_spin.value(),
                ),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid recording", str(exc))
            return
        method_id = str(self.method_combo.currentData())
        self.set_busy(True)
        self.status.setText("Analyzing ECG and HRV…")
        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(recording, method_id)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.completed.connect(self.analysis_finished)
        self.worker.failed.connect(self.analysis_failed)
        self.worker.completed.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._thread_finished)
        self.worker_thread.start()

    def set_busy(self, busy: bool) -> None:
        self.inputs.setEnabled(not busy)
        self.progress.setVisible(busy)

    @Slot(object)
    def analysis_finished(self, result: object) -> None:
        if not isinstance(result, AnalysisResult):
            self.analysis_failed("Analysis returned an unexpected result.")
            return
        self.result = result
        for section, table in self.tables.items():
            specs = [spec for spec in PARAMETERS.values() if spec.section == section]
            table.setRowCount(len(specs))
            for row, spec in enumerate(specs):
                table.setItem(row, 0, QTableWidgetItem(spec.label))
                table.setItem(row, 1, QTableWidgetItem(render_metric(result.values.get(spec.key), spec.precision)))
                table.setItem(row, 2, QTableWidgetItem(spec.unit))
        self.tabs.setVisible(True)
        self.actions_widget.setVisible(True)
        self.set_busy(False)
        self.status.setText("Analysis complete." + ("\n" + "\n".join(result.warnings) if result.warnings else ""))

    @Slot(str)
    def analysis_failed(self, message: str) -> None:
        self.set_busy(False)
        self.status.setText("Analysis failed.")
        QMessageBox.critical(self, "Analysis failed", message)

    @Slot()
    def _thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None

    @Slot()
    def export_csv(self) -> None:
        if self.result is None:
            return
        destination = self._default_export_path("csv")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export analysis",
            str(destination),
            "CSV files (*.csv)",
        )
        if not filename:
            return
        try:
            export_result(self.result, filename)
        except ValueError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.status.setText(f"Exported {filename}")

    def _default_export_path(self, extension: str) -> Path:
        assert self.result is not None
        name = self.result.source_path.name
        if name.lower().endswith(".gz"):
            name = name[:-3]
        if name.lower().endswith(".csv"):
            name = name[:-4]
        return self.result.source_path.with_name(f"{name}_hrv.{extension}")

    @Slot()
    def export_pdf(self) -> None:
        if self.result is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF report",
            str(self._default_export_path("pdf")),
            "PDF files (*.pdf)",
        )
        if not filename:
            return
        try:
            export_pdf_report(self.result, filename)
        except ValueError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.status.setText(f"Exported {filename}")

    @Slot()
    def reset(self) -> None:
        self.source_path = None
        self.result = None
        self.file_edit.clear()
        self.time_combo.clear()
        self.ecg_combo.clear()
        self.tabs.setVisible(False)
        self.actions_widget.setVisible(False)
        self.analyze_button.setEnabled(False)
        self.status.setText("Choose a CSV or CSV.GZ recording to begin.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        event.accept()


def main() -> int:
    if "--smoke-test" in sys.argv:
        return 0 if METHODS and PARAMETERS else 1
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
