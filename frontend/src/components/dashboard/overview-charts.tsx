"use client";

/**
 * Overview charts — single-hue (brand orange), thin marks, rounded data ends,
 * recessive grid, direct value labels (contrast relief per dataviz check),
 * tooltips on hover. One series per chart → the card title names it, no legend.
 */

import { useTheme } from "next-themes";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const ORANGE = "#ff6b00";

function useChartInk() {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  return {
    grid: dark ? "rgba(255,255,255,0.08)" : "#eceef0",
    muted: dark ? "#9a9fa8" : "#7b8089",
    ink: dark ? "#ecedee" : "#17181a",
    cursor: dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)",
  };
}

export interface DayPoint {
  day: string; // e.g. "Jul 08"
  count: number;
}

export interface StagePoint {
  stage: string; // pretty label e.g. "Shortlisted"
  count: number;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value?: number | string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover rounded-xl border px-3 py-2 shadow-md">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-sm font-semibold tabular-nums">{payload[0].value}</p>
    </div>
  );
}

export function ApplicationsOverTime({ data }: { data: DayPoint[] }) {
  const ink = useChartInk();
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 20, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={ink.grid} />
        <XAxis
          dataKey="day"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 11, fill: ink.muted }}
          interval="preserveStartEnd"
        />
        <YAxis
          allowDecimals={false}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 11, fill: ink.muted }}
          width={40}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: ink.cursor }} />
        <Bar dataKey="count" fill={ORANGE} radius={[4, 4, 0, 0]} maxBarSize={28}>
          <LabelList
            dataKey="count"
            position="top"
            formatter={(v: React.ReactNode) => (Number(v) > 0 ? String(v) : "")}
            style={{ fontSize: 11, fill: ink.ink, fontFamily: "var(--font-jetbrains)" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PipelineByStage({ data }: { data: StagePoint[] }) {
  const ink = useChartInk();
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 44)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 36, left: 8, bottom: 0 }}
      >
        <CartesianGrid horizontal={false} stroke={ink.grid} />
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="stage"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: ink.ink }}
          width={130}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: ink.cursor }} />
        <Bar dataKey="count" fill={ORANGE} radius={[0, 4, 4, 0]} maxBarSize={18}>
          <LabelList
            dataKey="count"
            position="right"
            style={{ fontSize: 11, fill: ink.ink, fontFamily: "var(--font-jetbrains)" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
