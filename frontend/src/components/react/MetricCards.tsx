import React from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../ui/card";
import { Heart, Activity, Sliders, Percent } from "lucide-react";

interface MetricCardsProps {
  avgHeartRate: number;
  sdnn: number;
  rmssd: number;
  pnn50: number;
}

export const MetricCards: React.FC<MetricCardsProps> = ({
  avgHeartRate,
  sdnn,
  rmssd,
  pnn50,
}) => {
  return (
    <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
      <Card className="bg-card">
        <CardHeader className="p-4 pb-2">
          <CardDescription className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Heart className="size-3 text-red-500 fill-red-500" /> Heart Rate
          </CardDescription>
          <CardTitle className="text-2xl font-bold">
            {avgHeartRate} <span className="text-sm font-medium text-muted-foreground">bpm</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-xs text-muted-foreground">Mean beat frequency</p>
        </CardContent>
      </Card>

      <Card className="bg-card">
        <CardHeader className="p-4 pb-2">
          <CardDescription className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Activity className="size-3 text-sky-500" /> HRV (SDNN)
          </CardDescription>
          <CardTitle className="text-2xl font-bold">
            {sdnn} <span className="text-sm font-medium text-muted-foreground">ms</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-xs text-muted-foreground">Overall beat variability</p>
        </CardContent>
      </Card>

      <Card className="bg-card">
        <CardHeader className="p-4 pb-2">
          <CardDescription className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Sliders className="size-3 text-emerald-500" /> HRV (RMSSD)
          </CardDescription>
          <CardTitle className="text-2xl font-bold">
            {rmssd} <span className="text-sm font-medium text-muted-foreground">ms</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-xs text-muted-foreground">Short-term beat variation</p>
        </CardContent>
      </Card>

      <Card className="bg-card">
        <CardHeader className="p-4 pb-2">
          <CardDescription className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Percent className="size-3 text-pink-500" /> HRV (pNN50)
          </CardDescription>
          <CardTitle className="text-2xl font-bold">
            {pnn50.toFixed(1)} <span className="text-sm font-medium text-muted-foreground">%</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-xs text-muted-foreground">Percentage of NN50 intervals</p>
        </CardContent>
      </Card>
    </div>
  );
};
