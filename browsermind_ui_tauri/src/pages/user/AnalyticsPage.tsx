import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui";
import { useAnalytics } from "@/lib/queries";
import { formatPercent } from "@/lib/utils";
import type { FailureCategory } from "@/types";

function prettyCategory(c: FailureCategory): string {
  return c
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

export default function AnalyticsPage() {
  const { data, isLoading } = useAnalytics();

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
          <p className="text-xs text-text-muted">
            How well your automations are working
          </p>
        </header>
        <Skeleton className="h-32 w-full" />
        <div className="grid grid-cols-3 gap-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const sortedFailures = [...data.failureOntology].sort(
    (a, b) => b.share - a.share,
  );
  const top = sortedFailures[0];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
        <p className="text-xs text-text-muted">
          How well your automations are working
        </p>
      </header>

      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-2 py-8">
          <div className="text-xs text-text-muted">Replay Reliability</div>
          <div className="text-5xl font-semibold text-accent leading-none tabular-nums">
            {formatPercent(data.replayResolutionRate)}
          </div>
          <div className="text-xs text-text-subtle">Last 14 days</div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="text-xs text-text-muted">Tasks Completed</div>
            <div className="text-2xl font-semibold tabular-nums">
              {formatPercent(data.taskCompletionRate)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="text-xs text-text-muted">False Positive Rate</div>
            <div className="text-2xl font-semibold tabular-nums">
              {formatPercent(data.falsePositiveRate)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="text-xs text-text-muted">Environment Stability</div>
            <div className="text-2xl font-semibold tabular-nums">
              {formatPercent(data.environmentStability)}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Where things break</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-2.5">
            {sortedFailures.map((f) => (
              <div key={f.category} className="flex items-center gap-3">
                <div className="w-32 text-xs text-text-muted truncate">
                  {prettyCategory(f.category)}
                </div>
                <div className="flex-1 h-1.5 rounded-full bg-bg-elevated overflow-hidden">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${f.share * 100}%` }}
                  />
                </div>
                <div className="w-12 text-right text-xs tabular-nums">
                  {formatPercent(f.share)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Resolution Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[120px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data.trend.map((p) => ({
                  date: p.date,
                  rate: Math.round(p.resolutionRate * 100),
                }))}
                margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
              >
                <defs>
                  <linearGradient id="userTrend" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#3B82F6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#A1A1AA", fontSize: 11 }}
                  axisLine={{ stroke: "#232326" }}
                  tickLine={false}
                  hide
                />
                <YAxis
                  tick={{ fill: "#A1A1AA", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={28}
                  domain={[0, 100]}
                />
                <RTooltip
                  contentStyle={{
                    background: "#18181B",
                    border: "1px solid #232326",
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                  labelStyle={{ color: "#A1A1AA" }}
                  itemStyle={{ color: "#FAFAFA" }}
                  formatter={(v: number) => [`${v}%`, "Rate"]}
                />
                <Area
                  type="monotone"
                  dataKey="rate"
                  stroke="#3B82F6"
                  strokeWidth={1.5}
                  fill="url(#userTrend)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {top && (
        <Card>
          <CardHeader>
            <CardTitle>Top Failure</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <div className="text-base font-medium">
                {prettyCategory(top.category)}
              </div>
              <div className="text-xs text-text-muted">
                e.g. Location (City) Name Drift
              </div>
              <div className="text-xs text-text-subtle">
                {formatPercent(top.share)} of recent failures
              </div>
            </div>
            <Button variant="secondary" size="sm">
              View Evidence
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
