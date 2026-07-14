import React from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "../ui/card";
import { Sliders } from "lucide-react";

interface FrequencySummaryProps {
  lf: number;
  hf: number;
  lfHf: number;
  lfnu: number;
  hfnu: number;
  totalPower: number;
  respHz: number;
}

export const FrequencySummary: React.FC<FrequencySummaryProps> = ({
  lf,
  hf,
  lfHf,
  lfnu,
  hfnu,
  totalPower,
  respHz,
}) => {
  const { t } = useTranslation();
  return (
    <div className="max-w-xl mx-auto w-full">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-1.5">
            <Sliders className="size-4 text-primary" /> {t("frequencyDomainTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border border-t border-border">
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("lfPower")}</span>
              <span className="text-right font-mono font-semibold">{lf.toFixed(0)} ms²</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("hfPower")}</span>
              <span className="text-right font-mono font-semibold">{hf.toFixed(0)} ms²</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("lfHfRatio")}</span>
              <span className="text-right font-mono font-semibold">{lfHf}</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("lfnu")}</span>
              <span className="text-right font-mono font-semibold">{lfnu} %</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("hfnu")}</span>
              <span className="text-right font-mono font-semibold">{hfnu} %</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("totalPower")}</span>
              <span className="text-right font-mono font-semibold">{totalPower} ms²</span>
            </div>
            <div className="grid grid-cols-2 p-3 text-sm hover:bg-muted/30 transition-colors">
              <span className="font-medium text-muted-foreground">{t("resp")}</span>
              <span className="text-right font-mono font-semibold">{respHz > 0 ? `${respHz.toFixed(3)} Hz` : "-"}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
