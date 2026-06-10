import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui";
import { useAnalytics } from "@/lib/queries";
import { formatPercent } from "@/lib/utils";

const tooltipStyle = {
  contentStyle: {
    background: "#18181B",
    border: "1px solid #232326",
    borderRadius: 6,
    fontSize: 11,
  },
  labelStyle: { color: "#A1A1AA" },
  itemStyle: { color: "#FAFAFA" },
} as const;

export default function AnalyticsPage() {
  const { data, isLoading } = useAnalytics();

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
          <p className="text-xs text-text-muted">
            Replay reliability and failure attribution.
          </p>
        </header>
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const trend = data.trend.map((p) => ({
    date: p.date,
    rate: Math.round(p.resolutionRate * 100),
    fpr: Math.round(p.fpr * 100),
  }));

  const failureChart = data.failureOntology
    .slice()
    .sort((a, b) => b.share - a.share)
    .map((f) => ({
      name: f.category.replace(/_/g, " "),
      share: Math.round(f.share * 1000) / 10,
    }));

  const driftChart = data.trend.map((p) => ({
    date: p.date,
    drift: Math.round(data.identityDrift * 100 * (1 - p.resolutionRate * 0.4)),
  }));

  const ceiling = Math.round(data.replayCeiling * 100);
  const current = Math.round(data.replayResolutionRate * 100);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
        <p className="text-xs text-text-muted">
          Replay reliability, failure attribution, and trend.
        </p>
      </header>

      <div className="grid grid-cols-12 gap-4">
        <SparkCard
          className="col-span-3"
          label="Resolution Rate"
          value={formatPercent(data.replayResolutionRate)}
          color="#3B82F6"
          trend={trend.map((t) => ({ date: t.date, v: t.rate }))}
        />
        <SparkCard
          className="col-span-3"
          label="False Positive Rate"
          value={formatPercent(data.falsePositiveRate)}
          color="#EF4444"
          trend={trend.map((t) => ({ date: t.date, v: t.fpr }))}
        />
        <SparkCard
          className="col-span-3"
          label="Task Completion"
          value={formatPercent(data.taskCompletionRate)}
          color="#10B981"
          trend={trend.map((t) => ({ date: t.date, v: t.rate }))}
        />
        <SparkCard
          className="col-span-3"
          label="Environment Stability"
          value={formatPercent(data.environmentStability)}
          color="#3B82F6"
          trend={trend.map((t) => ({ date: t.date, v: 100 - t.fpr }))}
        />

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Identity Drift</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={driftChart}>
                  <CartesianGrid stroke="#232326" strokeOpacity={0.3} vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "#A1A1AA", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#A1A1AA", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                  <RTooltip {...tooltipStyle} formatter={(v: number) => [`${v}%`, "Drift"]} />
                  <Bar dataKey="drift" fill="#F59E0B" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Replay Ceiling</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-3 py-3">
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>Current</span>
                <span className="tabular-nums">{current}%</span>
              </div>
              <div className="h-3 rounded-full bg-bg-elevated overflow-hidden flex">
                <div
                  className="h-full bg-accent"
                  style={{ width: `${current}%` }}
                />
                <div
                  className="h-full bg-accent/30"
                  style={{ width: `${Math.max(0, ceiling - current)}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>Ceiling</span>
                <span className="tabular-nums">{ceiling}%</span>
              </div>
              <div className="text-[11px] text-text-subtle">
                Headroom: {ceiling - current}% — once reached, further gains require
                workflow changes, not retries.
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-12">
          <CardHeader>
            <CardTitle>Failure Ontology Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={failureChart}>
                  <CartesianGrid stroke="#232326" strokeOpacity={0.3} vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#A1A1AA", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                    angle={-25}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis
                    tick={{ fill: "#A1A1AA", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={32}
                  />
                  <RTooltip {...tooltipStyle} formatter={(v: number) => [`${v}%`, "Share"]} />
                  <Bar dataKey="share" fill="#EF4444" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SparkCard({
  className,
  label,
  value,
  color,
  trend,
}: {
  className?: string;
  label: string;
  value: string;
  color: string;
  trend: { date: string; v: number }[];
}) {
  const gradId = `sparkGrad-${label.replace(/\s/g, "")}`;
  return (
    <Card className={className}>
      <CardContent className="p-4 flex flex-col gap-2">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle">
          {label}
        </div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        <div className="h-12 -mx-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trend} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={color}
                strokeWidth={1.5}
                fill={`url(#${gradId})`}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
