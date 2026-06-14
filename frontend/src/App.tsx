import { useState } from "react";
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
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  // File processing handler
  const handleFileSelect = (file: File) => {
    setFileName(file.name);
    setIsAnalyzing(true);
    setError(null);

    // Try posting the file to the python backend first
    const formData = new FormData();
    formData.append("file", file);

    fetch("/api/analyze", {
      method: "POST",
      body: formData,
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error("Backend response error");
        }
        return res.json();
      })
      .then((data) => {
        setResults(data);
        setIsAnalyzing(false);
      })
      .catch((err) => {
        console.warn(
          "Python backend connection failed. Falling back to local JS processing.",
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
                    "Failed to process the CSV file locally. Ensure columns 'sec' and 'CH1' exist.",
                );
                setIsAnalyzing(false);
              }
            }, 100);
          } catch (readErr) {
            setError("Failed to read the file locally.");
            setIsAnalyzing(false);
          }
        };
        reader.onerror = () => {
          setError("File reading encountered an error.");
          setIsAnalyzing(false);
        };
        reader.readAsText(file);
      });
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
        setError("Failed to generate demo data.");
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
