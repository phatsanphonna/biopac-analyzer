import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  Upload,
  FileSpreadsheet,
  Trash2,
  Play,
  RotateCcw,
  Loader2,
  AlertCircle,
  FileText,
  Activity,
  Heart,
  Wind,
  LineChart,
} from "lucide-react";

interface MappingConfig {
  time_col: string;
  ecg_col: string;
  resp_col: string;
  fs: number;
}

export default function BiopacAnalyzer() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [config, setConfig] = useState<MappingConfig>({
    time_col: "",
    ecg_col: "",
    resp_col: "none",
    fs: 250,
  });
  
  const [status, setStatus] = useState<"idle" | "parsing" | "ready" | "analyzing" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [results, setResults] = useState<any | null>(null);
  const [activeChartTab, setActiveChartTab] = useState<string>("ecg_preview");

  // Handle file selection
  const handleFileSelect = async (selectedFiles: FileList | null) => {
    if (!selectedFiles || selectedFiles.length === 0) return;
    
    const selectedFile = selectedFiles[0];
    if (!selectedFile.name.endsWith(".csv")) {
      setErrorMsg("Please upload a valid CSV file (.csv)");
      setStatus("error");
      return;
    }
    
    setFile(selectedFile);
    setStatus("parsing");
    setErrorMsg(null);
    setResults(null);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch("/api/columns", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Failed to read CSV columns");
      }

      const data = await res.json();
      if (!data.columns || data.columns.length === 0) {
        throw new Error("No columns found in the CSV file");
      }

      setColumns(data.columns);
      
      // Auto-map columns
      const cols: string[] = data.columns;
      const timeGuess = cols.find((c) => c.toLowerCase().includes("sec") || c.toLowerCase().includes("time")) || cols[0] || "";
      const ecgGuess = cols.find((c) => c.toLowerCase().includes("ch1") || c.toLowerCase().includes("ecg")) || cols[1] || cols[0] || "";
      const respGuess = cols.find((c) => c.toLowerCase().includes("ch2") || c.toLowerCase().includes("resp")) || "none";

      setConfig({
        time_col: timeGuess,
        ecg_col: ecgGuess,
        resp_col: respGuess,
        fs: 250,
      });
      
      setStatus("ready");
    } catch (err: any) {
      setErrorMsg(err.message || "An error occurred while parsing the file headers.");
      setStatus("error");
    }
  };

  // Trigger analysis
  const runAnalysis = async () => {
    if (!file) return;
    
    setStatus("analyzing");
    setErrorMsg(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("time_col", config.time_col);
    formData.append("ecg_col", config.ecg_col);
    if (config.resp_col !== "none") {
      formData.append("resp_col", config.resp_col);
    }
    formData.append("fs", config.fs.toString());

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Analysis failed");
      }

      const data = await res.json();
      setResults(data);
      setStatus("success");
      
      // Set active chart tab based on availability
      if (data.charts) {
        const availableTabs = Object.keys(data.charts).filter(k => data.charts[k]);
        if (availableTabs.length > 0) {
          setActiveChartTab(availableTabs[0]);
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "An error occurred during analysis.");
      setStatus("error");
    }
  };

  // Reset uploader state
  const resetAll = () => {
    setFile(null);
    setColumns([]);
    setConfig({
      time_col: "",
      ecg_col: "",
      resp_col: "none",
      fs: 250,
    });
    setResults(null);
    setErrorMsg(null);
    setStatus("idle");
  };

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col gap-6">
      {/* 1. UPLOADER OR CONFIG FORM */}
      {status !== "success" && (
        <Card>
          <CardHeader>
            <CardTitle>
              {status === "ready" ? "Configure Mappings" : "Upload Data"}
            </CardTitle>
            <CardDescription>
              {status === "ready"
                ? "Configure the signal column mappings and sampling rate parameters below."
                : "Import a physiological CSV file from BIOPAC to generate calculations and plots."}
            </CardDescription>
          </CardHeader>
          
          <CardContent className="flex flex-col gap-5">
            {/* Error alerts */}
            {status === "error" && errorMsg && (
              <div className="flex gap-2 items-start py-3 text-sm">
                <AlertCircle className="size-4 shrink-0 text-foreground mt-0.5" />
                <div className="flex-1 text-muted-foreground">
                  <span className="font-semibold text-foreground">Analysis Error: </span>
                  {errorMsg}
                </div>
              </div>
            )}

            {/* Standard Uploader Zone */}
            {(status === "idle" || status === "parsing" || status === "error") && (
              <div
                className={cn(
                  "border border-dashed border-muted-foreground rounded-lg p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors hover:bg-muted/10",
                  status === "parsing" && "pointer-events-none opacity-60"
                )}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (status !== "parsing") {
                    handleFileSelect(e.dataTransfer.files);
                  }
                }}
              >
                {status === "parsing" ? (
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="size-8 animate-spin text-muted-foreground" />
                    <p className="text-sm font-medium text-foreground">Reading CSV headers...</p>
                  </div>
                ) : (
                  <>
                    <div className="mb-3 bg-muted rounded-full p-3">
                      <Upload className="size-5 text-muted-foreground" />
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      Drag and drop BIOPAC CSV file here
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      or <span className="text-foreground underline underline-offset-2 font-medium">click to browse</span>
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-3">
                      Accepts file containing columns like ECG, time, and optional respiration.
                    </p>
                  </>
                )}
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept=".csv"
                  onChange={(e) => handleFileSelect(e.target.files)}
                />
              </div>
            )}

            {/* File Info & Configuration Form */}
            {(status === "ready" || status === "analyzing") && file && (
              <div className="flex flex-col gap-6">
                {/* File summary bar */}
                <div className="flex justify-between items-center px-4 py-3 bg-muted/20 text-sm rounded-md border border-border">
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="size-4 text-muted-foreground" />
                    <span className="font-medium truncate max-w-[300px]">{file.name}</span>
                    <span className="text-muted-foreground text-xs">
                      ({Math.round(file.size / 1024)} KB)
                    </span>
                  </div>
                  {status === "ready" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 text-muted-foreground hover:text-foreground hover:bg-muted/50"
                      onClick={resetAll}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </div>

                {/* Configuration Fields */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="time_col" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Time Column</Label>
                    <Select
                      value={config.time_col}
                      onValueChange={(val) => setConfig((prev) => ({ ...prev, time_col: val }))}
                      disabled={status === "analyzing"}
                    >
                      <SelectTrigger id="time_col" className="w-full">
                        <SelectValue placeholder="Select Time column" />
                      </SelectTrigger>
                      <SelectContent>
                        {columns.map((col) => (
                          <SelectItem key={col} value={col}>
                            {col}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label htmlFor="ecg_col" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">ECG Column (CH1)</Label>
                    <Select
                      value={config.ecg_col}
                      onValueChange={(val) => setConfig((prev) => ({ ...prev, ecg_col: val }))}
                      disabled={status === "analyzing"}
                    >
                      <SelectTrigger id="ecg_col" className="w-full">
                        <SelectValue placeholder="Select ECG column" />
                      </SelectTrigger>
                      <SelectContent>
                        {columns.map((col) => (
                          <SelectItem key={col} value={col}>
                            {col}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label htmlFor="resp_col" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Respiration Column (Optional)</Label>
                    <Select
                      value={config.resp_col}
                      onValueChange={(val) => setConfig((prev) => ({ ...prev, resp_col: val }))}
                      disabled={status === "analyzing"}
                    >
                      <SelectTrigger id="resp_col" className="w-full">
                        <SelectValue placeholder="Select Respiration column" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">None (Generate ECG-Derived Respiration)</SelectItem>
                        {columns.map((col) => (
                          <SelectItem key={col} value={col}>
                            {col}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label htmlFor="fs" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Sampling Rate (Hz)</Label>
                    <Input
                      id="fs"
                      type="number"
                      value={config.fs}
                      onChange={(e) => setConfig((prev) => ({ ...prev, fs: parseInt(e.target.value) || 250 }))}
                      disabled={status === "analyzing"}
                      min={10}
                      max={10000}
                    />
                  </div>
                </div>
              </div>
            )}
          </CardContent>

          {(status === "ready" || status === "analyzing") && (
            <CardFooter className="flex justify-between items-center border-t border-border/50 bg-muted/10 px-6 py-4 rounded-b-lg">
              <Button
                variant="outline"
                onClick={resetAll}
                disabled={status === "analyzing"}
                className="text-sm"
              >
                Reset
              </Button>
              <Button
                onClick={runAnalysis}
                disabled={status === "analyzing" || !config.time_col || !config.ecg_col}
                className="text-sm font-medium"
              >
                {status === "analyzing" ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Analyzing signals...
                  </>
                ) : (
                  <>
                    <Play className="size-3.5" />
                    Run Analysis
                  </>
                )}
              </Button>
            </CardFooter>
          )}
        </Card>
      )}

      {/* 2. RESULTS DISPLAY */}
      {status === "success" && results && (
        <div className="flex flex-col gap-6">
          {/* Header Card */}
          <Card>
            <CardContent className="flex flex-col sm:flex-row justify-between sm:items-center py-5 gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <FileText className="size-5 text-muted-foreground" />
                  <h2 className="text-lg font-semibold tracking-tight">Physiological Analysis Report</h2>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Processed file: <span className="font-semibold text-foreground">{file?.name}</span> &bull; 
                  Duration: <span className="font-semibold text-foreground">{results.duration_sec.toFixed(1)}s</span> &bull; 
                  Total Heartbeats: <span className="font-semibold text-foreground">{results.total_beats}</span>
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={resetAll} className="w-fit">
                <RotateCcw className="size-3.5" />
                Upload Another
              </Button>
            </CardContent>
          </Card>

          {/* Grid: ANS Balance & Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* ANS Balance Section */}
            <Card className="flex flex-col justify-between">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">ANS Balance (Kubios Emulation)</CardTitle>
                <CardDescription className="text-xs">Autonomic Nervous System balance index</CardDescription>
              </CardHeader>
              <CardContent className="py-6 flex flex-col gap-6">
                {/* Visual balance line */}
                <div className="relative w-full h-1.5 bg-muted rounded-full">
                  {/* Zero line */}
                  <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-foreground/20 z-10"></div>
                  
                  {/* PNS indicator */}
                  <div 
                    className="absolute h-3.5 w-3.5 rounded-full border-2 border-background bg-foreground -top-1"
                    style={{
                      left: `calc(50% + ${Math.max(-5, Math.min(5, results.ans_indices.pns_index)) * 9}%)`,
                      transform: 'translateX(-50%)'
                    }}
                  />
                </div>
                
                <div className="grid grid-cols-2 text-center divide-x divide-border">
                  <div>
                    <div className="text-2xl font-bold tracking-tight">
                      {results.ans_indices.pns_index > 0 ? "+" : ""}
                      {results.ans_indices.pns_index.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium mt-1">
                      PNS Index
                    </div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold tracking-tight">
                      {results.ans_indices.sns_index > 0 ? "+" : ""}
                      {results.ans_indices.sns_index.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium mt-1">
                      SNS Index
                    </div>
                  </div>
                </div>
              </CardContent>
              <CardFooter className="border-t border-border/40 py-2.5 px-4 bg-muted/10 text-[10px] text-muted-foreground rounded-b-lg">
                Zero represents normal population average. Max/Min limit &plusmn;5.0.
              </CardFooter>
            </Card>

            {/* Heart Rate Summary */}
            <Card className="flex flex-col justify-between">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                  <Heart className="size-4 text-muted-foreground/80" />
                  Heart Rate (ECG)
                </CardTitle>
                <CardDescription className="text-xs">Summary of cardiovascular metrics</CardDescription>
              </CardHeader>
              <CardContent className="pt-2 flex flex-col gap-4">
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-bold tracking-tight">{results.time_domain.mean_hr_bpm}</span>
                  <span className="text-xs text-muted-foreground">bpm average</span>
                </div>
                <div className="grid grid-cols-2 border-t border-border pt-4 gap-2 text-xs text-muted-foreground">
                  <div>
                    Min HR: <span className="font-semibold text-foreground">{results.time_domain.min_hr_bpm} bpm</span>
                  </div>
                  <div>
                    Max HR: <span className="font-semibold text-foreground">{results.time_domain.max_hr_bpm} bpm</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Respiration Summary */}
            <Card className="flex flex-col justify-between">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                  <Wind className="size-4 text-muted-foreground/80" />
                  Respiration
                </CardTitle>
                <CardDescription className="text-xs">
                  {results.respiration.has_respiration_signal ? "Measured breathing rate" : "ECG-Derived Respiration (EDR)"}
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-2 flex flex-col gap-4">
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-bold tracking-tight">
                    {results.respiration.has_respiration_signal 
                      ? results.respiration.measured_resp_bpm 
                      : results.respiration.consensus_edr_bpm || "N/A"}
                  </span>
                  <span className="text-xs text-muted-foreground">breaths/min</span>
                </div>
                <div className="grid grid-cols-2 border-t border-border pt-4 gap-2 text-xs text-muted-foreground">
                  <div>
                    RSA Amp: <span className="font-semibold text-foreground">{results.rsa.avg_rsa_ms ? `${results.rsa.avg_rsa_ms.toFixed(1)} ms` : "N/A"}</span>
                  </div>
                  <div>
                    RSA Coord: <span className="font-semibold text-foreground">{results.rsa.avg_rsa_bpm ? `${results.rsa.avg_rsa_bpm.toFixed(1)} bpm` : "N/A"}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Detailed HRV Parameters & Charts Section */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-6 pt-4">
            {/* HRV Parameters (Left 2 columns) */}
            <div className="md:col-span-2 flex flex-col gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Heart Rate Variability (HRV)</CardTitle>
                  <CardDescription className="text-xs">Time and frequency domain indicators</CardDescription>
                </CardHeader>
                <CardContent className="p-0 text-sm">
                  <div className="flex flex-col">
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">SDNN</span>
                      <span className="font-medium text-right">{results.time_domain.sdnn_ms} ms</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">RMSSD</span>
                      <span className="font-medium text-right">{results.time_domain.rmssd_ms} ms</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">pNN50</span>
                      <span className="font-medium text-right">{results.time_domain.pnn50_percent !== null ? `${results.time_domain.pnn50_percent}%` : "N/A"}</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">LF Power</span>
                      <span className="font-medium text-right">{results.frequency_domain.lf_power_ms2 || "N/A"} ms&sup2;</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">HF Power</span>
                      <span className="font-medium text-right">{results.frequency_domain.hf_power_ms2 || "N/A"} ms&sup2;</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">LF/HF Ratio</span>
                      <span className="font-medium text-right">{results.frequency_domain.lf_hf_ratio || "N/A"}</span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2 border-b border-border/40">
                      <span className="text-muted-foreground">SD1 / SD2</span>
                      <span className="font-medium text-right">
                        {results.nonlinear.sd1_ms} / {results.nonlinear.sd2_ms} ms
                      </span>
                    </div>
                    <div className="flex justify-between items-center px-4 py-2">
                      <span className="text-muted-foreground">Sample Entropy</span>
                      <span className="font-medium text-right">{results.nonlinear.sample_entropy || "N/A"}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Charts View (Right 3 columns) */}
            <div className="md:col-span-3">
              <Card className="h-full flex flex-col justify-between">
                <CardHeader className="pb-3 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                        <LineChart className="size-4 text-muted-foreground/80" />
                        Visualization Charts
                      </CardTitle>
                      <CardDescription className="text-xs mt-0.5">Calculated charts from signals</CardDescription>
                    </div>
                    
                    {/* Minimal select trigger */}
                    <Select value={activeChartTab} onValueChange={setActiveChartTab}>
                      <SelectTrigger className="w-[180px] h-8 text-xs border border-input rounded-md bg-transparent">
                        <SelectValue placeholder="Choose chart" />
                      </SelectTrigger>
                      <SelectContent>
                        {results.charts.ecg_preview && <SelectItem value="ecg_preview">ECG Preview</SelectItem>}
                        {results.charts.poincare && <SelectItem value="poincare">Poincaré Plot</SelectItem>}
                        {results.charts.fft_spectrum && <SelectItem value="fft_spectrum">HRV Power Spectrum</SelectItem>}
                        {results.charts.rsa_overlay && <SelectItem value="rsa_overlay">RSA Coordination</SelectItem>}
                        {results.charts.rr_tachogram && <SelectItem value="rr_tachogram">RR Tachogram</SelectItem>}
                      </SelectContent>
                    </Select>
                  </div>
                </CardHeader>
                
                <CardContent className="p-4 flex-grow flex items-center justify-center min-h-[300px] bg-muted/10">
                  {results.charts[activeChartTab] ? (
                    <div className="w-full flex flex-col items-center">
                      <img
                        src={results.charts[activeChartTab]}
                        alt={activeChartTab}
                        className="max-h-[340px] w-auto object-contain bg-white border border-border rounded shadow-2xs"
                      />
                    </div>
                  ) : (
                    <div className="text-muted-foreground text-xs flex flex-col items-center gap-2">
                      <Activity className="size-6 text-muted-foreground/60" />
                      Chart data not generated for this signal mapping.
                    </div>
                  )}
                </CardContent>

                <CardFooter className="border-t border-border/40 py-2.5 bg-muted/10 text-[10px] text-muted-foreground justify-center text-center rounded-b-lg">
                  Charts are processed with standard Python matplotlib and neurokit2 packages.
                </CardFooter>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
