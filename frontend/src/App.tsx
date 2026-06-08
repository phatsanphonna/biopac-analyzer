import BiopacAnalyzer from "@/components/BiopacAnalyzer";

function App() {
  return (
    <div className="min-h-svh bg-background text-foreground flex flex-col font-sans">
      <header className="px-6 py-6 max-w-4xl w-full mx-auto flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">BIOPAC Signal Analyzer</h1>
      </header>

      <main className="flex-1 max-w-4xl w-full mx-auto p-6 md:py-10">
        <BiopacAnalyzer />
      </main>
    </div>
  );
}

export default App;
