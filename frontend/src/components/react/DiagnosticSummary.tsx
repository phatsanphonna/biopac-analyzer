import React from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "../ui/card";
import { FileText } from "lucide-react";

interface DiagnosticSummaryProps {
  meanRR: number;
  avgHeartRate: number;
  minHR: number;
  sdnn: number;
  rmssd: number;
  pnn50: number;
}

export const DiagnosticSummary: React.FC<DiagnosticSummaryProps> = ({
  meanRR,
  avgHeartRate,
  minHR,
  sdnn,
  rmssd,
  pnn50,
}) => {
  return (
    <div className="max-w-xl mx-auto w-full">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-1.5">
            <FileText className="size-4 text-primary" /> Time-Domain HRV Results
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border border-t border-border">
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">Mean RR</span>
              <span className="text-right font-mono font-semibold">{meanRR} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">Mean HR</span>
              <span className="text-right font-mono font-semibold">{avgHeartRate} bpm</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">Min HR</span>
              <span className="text-right font-mono font-semibold">{minHR} bpm</span>
            </div>

            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">SDNN</span>
              <span className="text-right font-mono font-semibold">{sdnn} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">RMSSD</span>
              <span className="text-right font-mono font-semibold">{rmssd} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">pNN50</span>
              <span className="text-right font-mono font-semibold">{pnn50.toFixed(1)} %</span>
            </div>
          </div>
        </CardContent>

      </Card>
    </div>
  );
};
