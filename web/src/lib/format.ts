export function money(value: number | null | undefined, full = false): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  if (full || Math.abs(value) < 100_000)
    return `PKR ${new Intl.NumberFormat("en-PK", { maximumFractionDigits: 0 }).format(value)}`;
  const scale = Math.abs(value) >= 10_000_000 ? 10_000_000 : 100_000;
  return `PKR ${(value / scale).toLocaleString("en-PK", { maximumFractionDigits: 2 })} ${scale === 100_000 ? "lakh" : "crore"}`;
}
export function percent(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value)
    ? "Not available"
    : `${value.toFixed(digits)}%`;
}
export function date(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return "Not available";
  return new Intl.DateTimeFormat("en-PK", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Karachi",
  }).format(new Date(value));
}
export function observedDays(start: string | null, end: string | null): number {
  if (!start || !end) return 0;
  const days = (Date.parse(end) - Date.parse(start)) / 86_400_000;
  return Number.isFinite(days) && days >= 0 ? Math.floor(days) + 1 : 0;
}

export function chartLabel(value: string | number): string {
  const label = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(label) && Number.isFinite(Date.parse(label))) {
    return new Intl.DateTimeFormat("en-PK", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    }).format(new Date(label));
  }
  return label;
}

export function chartDay(value: number): string {
  return `${value.toLocaleString("en-PK", { maximumFractionDigits: 1 })}d`;
}
