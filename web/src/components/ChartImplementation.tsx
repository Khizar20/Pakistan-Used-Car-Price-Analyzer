import { useId, useState } from "react";
import { chartDay, chartLabel, money } from "../lib/format";
import {
  ResponsiveContainer,
  LineChart as ReLine,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  ErrorBar,
  ReferenceDot,
  ScatterChart as ReScatter,
  Scatter,
} from "recharts";

export type ChartRow = {
  label: string;
  value: number;
  lower?: number | null;
  upper?: number | null;
};
export type Props = {
  title: string;
  description: string;
  rows: ChartRow[];
  unit: string;
  kind?: "line" | "bar" | "scatter";
  step?: boolean;
  full?: boolean;
  marker?: { label: string; value: number };
};
export function Chart({
  title,
  description,
  rows,
  unit,
  kind = "line",
  marker,
  step = false,
  full = false,
}: Props) {
  const id = useId();
  const [table, setTable] = useState(false);
  const horizontal =
    kind === "bar" && rows.some((row) => row.label.length > 14);
  const height = horizontal ? Math.max(280, rows.length * 38) : 280;
  const formatTick = (value: number) =>
    unit.includes("PKR")
      ? money(value, full).replace("PKR ", "")
      : value.toLocaleString("en-PK", { maximumFractionDigits: 2 });
  const data = rows.map((row) => ({
    ...row,
    x: step ? Number.parseFloat(row.label) : Number(row.label),
    error:
      row.lower != null && row.upper != null
        ? [
            Math.max(0, row.value - row.lower),
            Math.max(0, row.upper - row.value),
          ]
        : [0, 0],
  }));
  return (
    <section className="chart-section" aria-labelledby={id}>
      <div className="section-heading">
        <h2 id={id}>{title}</h2>
        <button
          type="button"
          className="text-button"
          aria-expanded={table}
          onClick={() => setTable(!table)}
        >
          {table ? "Hide data table" : "Show data table"}
        </button>
      </div>
      <p className="caption">{description}</p>
      {rows.length ? (
        <>
          <div
            className="chart"
            style={{ height }}
            role="img"
            aria-label={`${title}. ${rows.length} points. ${description} Exact values are available in the data table.`}
          >
            <ResponsiveContainer width="100%" height={height} minWidth={1}>
              {kind === "bar" ? (
                <BarChart
                  data={data}
                  layout={horizontal ? "vertical" : "horizontal"}
                  accessibilityLayer={false}
                  margin={{ left: 5, right: 24, top: 12, bottom: 24 }}
                >
                  <CartesianGrid vertical={false} stroke="var(--chalk)" />
                  <XAxis
                    dataKey={horizontal ? undefined : "label"}
                    tickFormatter={horizontal ? formatTick : chartLabel}
                    type={horizontal ? "number" : "category"}
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    type={horizontal ? "category" : "number"}
                    tickFormatter={horizontal ? undefined : formatTick}
                    dataKey={horizontal ? "label" : undefined}
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                    width={horizontal ? 148 : 65}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--paper)",
                      border: "1px solid var(--chalk)",
                      color: "var(--ink)",
                    }}
                  />
                  <Bar
                    dataKey="value"
                    name={unit}
                    fill="var(--motorway)"
                    isAnimationActive={false}
                  >
                    <ErrorBar
                      dataKey="error"
                      direction={horizontal ? "x" : "y"}
                      width={4}
                      stroke="var(--ink)"
                    />
                  </Bar>
                </BarChart>
              ) : kind === "scatter" ? (
                <ReScatter
                  data={data}
                  accessibilityLayer={false}
                  margin={{ left: 5, right: 24, top: 12, bottom: 24 }}
                >
                  <CartesianGrid stroke="var(--chalk)" />
                  <XAxis
                    dataKey="x"
                    tickFormatter={formatTick}
                    type="number"
                    name="Fitted PKR"
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                  />
                  <YAxis
                    dataKey="value"
                    tickFormatter={formatTick}
                    type="number"
                    name={unit}
                    width={65}
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--paper)",
                      border: "1px solid var(--chalk)",
                      color: "var(--ink)",
                    }}
                  />
                  <Scatter
                    data={data}
                    fill="var(--motorway)"
                    isAnimationActive={false}
                  />
                </ReScatter>
              ) : (
                <ReLine
                  data={data}
                  accessibilityLayer={false}
                  margin={{ left: 5, right: 24, top: 12, bottom: 24 }}
                >
                  <CartesianGrid vertical={false} stroke="var(--chalk)" />
                  <XAxis
                    dataKey={step ? "x" : "label"}
                    type={step ? "number" : "category"}
                    domain={step ? [0, "dataMax"] : undefined}
                    tickFormatter={step ? chartDay : chartLabel}
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: "var(--muted)", fontSize: 12 }}
                    tickFormatter={formatTick}
                    width={65}
                    domain={step ? [0, 100] : ["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--paper)",
                      border: "1px solid var(--chalk)",
                      color: "var(--ink)",
                    }}
                  />
                  <Line
                    type={step ? "stepAfter" : "linear"}
                    dataKey="value"
                    name={unit}
                    stroke="var(--motorway)"
                    strokeWidth={2}
                    dot={rows.length === 1 ? { r: 4 } : false}
                    isAnimationActive={false}
                  />
                  <Line
                    type={step ? "stepAfter" : "linear"}
                    dataKey="lower"
                    name="Lower bound"
                    stroke="var(--muted)"
                    strokeDasharray="3 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type={step ? "stepAfter" : "linear"}
                    dataKey="upper"
                    name="Upper bound"
                    stroke="var(--muted)"
                    strokeDasharray="3 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                  {marker && (
                    <ReferenceDot
                      className="selected-point"
                      x={marker.label}
                      y={marker.value}
                      r={6}
                      fill="var(--marker)"
                      stroke="var(--ink)"
                    />
                  )}
                </ReLine>
              )}
            </ResponsiveContainer>
          </div>
          {table && (
            <div className="table-wrap">
              <table>
                <caption>
                  {title} — {unit}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Observation</th>
                    <th scope="col">Value</th>
                    <th scope="col">Lower bound</th>
                    <th scope="col">Upper bound</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      <th scope="row">{row.label}</th>
                      <td>
                        {row.value.toLocaleString("en-PK", {
                          maximumFractionDigits: 3,
                        })}
                      </td>
                      <td>
                        {row.lower?.toLocaleString("en-PK", {
                          maximumFractionDigits: 3,
                        }) ?? "Not available"}
                      </td>
                      <td>
                        {row.upper?.toLocaleString("en-PK", {
                          maximumFractionDigits: 3,
                        }) ?? "Not available"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <Empty
          level={3}
          title="More observations are needed"
          detail="There are no supported points for this view yet."
        />
      )}
    </section>
  );
}
export const LineChart = Chart;
export function BarWithCI(props: Omit<Props, "kind">) {
  return <Chart {...props} kind="bar" />;
}
export function SurvivalChart(props: Props) {
  return <Chart {...props} step />;
}
export function ScatterChart(props: Props) {
  return <Chart {...props} kind="scatter" />;
}
export const DepreciationCurve = Chart;
export function Empty({
  title,
  detail,
  level = 2,
}: {
  title: string;
  detail: string;
  level?: 2 | 3;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <div className="empty">
      <span className="empty-symbol" aria-hidden="true">
        —
      </span>
      <div>
        <Heading>{title}</Heading>
        <p>{detail}</p>
        <a href="#about">How the data works</a>
      </div>
    </div>
  );
}
