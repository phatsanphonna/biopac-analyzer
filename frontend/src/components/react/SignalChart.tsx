import React, { useMemo } from "react";

interface Point {
  time: number;
  value: number;
  isPeak?: boolean;
}

interface SignalChartProps {
  data: Point[];
  title: string;
  color: string;
  peakColor?: string;
  yLabel?: string;
  xLabel?: string;
  windowSizeSeconds?: number;
  currentTimeOffset?: number; // starts at what second
}

export const SignalChart: React.FC<SignalChartProps> = ({
  data,
  title,
  color,
  peakColor = "red",
  yLabel = "Amplitude",
  xLabel = "Time (s)",
  windowSizeSeconds = 10,
  currentTimeOffset = 0,
}) => {
  // Filter data points that fall within the current sliding window
  const visibleData = useMemo(() => {
    const endOffset = currentTimeOffset + windowSizeSeconds;
    return data.filter(d => d.time >= currentTimeOffset && d.time <= endOffset);
  }, [data, currentTimeOffset, windowSizeSeconds]);

  // Find min/max values in visible data for scaling
  const { minVal, maxVal } = useMemo(() => {
    if (visibleData.length === 0) return { minVal: -1, maxVal: 1 };
    let min = Infinity;
    let max = -Infinity;
    for (const p of visibleData) {
      if (p.value < min) min = p.value;
      if (p.value > max) max = p.value;
    }
    // Add small buffer to avoid touching the very top/bottom
    const range = max - min || 1;
    return {
      minVal: min - range * 0.1,
      maxVal: max + range * 0.1,
    };
  }, [visibleData]);

  // Width and height of SVG viewport
  const width = 800;
  const height = 250;
  const paddingLeft = 60;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 40;

  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  // Scale functions
  const getX = (t: number) => {
    const tMin = currentTimeOffset;
    const tMax = currentTimeOffset + windowSizeSeconds;
    return paddingLeft + ((t - tMin) / (tMax - tMin)) * chartWidth;
  };

  const getY = (val: number) => {
    return (
      paddingTop +
      chartHeight -
      ((val - minVal) / (maxVal - minVal)) * chartHeight
    );
  };

  // Generate SVG Path data string
  const pathD = useMemo(() => {
    if (visibleData.length === 0) return "";
    let d = "";
    for (let i = 0; i < visibleData.length; i++) {
      const x = getX(visibleData[i].time);
      const y = getY(visibleData[i].value);
      if (i === 0) {
        d += `M ${x} ${y}`;
      } else {
        d += ` L ${x} ${y}`;
      }
    }
    return d;
  }, [visibleData, minVal, maxVal, currentTimeOffset, windowSizeSeconds]);

  // Grid lines (horizontal)
  const gridLines = useMemo(() => {
    const lines = [];
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const val = minVal + (i / steps) * (maxVal - minVal);
      const y = getY(val);
      lines.push({ y, val: val.toFixed(2) });
    }
    return lines;
  }, [minVal, maxVal]);

  // Grid lines (vertical - every 1 second or 2 seconds)
  const timeLines = useMemo(() => {
    const lines = [];
    const step = windowSizeSeconds <= 5 ? 1 : 2; // grid steps in seconds
    const start = Math.ceil(currentTimeOffset);
    const end = Math.floor(currentTimeOffset + windowSizeSeconds);

    for (let t = start; t <= end; t++) {
      if ((t - start) % step === 0) {
        const x = getX(t);
        lines.push({ x, time: t });
      }
    }
    return lines;
  }, [currentTimeOffset, windowSizeSeconds]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
        <span className="text-xs font-mono text-muted-foreground">
          Window: {currentTimeOffset.toFixed(1)}s – {(currentTimeOffset + windowSizeSeconds).toFixed(1)}s
        </span>
      </div>

      <div className="relative bg-card border border-border rounded-xl p-2 shadow-xs overflow-hidden">
        {visibleData.length === 0 ? (
          <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
            No signal data in this range
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto select-none"
            style={{ display: "block" }}
          >
            {/* Horizontal Grid Lines & Y-axis labels */}
            {gridLines.map((line, idx) => (
              <g key={`h-grid-${idx}`}>
                <line
                  x1={paddingLeft}
                  y1={line.y}
                  x2={width - paddingRight}
                  y2={line.y}
                  stroke="currentColor"
                  className="text-border/50"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x={paddingLeft - 10}
                  y={line.y + 4}
                  textAnchor="end"
                  className="fill-muted-foreground text-[10px] font-mono"
                >
                  {line.val}
                </text>
              </g>
            ))}

            {/* Vertical Time Lines & X-axis labels */}
            {timeLines.map((line, idx) => (
              <g key={`v-grid-${idx}`}>
                <line
                  x1={line.x}
                  y1={paddingTop}
                  x2={line.x}
                  y2={height - paddingBottom}
                  stroke="currentColor"
                  className="text-border/30"
                  strokeWidth="1"
                />
                <text
                  x={line.x}
                  y={height - paddingBottom + 16}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[10px] font-mono"
                >
                  {line.time}s
                </text>
              </g>
            ))}

            {/* Main Signal Path */}
            <path
              d={pathD}
              fill="none"
              stroke={color}
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Highlighted Peaks (if any) */}
            {visibleData
              .filter(p => p.isPeak)
              .map((p, idx) => {
                const cx = getX(p.time);
                const cy = getY(p.value);
                return (
                  <g key={`peak-${idx}`} className="group/peak">
                    <circle
                      cx={cx}
                      cy={cy}
                      r="6"
                      fill={peakColor}
                      className="opacity-30 animate-pulse"
                    />
                    <circle
                      cx={cx}
                      cy={cy}
                      r="3.5"
                      fill={peakColor}
                      stroke="white"
                      strokeWidth="1"
                    />
                  </g>
                );
              })}

            {/* X and Y Axis Titles */}
            <text
              x={paddingLeft + chartWidth / 2}
              y={height - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-xs font-medium"
            >
              {xLabel}
            </text>
            
            <text
              transform={`rotate(-90 ${15} ${paddingTop + chartHeight / 2})`}
              x={15}
              y={paddingTop + chartHeight / 2}
              textAnchor="middle"
              className="fill-muted-foreground text-xs font-medium"
            >
              {yLabel}
            </text>
          </svg>
        )}
      </div>
    </div>
  );
};
