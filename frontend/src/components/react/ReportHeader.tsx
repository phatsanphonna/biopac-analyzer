import React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/button";
import { Printer } from "lucide-react";

interface ReportHeaderProps {
  fileName: string;
  duration: number;
  sampleRate: number;
  onPrint: () => void;
  onReset: () => void;
}

export const ReportHeader: React.FC<ReportHeaderProps> = ({
  fileName,
  duration,
  sampleRate,
  onPrint,
  onReset,
}) => {
  const { t } = useTranslation();
  return (
    <>
      {/* Interactive Header (no-print) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/50 pb-4 no-print">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{t("analysisReport")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("fileLabel")}: <span className="font-mono text-foreground">{fileName}</span> ({duration.toFixed(1)}s, {sampleRate} Hz)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onPrint} className="gap-1">
            <Printer className="size-4" />
            {t("printReport")}
          </Button>
          <Button variant="secondary" size="sm" onClick={onReset}>
            {t("uploadAnother")}
          </Button>
        </div>
      </div>

      {/* Print Header (Only visible when printing) */}
      <div className="hidden print:block border-b-2 border-foreground pb-4 space-y-1">
        <h1 className="text-3xl font-bold tracking-tight text-foreground uppercase">{t("printHeaderTitle")}</h1>
        <div className="grid grid-cols-2 text-sm text-muted-foreground">
          <p>{t("sourceRecord")}: <strong className="text-foreground">{fileName}</strong></p>
          <p>{t("recordDuration")}: <strong className="text-foreground">{duration.toFixed(1)} {t("secondsUnit")}</strong></p>
          <p>{t("samplingRate")}: <strong className="text-foreground">{sampleRate} Hz</strong></p>
          <p>{t("analysisDate")}: <strong className="text-foreground">{new Date().toLocaleDateString()}</strong></p>
        </div>
      </div>
    </>
  );
};
