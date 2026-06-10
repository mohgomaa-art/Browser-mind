import { formatDistanceToNowStrict, isYesterday, isToday } from "date-fns";

export function formatRelative(date: Date | string | number): string {
  const d = typeof date === "object" ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return "";
  if (isToday(d)) {
    const diff = Date.now() - d.getTime();
    if (diff < 60_000) return "just now";
    return `${formatDistanceToNowStrict(d)} ago`;
  }
  if (isYesterday(d)) return "yesterday";
  return `${formatDistanceToNowStrict(d)} ago`;
}

const COMPACT = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatNumber(n: number, compact = false): string {
  if (!Number.isFinite(n)) return "—";
  if (compact) return COMPACT.format(n);
  return new Intl.NumberFormat("en").format(n);
}

export function formatPercent(n: number, fractionDigits = 0): string {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(fractionDigits)}%`;
}

export function truncate(s: string, n: number): string {
  if (!s) return "";
  if (s.length <= n) return s;
  return `${s.slice(0, Math.max(0, n - 1))}…`;
}
