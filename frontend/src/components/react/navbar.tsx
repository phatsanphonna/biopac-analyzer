import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";

const Navbar = () => {
  const { t, i18n } = useTranslation();

  return (
    <header className="border-b border-border bg-card/50 backdrop-blur sticky top-0 z-50 no-print">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between">
        <div className="font-semibold text-lg tracking-tight text-foreground">
          {t("title")}
        </div>
        <div className="flex items-center gap-2">
          <Globe className="size-4 text-muted-foreground" />
          <div className="inline-flex rounded-lg border border-border bg-muted p-0.5">
            <button
              onClick={() => i18n.changeLanguage("en")}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all cursor-pointer ${
                i18n.language === "en"
                  ? "bg-background text-foreground shadow-sm font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              EN
            </button>
            <button
              onClick={() => i18n.changeLanguage("zh-TW")}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all cursor-pointer ${
                i18n.language === "zh-TW"
                  ? "bg-background text-foreground shadow-sm font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              繁中
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Navbar;

