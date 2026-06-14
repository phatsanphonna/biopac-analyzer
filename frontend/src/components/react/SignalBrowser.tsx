import React, { useState } from "react";
import { SignalChart } from "./SignalChart";
import { Input } from "../ui/input";

interface ChartPoint {
  time: number;
  value: number;
  isPeak?: boolean;
}

interface SignalBrowserProps {
  duration: number;
  ecgPoints: ChartPoint[];
  hrPoints: ChartPoint[];
}

export const SignalBrowser: React.FC<SignalBrowserProps> = ({
  duration,
  ecgPoints,
  hrPoints,
}) => {
  const [activeTab, setActiveTab] = useState<"ecg" | "hr">("ecg");
  const [timeOffset, setTimeOffset] = useState(0);
  const [windowSize, setWindowSize] = useState(10); // seconds default

  const handleOffsetChange = (val: number) => {
    if (!isNaN(val)) {
      setTimeOffset(Math.max(0, Math.min(duration - windowSize, val)));
    }
  };

  return (
    <div className="space-y-4 no-print">
      <div className="flex border-b border-border/50">
        <button
          onClick={() => setActiveTab("ecg")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
            activeTab === "ecg" 
              ? "border-primary text-primary" 
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          ECG Waveform (CH1)
        </button>
        <button
          onClick={() => setActiveTab("hr")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
            activeTab === "hr" 
              ? "border-primary text-primary" 
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Heart Rate (BPM)
        </button>
      </div>

      {/* Renders Selected Chart */}
      {activeTab === "ecg" && (
        <SignalChart
          data={ecgPoints}
          title="Raw ECG Stream with detected R-Peaks"
          color="var(--color-primary)"
          peakColor="#ef4444"
          yLabel="ECG Amplitude (mV)"
          windowSizeSeconds={windowSize}
          currentTimeOffset={timeOffset}
        />
      )}

      {activeTab === "hr" && (
        <SignalChart
          data={hrPoints}
          title="Instantaneous Heart Rate (Time-series)"
          color="#ec4899"
          yLabel="Heart Rate (BPM)"
          windowSizeSeconds={windowSize}
          currentTimeOffset={timeOffset}
        />
      )}

      {/* Navigation controls */}
      <div className="flex flex-col gap-3 p-4 bg-muted/20 border border-border/50 rounded-xl">
        <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
          <span>Scroll Signal Timeline</span>
          <span>Drag slider or type a starting second</span>
        </div>
        
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={0}
            max={Math.max(0, duration - windowSize)}
            step={0.1}
            value={timeOffset}
            onChange={(e) => setTimeOffset(parseFloat(e.target.value))}
            className="flex-1 h-1.5 bg-muted border border-border rounded-lg appearance-none cursor-pointer accent-primary"
          />
          <div className="flex items-center gap-1 shrink-0">
            <Input
              type="number"
              value={timeOffset.toFixed(1)}
              onChange={(e) => handleOffsetChange(parseFloat(e.target.value))}
              className="w-16 h-8 text-xs font-mono text-center px-1"
            />
            <span className="text-xs text-muted-foreground">sec</span>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border/40 pt-2 text-xs">
          <span className="text-muted-foreground">Window Size:</span>
          <div className="flex gap-2">
            {[5, 10, 15, 30].map(s => (
              <button
                key={s}
                onClick={() => {
                  setWindowSize(s);
                  setTimeOffset(prev => Math.min(duration - s, prev));
                }}
                className={`px-2 py-0.5 rounded border transition-colors ${
                  windowSize === s 
                    ? "bg-primary border-primary text-primary-foreground font-semibold" 
                    : "border-border hover:bg-muted text-muted-foreground"
                }`}
              >
                {s}s
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
