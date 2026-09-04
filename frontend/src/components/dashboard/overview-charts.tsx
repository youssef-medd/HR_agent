"use client";

/**
 * Overview charts — neo-brutalist marks over the real A9 series.
 *
 * Single-hue brand orange, but chunky: square bars with a hard ink stroke, a
 * dashed recessive grid, and a hard-edged tooltip with no radius or blur. One
 * series per chart → the card title names it, no legend.
 *
 * Data and the component API (`DayPoint`, `StagePoint`) are unchanged — only
 * the marks. Theme awareness stays in `useChartInk()`.
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
    grid: dark ? "rgba(236,229,219,0.16)" : "rgba(0,0,0,0.12)",
    muted: dark ? "#8c837a" : "#7b8089",
    ink: dark ? "#ece5db" : "#17181a",
    cursor: dark ? "rgba(236,229,219,0.07)" : "rgba(0,0,0,0.05)",
    // Bar outline — the defining mark of the brutalist treatment.
    stroke: dark ? "#ece5db" : "#000000",
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
    <div className="border-[3px] border-black bg-black px-3 py-1.5 text-white dark:border-[#ece5db] dark:bg-[#ece5db] dark:text-[#0b0a0a]">
      <p className="text-[10px] font-bold tracking-widest uppercase opacity-70">
        {label}
      </p>
      <p className="brutal-num text-lg leading-tight">{payload[0].value}</p>
    </div>
  );
}

export function ApplicationsOverTime({ data }: { data: DayPoint[] }) {
  const ink = useChartInk();
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 20, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={ink.grid} strokeDasharray="4 4" />
        <XAxis
          dataKey="day"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 10, fill: ink.muted, fontWeight: 700 }}
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
        <Bar
          dataKey="count"
          fill={ORANGE}
          stroke={ink.stroke}
          strokeWidth={2}
          radius={0}
          maxBarSize={34}
        >
          <LabelList
            dataKey="count"
            position="top"
            formatter={(v: React.ReactNode) => (Number(v) > 0 ? String(v) : "")}
            style={{
              fontSize: 11,
              fill: ink.ink,
              fontWeight: 700,
              fontFamily: "var(--font-jetbrains)",
            }}
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
        <CartesianGrid horizontal={false} stroke={ink.grid} strokeDasharray="4 4" />
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="stage"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 11, fill: ink.ink, fontWeight: 700 }}
          width={130}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: ink.cursor }} />
        <Bar
          dataKey="count"
          fill={ORANGE}
          stroke={ink.stroke}
          strokeWidth={2}
          radius={0}
          maxBarSize={22}
        >
          <LabelList
            dataKey="count"
            position="right"
            style={{
              fontSize: 11,
              fill: ink.ink,
              fontWeight: 700,
              fontFamily: "var(--font-jetbrains)",
            }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
