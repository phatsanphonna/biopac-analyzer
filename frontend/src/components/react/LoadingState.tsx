import React from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

export const LoadingState: React.FC = () => {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center py-20 space-y-4">
      <RefreshCw className="size-12 animate-spin text-primary" />
      <h2 className="text-xl font-semibold text-foreground">{t("analyzing")}</h2>
    </div>
  );
};
