import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Globe,
  KeyRound,
} from "lucide-react";
import {
  Bar,
  BarChart,
  Area,
  AreaChart,
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
  Tag,
} from "@/components/ui";
import {
  useAnalytics,
  useEnvironments,
  useExecutions,
  useIdentities,
  useTasks,
} from "@/lib/queries";
import { formatPercent, formatRelative } from "@/lib/utils";
import { adapter } from "@/lib/adapters";
import type { TaskState } from "@/types";

const TASK_STATE_VARIANT: Record<
  TaskState,
  "active" | "warning" | "error" | "neutral" | "expired"
> = {
  created: "neutral",
  running: "active",
  paused: "warning",
  waiting: "warning",
  blocked: "warning",
  failed: "error",
  completed: "active",
};

function chartTooltip() {
  return {
    contentStyle: {
      background: "#18181B",
      border: "1px solid #232326",
      borderRadius: 6,
      fontSize: 11,
    },
    labelStyle: { color: "#A1A1AA" },
    itemStyle: { color: "#FAFAFA" },
  };
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle">
          {label}
        </div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {hint && (
          <div className="text-[11px] text-text-subtle">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const tasks = useTasks();
  const execs = useExecutions();
  const identities = useIdentities();
  const envs = useEnvironments();
  const analytics = useAnalytics();
  const recentLedger = useQuery({
    queryKey: ["ledger", "dashboard"],
    queryFn: () => adapter.ledger.list({ kind: "execution" }),
  });

  const running = (execs.data ?? []).filter((e) => e.state === "running").length;
  const activeIdentities = (identities.data ?? []).filter((i) => i.status === "active").length;
  const connectedEnvs = (envs.data ?? []).filter((e) => e.status === "connected").length;

  const hourBins = Array.from({ length: 24 }, (_, i) => ({
    hour: `${i}:00`,
    count: 0,
  }));
  for (const e of execs.data ?? []) {
    const h = new Date(e.startedAt).getHours();
    if (hourBins[h]) hourBins[h].count += 1;
  }

  const failureChart = (analytics.data?.failureOntology ?? [])
    .slice()
    .sort((a, b) => b.share - a.share)
    .slice(0, 6)
    .map((f) => ({
      name: f.category.replace(/_/g, " "),
      share: Math.round(f.share * 1000) / 10,
    }));

  const trend = (analytics.data?.trend ?? []).map((p) => ({
    date: p.date,
    rate: Math.round(p.resolutionRate * 100),
    fpr: Math.round(p.fpr * 100),
  }));

  const recentTasks = (tasks.data ?? [])
    .slice()
    .sort(
      (a, b) =>
        new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    )
    .slice(0, 5);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
        <p className="text-xs text-text-muted">
          System overview and recent activity
        </p>
      </header>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-3">
          <StatCard
            label="Active Executions"
            value={running}
            hint={
              <span className="inline-flex items-center gap-1">
                <Activity className="h-3 w-3" /> running now
              </span> as unknown as string
            }
          />
        </div>
        <div className="col-span-3">
          <StatCard
            label="Replay Success"
            value={
              analytics.data
                ? formatPercent(analytics.data.replayResolutionRate)
                : "—"
            }
            hint="14-day average"
          />
        </div>
        <div className="col-span-3">
          <StatCard
            label="Identity Health"
            value={`${activeIdentities} / ${identities.data?.length ?? 0}`}
            hint={
              <span className="inline-flex items-center gap-1">
                <KeyRound className="h-3 w-3" /> active
              </span> as unknown as string
            }
          />
        </div>
        <div className="col-span-3">
          <StatCard
            label="Environment Health"
            value={`${connectedEnvs} / ${envs.data?.length ?? 0}`}
            hint={
              <span className="inline-flex items-center gap-1">
                <Globe className="h-3 w-3" /> connected
              </span> as unknown as string
            }
          />
        </div>

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Execution Timeline (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hourBins}>
                  <CartesianGrid stroke="#232326" strokeOpacity={0.3} vertical={false} />
                  <XAxis
                    dataKey="hour"
                    tick={{ fill: "#A1A1AA", fontSize: 10 }}
                    axisLine={{ stroke: "#232326" }}
                    tickLine={false}
                    interval={3}
                  />
                  <YAxis
                    tick={{ fill: "#A1A1AA", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                  />
                  <RTooltip {...chartTooltip()} />
                  <Bar dataKey="count" fill="#3B82F6" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Failure Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={failureChart}
                  layout="vertical"
                  margin={{ left: 10, right: 8 }}
                >
                  <CartesianGrid stroke="#232326" strokeOpacity={0.3} horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: "#A1A1AA", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fill: "#A1A1AA", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    width={120}
                  />
                  <RTooltip
                    {...chartTooltip()}
                    formatter={(v: number) => [`${v}%`, "Share"]}
                  />
                  <Bar dataKey="share" fill="#EF4444" radius={[0, 2, 2, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Recent Tasks</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {tasks.isLoading ? (
              <div className="p-4">
                <Skeleton className="h-4 w-full mb-2" />
                <Skeleton className="h-4 w-full mb-2" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : (
              <table className="w-full text-xs">
                <tbody>
                  {recentTasks.map((t) => (
                    <tr
                      key={t.id}
                      className="border-t border-border-default hover:bg-bg-elevated"
                    >
                      <td className="py-2 px-3 truncate max-w-0">{t.goal}</td>
                      <td className="py-2 px-3">
                        <Tag variant={TASK_STATE_VARIANT[t.state]}>
                          {t.state}
                        </Tag>
                      </td>
                      <td className="py-2 px-3 text-text-muted">
                        {t.environmentKey ?? "—"}
                      </td>
                      <td className="py-2 px-3 text-text-subtle text-right">
                        {formatRelative(t.updatedAt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card className="col-span-6">
          <CardHeader>
            <CardTitle>Replay Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend}>
                  <defs>
                    <linearGradient id="dRate" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#3B82F6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#232326" strokeOpacity={0.3} vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#A1A1AA", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "#A1A1AA", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                  />
                  <RTooltip {...chartTooltip()} />
                  <Area
                    type="monotone"
                    dataKey="rate"
                    name="Resolution"
                    stroke="#3B82F6"
                    fill="url(#dRate)"
                    strokeWidth={1.5}
                  />
                  <Area
                    type="monotone"
                    dataKey="fpr"
                    name="FPR"
                    stroke="#EF4444"
                    fill="transparent"
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {recentLedger.data && recentLedger.data.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent Activity</CardTitle>
            <span className="text-[11px] text-text-subtle">
              <AlertTriangle className="h-3 w-3 inline mr-1" />
              read-only
            </span>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="text-xs">
              {recentLedger.data.slice(0, 8).map((e) => (
                <li
                  key={e.id}
                  className="flex items-center gap-3 px-4 py-2 border-t border-border-default"
                >
                  <span className="text-text-subtle font-mono text-[11px] w-24">
                    {formatRelative(e.timestamp)}
                  </span>
                  <span className="flex-1 truncate text-text-muted">
                    {e.summary}
                  </span>
                  <Tag variant="neutral">{e.entityType}</Tag>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
