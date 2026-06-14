import React, { useState, useRef } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { UploadCloud, Info } from "lucide-react";

interface FileUploaderProps {
  onFileSelect: (file: File) => void;
  onLoadDemo: () => void;
  error: string | null;
}

export const FileUploader: React.FC<FileUploaderProps> = ({
  onFileSelect,
  onLoadDemo,
  error,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  return (
    <div className="grid gap-8 md:grid-cols-2 items-center py-8">
      <div className="space-y-6">
        <h1 className="text-4xl font-extrabold tracking-tight lg:text-5xl text-foreground">
          BIOPAC Signal Analyzer
        </h1>
        <p className="text-muted-foreground text-lg leading-relaxed">
          Import raw CSV signals recorded from BIOPAC units. The analyzer automatically cleans ECG/respiration tracks, identifies R-peaks, and generates an autonomic nervous system report.
        </p>
        
        <div className="space-y-3">
          <h3 className="font-semibold text-sm text-foreground">Format requirements:</h3>
          <ul className="text-sm text-muted-foreground space-y-1.5 list-disc pl-5">
            <li>CSV format with column names in the first row.</li>
            <li>Needs a <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs text-foreground">sec</code> or <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs text-foreground">time</code> column.</li>
            <li>ECG recording mapped to <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs text-foreground">CH1</code>.</li>
            <li>(Optional) Respiration wave mapped to <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs text-foreground">CH2</code>.</li>
          </ul>
        </div>
      </div>

      <div className="space-y-4">
        <Card 
          className={`w-full transition-all border-2 border-dashed ${
            dragActive 
              ? "border-primary bg-primary/5 shadow-md" 
              : "border-muted-foreground/25 hover:border-primary/50"
          }`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
        >
          <CardHeader>
            <CardTitle>Import CSV Record</CardTitle>
            <CardDescription>Select or drag a BIOPAC CSV file into this window</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div 
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg p-10 flex flex-col items-center justify-center gap-3 text-center cursor-pointer"
            >
              <UploadCloud className="size-12 text-muted-foreground/85 stroke-1" />
              <div className="space-y-1">
                <p className="text-sm font-medium">Click to select files</p>
                <p className="text-xs text-muted-foreground">CSV file format up to 20MB</p>
              </div>
              <Input 
                ref={fileInputRef}
                id="file-upload" 
                type="file" 
                accept=".csv"
                className="hidden" 
                onChange={handleFileChange}
              />
            </div>

            {error && (
              <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-lg flex items-start gap-2">
                <Info className="size-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}
          </CardContent>
          <CardFooter className="flex justify-between border-t border-border/50 pt-4">
            <Button variant="outline" onClick={onLoadDemo} className="w-full sm:w-auto">
              Try Demo Signal
            </Button>
            <Button onClick={() => fileInputRef.current?.click()} className="w-full sm:w-auto">
              Select File
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
};
