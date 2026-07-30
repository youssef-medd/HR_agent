"use client";

import { Download, Printer } from "lucide-react";

import { Button } from "@/components/ui/button";

/** A9 CSV/PDF export controls for the reports dashboard. */
export function ExportButtons() {
  return (
    <div className="flex gap-2">
      <Button variant="outline" size="sm" asChild>
        <a href="/api/reports/applications.csv" download>
          <Download className="size-4" /> CSV
        </a>
      </Button>
      <Button variant="outline" size="sm" onClick={() => window.print()}>
        <Printer className="size-4" /> Print / PDF
      </Button>
    </div>
  );
}
