import { useState } from "react";
import { useTranslation } from "react-i18next";
import Navbar from "./components/react/navbar";
import { FileUploader } from "./components/react/FileUploader";
import { LoadingState } from "./components/react/LoadingState";
import { ReportHeader } from "./components/react/ReportHeader";
import { DiagnosticSummary } from "./components/react/DiagnosticSummary";
import { FrequencySummary } from "./components/react/FrequencySummary";
import {
  parseCSV,
  analyzeSignals,
  generateSyntheticData,
} from "./lib/signalProcessor";
import type { AnalysisResults } from "./lib/signalProcessor";

function App() {
  const { t } = useTranslation();
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  // File processing handler
  const handleFileSelect = async (file: File) => {
    setFileName(file.name);
    setIsAnalyzing(true);
    setError(null);

    try {
      const compressed = await new Response(
        file.stream().pipeThrough(new CompressionStream("gzip")),
      ).blob();

      if (compressed.size > 4_000_000) {
        setError("The CSV is still too large after compression.");
        setIsAnalyzing(false);
        return;
      }

      const formData = new FormData();
      formData.append("file", compressed, `${file.name}.gz`);

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error("Backend response error");
      }

      setResults(await response.json());
      setIsAnalyzing(false);
    } catch (err) {
      console.warn(
        t("connectionFailed"),
        err,
      );

      // Execute client-side fallback
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const text = e.target?.result as string;
          setTimeout(() => {
            try {
              const data = parseCSV(text);
              const analysisResults = analyzeSignals(data, file.name);
              setResults(analysisResults);
              setIsAnalyzing(false);
            } catch (localErr: any) {
              console.error(localErr);
              setError(
                localErr.message ||
                  t("csvError"),
              );
              setIsAnalyzing(false);
            }
          }, 100);
        } catch (readErr) {
          setError(t("readError"));
          setIsAnalyzing(false);
        }
      };
      reader.onerror = () => {
        setError(t("fileReadError"));
        setIsAnalyzing(false);
      };
      reader.readAsText(file);
    }
  };

  const loadDemoData = () => {
    setIsAnalyzing(true);
    setError(null);
    setFileName("synthetic_demo_ecg.csv");

    setTimeout(() => {
      try {
        const data = generateSyntheticData();
        const analysisResults = analyzeSignals(data, "synthetic_demo_ecg.csv");
        setResults(analysisResults);
        setIsAnalyzing(false);
      } catch (err) {
        setError(t("demoError"));
        setIsAnalyzing(false);
      }
    }, 300);
  };

  const resetAll = () => {
    setResults(null);
    setFileName("");
    setError(null);
  };

  return (
    <div className="min-h-screen bg-muted/10 flex flex-col font-sans">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-8 max-w-5xl flex flex-col justify-center">
        {isAnalyzing ? (
          <LoadingState />
        ) : !results ? (
          <FileUploader
            onFileSelect={handleFileSelect}
            onLoadDemo={loadDemoData}
            error={error}
          />
        ) : (
          <div className="space-y-6 py-6 print:py-0 print:space-y-8">
            <ReportHeader
              fileName={fileName}
              duration={results.duration}
              sampleRate={results.sampleRate}
              onPrint={() => window.print()}
              onReset={resetAll}
            />

            <div className="grid grid-cols-2 gap-4">
              <DiagnosticSummary
                meanRR={results.meanRR}
                avgHeartRate={results.avgHeartRate}
                minHR={results.minHR}
                sdnn={results.sdnn}
                rmssd={results.rmssd}
                pnn50={results.pnn50}
              />

              <FrequencySummary
                lf={results.lf}
                hf={results.hf}
                lfHf={results.lfHf}
                lfnu={results.lfnu}
                hfnu={results.hfnu}
                totalPower={results.totalPower}
                respHz={results.respHz}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
