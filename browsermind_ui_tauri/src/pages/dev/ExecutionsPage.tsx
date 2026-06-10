import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
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
import { useExecutions } from "@/lib/queries";
import { formatRelative } from "@/lib/utils";
import type { ExecutionState } from "@/types";

const EXEC_VARIANT: Record<
  ExecutionState,
  "active" | "warning" | "error" | "neutral" | "expired"
> = {
  pending: "neutral",
  running: "active",
  paused: "warning",
  waiting: "warning",
  failed: "error",
  completed: "active",
  cancelled: "expired",
};

function duration(start: string, end?: string): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

export default function ExecutionsPage() {
  const navigate = useNavigate();
  const [stateFilter, setStateFilter] = useState<string>("all");
  const execsQ = useExecutions(
    stateFilter === "all" ? undefined : { state: stateFilter as ExecutionState },
  );

  const items = execsQ.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Executions</h1>
          <p className="text-xs text-text-muted">
            Every replay run, with snapshot and checkpoint counts.
          </p>
        </div>
      </header>

      <div className="flex items-center gap-2">
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="paused">Paused</SelectItem>
            <SelectItem value="waiting">Waiting</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Ended</TableHead>
              <TableHead className="text-right">Duration</TableHead>
              <TableHead className="text-right">Retries</TableHead>
              <TableHead className="text-right">Step</TableHead>
              <TableHead className="text-right">Snap</TableHead>
              <TableHead className="text-right">Check</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {execsQ.isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={10}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : items.map((e) => (
                  <TableRow
                    key={e.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/dev/executions/${e.id}`)}
                  >
                    <TableCell className="font-mono text-xs">{e.id}</TableCell>
                    <TableCell className="font-mono text-[11px] text-text-muted">
                      {e.taskId}
                    </TableCell>
                    <TableCell>
                      <Tag variant={EXEC_VARIANT[e.state]}>{e.state}</Tag>
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {formatRelative(e.startedAt)}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {e.endedAt ? formatRelative(e.endedAt) : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-xs">
                      {duration(e.startedAt, e.endedAt)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{e.retryCount}</TableCell>
                    <TableCell className="text-right tabular-nums">{e.currentStepSeq ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{e.snapshots.length}</TableCell>
                    <TableCell className="text-right tabular-nums">{e.checkpoints.length}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
