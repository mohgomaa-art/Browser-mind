import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from "@/components/ui";
import { useEnvironments, useReplays } from "@/lib/queries";
import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { formatPercent, formatRelative } from "@/lib/utils";
import type { ReplayStatus } from "@/types";

const STATUS_VARIANT: Record<ReplayStatus, "active" | "warning" | "error"> = {
  OK: "active",
  BLOCKED: "warning",
  FAIL: "error",
};

export default function ReplaysPage() {
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<string>("all");
  const [env, setEnv] = useState<string>("all");
  const [campaignPending, setCampaignPending] = useState(false);
  const [campaignMsg, setCampaignMsg] = useState<string | null>(null);

  async function runCampaign() {
    if (campaignPending) return;
    setCampaignPending(true);
    setCampaignMsg(null);
    try {
      await adapter.benchmark.run();
      setCampaignMsg("Replay campaign started.");
      void replaysQ.refetch();
    } catch (e) {
      setCampaignMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCampaignPending(false);
    }
  }

  const filter: { workflowId?: string; environmentKey?: string } = {};
  if (workflow !== "all") filter.workflowId = workflow;
  if (env !== "all") filter.environmentKey = env;

  const replaysQ = useReplays(Object.keys(filter).length ? filter : undefined);
  const envsQ = useEnvironments();
  const wfQ = useQuery({
    queryKey: ["workflows"],
    queryFn: () => adapter.workflows.list(),
  });

  const items = replaysQ.data ?? [];
  const summary = useMemo(() => {
    if (items.length === 0) {
      return { rr: 0, fpr: 0, tcr: 0, count: 0 };
    }
    const rr = items.reduce((s, r) => s + r.resolutionRate, 0) / items.length;
    const fprItems = items.filter((r) => r.falsePositiveRate != null);
    const fpr = fprItems.length
      ? fprItems.reduce((s, r) => s + (r.falsePositiveRate ?? 0), 0) /
        fprItems.length
      : 0;
    const tcrItems = items.filter((r) => r.taskCompletionRate != null);
    const tcr = tcrItems.length
      ? tcrItems.reduce((s, r) => s + (r.taskCompletionRate ?? 0), 0) /
        tcrItems.length
      : 0;
    return { rr, fpr, tcr, count: items.length };
  }, [items]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Replays</h1>
          <p className="text-xs text-text-muted">
            Reproductions of workflows with verification verdicts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {campaignMsg && (
            <span className="text-xs text-text-muted">{campaignMsg}</span>
          )}
          <Button size="sm" disabled={campaignPending} onClick={runCampaign}>
            {campaignPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Run Campaign
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-4 gap-3">
        <SummaryCard label="Avg Resolution" value={formatPercent(summary.rr)} />
        <SummaryCard label="Avg FPR" value={formatPercent(summary.fpr)} />
        <SummaryCard label="Avg Task Completion" value={formatPercent(summary.tcr)} />
        <SummaryCard label="Total Runs" value={String(summary.count)} />
      </div>

      <div className="flex items-center gap-2">
        <Select value={workflow} onValueChange={setWorkflow}>
          <SelectTrigger className="w-56 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All workflows</SelectItem>
            {(wfQ.data ?? []).map((w) => (
              <SelectItem key={w.id} value={w.id}>
                {w.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={env} onValueChange={setEnv}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All envs</SelectItem>
            {(envsQ.data ?? []).map((e) => (
              <SelectItem key={e.key} value={e.key}>
                {e.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Workflow</TableHead>
              <TableHead>Env</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Resolution</TableHead>
              <TableHead className="text-right">FPR</TableHead>
              <TableHead className="text-right">Task</TableHead>
              <TableHead className="text-right">Steps</TableHead>
              <TableHead>Failure</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {replaysQ.isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={10}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : items.map((r) => (
                  <TableRow
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/dev/replays/${r.id}`)}
                  >
                    <TableCell className="font-mono text-xs">{r.id}</TableCell>
                    <TableCell className="font-mono text-[11px] text-text-muted">
                      {r.workflowId}
                    </TableCell>
                    <TableCell>
                      <Tag variant="neutral">{r.environmentKey}</Tag>
                    </TableCell>
                    <TableCell>
                      <Tag variant={STATUS_VARIANT[r.status]}>{r.status}</Tag>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPercent(r.resolutionRate)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.falsePositiveRate != null
                        ? formatPercent(r.falsePositiveRate)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.taskCompletionRate != null
                        ? formatPercent(r.taskCompletionRate)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.totalSteps}
                    </TableCell>
                    <TableCell>
                      {r.failureCategory ? (
                        <Tag variant="error">{r.failureCategory}</Tag>
                      ) : (
                        <span className="text-text-subtle text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {formatRelative(r.createdAt)}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle">
          {label}
        </div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
