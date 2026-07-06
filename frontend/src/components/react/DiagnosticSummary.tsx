import React from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  return (
    <div className="max-w-xl mx-auto w-full">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-1.5">
            <FileText className="size-4 text-primary" /> {t("timeDomainTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border border-t border-border">
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("meanRR")}</span>
              <span className="text-right font-mono font-semibold">{meanRR} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("meanHR")}</span>
              <span className="text-right font-mono font-semibold">{avgHeartRate} bpm</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("minHR")}</span>
              <span className="text-right font-mono font-semibold">{minHR} bpm</span>
            </div>

            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("sdnn")}</span>
              <span className="text-right font-mono font-semibold">{sdnn} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("rmssd")}</span>
              <span className="text-right font-mono font-semibold">{rmssd} ms</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("pnn50")}</span>
              <span className="text-right font-mono font-semibold">{pnn50.toFixed(1)} %</span>
            </div>
          </div>
        </CardContent>

      </Card>
    </div>
  );
};
