import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Loader2, RefreshCw } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatPercent, formatRelative } from "@/lib/utils";
import type { BenchmarkReport } from "@/lib/adapters/tauri";

function successRateVariant(rate: number): "active" | "warning" | "error" {
  if (rate >= 1.0) return "active";
  if (rate >= 0.5) return "warning";
  return "error";
}

function SuccessRateBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color =
    rate >= 1.0
      ? "bg-state-success"
      : rate >= 0.5
        ? "bg-state-warning"
        : "bg-state-error";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-bg-elevated overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="tabular-nums text-xs w-9 text-right">
        {pct}%
      </span>
    </div>
  );
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

export default function BenchmarkPage() {
  const queryClient = useQueryClient();
  const [runLoading, setRunLoading] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["benchmark", "reports"],
    queryFn: () => adapter.benchmark.listReports(),
    refetchInterval: 30000,
  });

  const reports = (data ?? []) as BenchmarkReport[];
  const latest = reports.length > 0
    ? [...reports].sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      )[0]
    : null;

  async function handleRun() {
    setRunLoading(true);
    setRunMsg(null);
    try {
      await adapter.benchmark.run();
      setRunMsg("Benchmark started. Results will appear when complete.");
      void queryClient.invalidateQueries({ queryKey: ["benchmark", "reports"] });
    } catch (e) {
      setRunMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRunLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Benchmark</h1>
          <p className="text-xs text-text-muted">
            Frozen benchmark suite — aggregate success rates across all registered workflows
          </p>
        </div>
        <div className="flex items-center gap-2">
          {runMsg && (
            <span className="text-xs text-text-muted max-w-xs truncate">
              {runMsg}
            </span>
          )}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void refetch()}
            disabled={isFetching || runLoading}
          >
            {isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={handleRun}
            disabled={runLoading || isFetching}
          >
            {runLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <FlaskConical className="h-3.5 w-3.5" />
            )}
            {runLoading ? "Starting…" : "Run Benchmark"}
          </Button>
        </div>
      </header>

      {isError && (
        <p className="text-xs text-state-error">
          Failed to load reports:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      )}

      {/* Empty state */}
      {!isLoading && reports.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-border-default bg-bg-panel py-16 gap-3 text-center">
          <FlaskConical className="h-8 w-8 text-text-subtle" />
          <p className="text-sm text-text-muted">No benchmark reports found.</p>
          <p className="text-xs text-text-subtle">
            Click &ldquo;Run Benchmark&rdquo; to generate the first report.
          </p>
        </div>
      )}

      {/* Latest report metrics */}
      {(isLoading || latest) && (
        <>
          <div className="grid grid-cols-4 gap-4">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <Skeleton className="h-4 w-24 mb-2" />
                    <Skeleton className="h-7 w-16" />
                  </CardContent>
                </Card>
              ))
            ) : latest ? (
              <>
                <StatCard
                  label="Aggregate Success Rate"
                  value={formatPercent(latest.aggregateSuccessRate)}
                  hint="latest run"
                />
                <StatCard
                  label="Total Runs"
                  value={latest.workflowCount * latest.runsPerWorkflow}
                  hint={`${latest.runsPerWorkflow} per workflow`}
                />
                <StatCard
                  label="Workflow Count"
                  value={latest.workflowCount}
                  hint="registered workflows"
                />
                <StatCard
                  label="Latest Date"
                  value={formatRelative(latest.timestamp)}
                  hint={new Date(latest.timestamp).toLocaleDateString()}
                />
              </>
            ) : null}
          </div>

          {/* Workflow breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Workflow Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="rounded-b-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Workflow</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Success Rate</TableHead>
                      <TableHead className="text-right">Runs</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoading ? (
                      Array.from({ length: 4 }).map((_, i) => (
                        <TableRow key={i}>
                          <TableCell colSpan={5}>
                            <Skeleton className="h-4 w-full" />
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      (latest?.workflows ?? []).map((wf) => (
                        <TableRow key={wf.name}>
                          <TableCell className="font-medium font-mono text-xs">
                            {wf.name}
                          </TableCell>
                          <TableCell className="text-xs text-text-muted max-w-xs truncate">
                            {wf.description || "—"}
                          </TableCell>
                          <TableCell>
                            <Tag variant={successRateVariant(wf.successRate)}>
                              {wf.successRate >= 1.0
                                ? "passing"
                                : wf.successRate <= 0
                                  ? "failing"
                                  : "partial"}
                            </Tag>
                          </TableCell>
                          <TableCell className="min-w-[140px]">
                            <SuccessRateBar rate={wf.successRate} />
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {latest?.runsPerWorkflow ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* History table */}
      {(isLoading || reports.length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>Report History</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="rounded-b-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Aggregate Success Rate</TableHead>
                    <TableHead className="text-right">Runs / Workflow</TableHead>
                    <TableHead className="text-right">Workflow Count</TableHead>
                    <TableHead>File</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    Array.from({ length: 3 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={5}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    [...reports]
                      .sort(
                        (a, b) =>
                          new Date(b.timestamp).getTime() -
                          new Date(a.timestamp).getTime(),
                      )
                      .map((r) => (
                        <TableRow key={r.filename}>
                          <TableCell className="text-xs text-text-muted">
                            {formatRelative(r.timestamp)}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <Tag variant={successRateVariant(r.aggregateSuccessRate)}>
                                {formatPercent(r.aggregateSuccessRate)}
                              </Tag>
                            </div>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {r.runsPerWorkflow}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {r.workflowCount}
                          </TableCell>
                          <TableCell className="font-mono text-[11px] text-text-subtle truncate max-w-[200px]">
                            {r.filename}
                          </TableCell>
                        </TableRow>
                      ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
