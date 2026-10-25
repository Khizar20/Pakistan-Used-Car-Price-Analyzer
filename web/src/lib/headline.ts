export type Point = {
  week: string;
  value: number;
  lower?: number | null;
  upper?: number | null;
};
export function headline(points: Point[], supported: boolean): string {
  if (!supported || points.length < 2 || points[0].value <= 0)
    return "A clearer picture starts with more observations.";
  const change = (points.at(-1)!.value / points[0].value - 1) * 100;
  if (Math.abs(change) < 0.1)
    return "Asking prices held broadly steady in the observed period.";
  return `Asking prices ${change < 0 ? "fell" : "rose"} ${Math.abs(change).toFixed(1)}% in the observed period.`;
}
