import { Component, lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Props } from "./ChartImplementation";
export type { ChartRow } from "./ChartImplementation";

const Plot = lazy(() =>
  import("./ChartImplementation").then((module) => ({ default: module.Chart })),
);
export function Chart(props: Props) {
  const height =
    props.kind === "bar" && props.rows.some((row) => row.label.length > 14)
      ? Math.max(280, props.rows.length * 38)
      : 280;
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (visible || !props.rows.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          if (container.current?.contains(document.activeElement))
            container.current.focus();
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100px" },
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [visible, props.rows.length]);
  if (!props.rows.length)
    return (
      <div className="chart-host">
        <section className="chart-section">
          <h2>{props.title}</h2>
          <p className="caption">{props.description}</p>
          <Empty
            level={3}
            title="More observations are needed"
            detail="There are no supported points for this view yet."
          />
        </section>
      </div>
    );
  const placeholder = (
    <section className="chart-section">
      <div className="section-heading">
        <h2>{props.title}</h2>
        <button className="text-button" disabled>
          Show data table
        </button>
      </div>
      <p className="caption">{props.description}</p>
      <div className="chart" style={{ height }}>
        <button
          onClick={() => {
            container.current?.focus();
            setVisible(true);
          }}
        >
          Load chart
        </button>
        <p className="caption">
          Charts load as you scroll into view. You can also load this chart with
          the button.
        </p>
      </div>
    </section>
  );
  return (
    <div
      ref={container}
      className="chart-host"
      tabIndex={-1}
      role="group"
      aria-label={props.title}
    >
      {visible ? (
        <Suspense
          fallback={
            <section className="chart-section">
              <div className="section-heading">
                <h2>{props.title}</h2>
                <button className="text-button" disabled>
                  Show data table
                </button>
              </div>
              <p className="caption">{props.description}</p>
              <div className="chart" role="status" style={{ height }}>
                Preparing chart data…
              </div>
            </section>
          }
        >
          <PlotBoundary>
            <Plot {...props} />
          </PlotBoundary>
        </Suspense>
      ) : (
        placeholder
      )}
    </div>
  );
}
class PlotBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div role="alert">
        <Empty
          title="This chart could not load"
          detail="Check your connection, then reload the page to retry."
        />
        <button onClick={() => location.reload()}>Reload page</button>
      </div>
    ) : (
      this.props.children
    );
  }
}
export const LineChart = Chart;
export function BarWithCI(props: Props) {
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
