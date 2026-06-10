import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Repeat,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { formatRelative } from "@/lib/utils";
import {
  useExecution,
  useTask,
  useEnvironments,
  useIdentities,
} from "@/lib/queries";
import type { ExecutionEvent, ExecutionState } from "@/types";

function execVariant(state: ExecutionState) {
  switch (state) {
    case "running":
      return "accent" as const;
    case "paused":
    case "waiting":
      return "warning" as const;
    case "failed":
      return "error" as const;
    case "completed":
      return "success" as const;
    case "cancelled":
      return "neutral" as const;
    default:
      return "neutral" as const;
  }
}

function eventDotClass(kind: ExecutionEvent["kind"]): string {
  switch (kind) {
    case "navigate":
    case "fill":
      return "bg-accent";
    case "click":
      return "bg-text-primary";
    case "extract":
      return "bg-text-muted";
    case "verify":
      return "bg-state-success";
    case "pause":
      return "bg-state-warning";
    case "fail":
      return "bg-state-error";
    default:
      return "bg-text-subtle";
  }
}

function formatHHMM(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function durationLabel(startedAt: string, endedAt?: string): string {
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const ms = Math.max(0, end - start);
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export default function SessionTimelinePage() {
  const { executionId = "" } = useParams<{ executionId: string }>();

  const execQuery = useExecution(executionId);
  const taskQuery = useTask(execQuery.data?.taskId ?? "");
  const envQuery = useEnvironments();
  const identitiesQuery = useIdentities();

  const env = useMemo(() => {
    const t = taskQuery.data;
    if (!t?.environmentKey) return undefined;
    return (envQuery.data ?? []).find((e) => e.key === t.environmentKey);
  }, [taskQuery.data, envQuery.data]);

  const identity = useMemo(() => {
    const t = taskQuery.data;
    if (!t?.environmentKey) return undefined;
    return (identitiesQuery.data ?? []).find(
      (i) => i.environmentKey === t.environmentKey && i.personaId === t.personaId,
    );
  }, [taskQuery.data, identitiesQuery.data]);

  const sortedEvents = useMemo<ExecutionEvent[]>(() => {
    const events = execQuery.data?.events ?? [];
    return [...events].sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }, [execQuery.data]);

  if (execQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-64 rounded-md" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Skeleton className="lg:col-span-2 h-96 rounded-lg" />
          <Skeleton className="h-64 rounded-lg" />
        </div>
      </div>
    );
  }

  if (execQuery.isError || !execQuery.data) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          to="/sessions"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-3 w-3" /> Back to sessions
        </Link>
        <Card>
          <div className="p-6 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load this session.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => execQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const exec = execQuery.data;
  const canResume = exec.state === "paused" || exec.state === "waiting";

  return (
    <div className="flex flex-col gap-6 pb-20">
      <div>
        <Link
          to="/sessions"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-3 w-3" /> Back to sessions
        </Link>
        <header className="flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight truncate">
              {taskQuery.data?.goal ?? "Session"}
            </h1>
            <div className="text-xs text-text-muted">
              {durationLabel(exec.startedAt, exec.endedAt)} ·{" "}
              {formatRelative(exec.startedAt)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {env ? <Badge variant="neutral">{env.label}</Badge> : null}
            <Badge variant={execVariant(exec.state)}>{exec.state}</Badge>
          </div>
        </header>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {sortedEvents.length === 0 ? (
              <p className="text-xs text-text-muted">No events yet.</p>
            ) : (
              <ol className="relative">
                <div className="absolute left-[3.25rem] top-0 bottom-0 w-px bg-border-default" />
                {sortedEvents.map((ev) => (
                  <li
                    key={ev.id}
                    className="relative flex items-start gap-3 py-2"
                  >
                    <div className="w-12 shrink-0 text-right font-mono text-[11px] text-text-subtle pt-1">
                      {formatHHMM(ev.timestamp)}
                    </div>
                    <div className="relative w-3 shrink-0 flex justify-center pt-2">
                      <div
                        className={`h-2 w-2 rounded-full ${eventDotClass(ev.kind)} ring-2 ring-bg-panel`}
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-text-primary">
                        {ev.summary}
                      </div>
                      {ev.detail ? (
                        <div className="text-xs text-text-muted">
                          {ev.detail}
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <aside className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Summary</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-xs">
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Task</span>
                <span className="text-text-primary truncate max-w-[14rem] text-right">
                  {taskQuery.data?.goal ?? "—"}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Environment</span>
                <span className="text-text-primary">{env?.label ?? "—"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Identity</span>
                <span className="text-text-primary truncate max-w-[14rem] text-right">
                  {identity?.identifier ?? "—"}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Snapshots</span>
                <span className="text-text-primary">
                  {exec.snapshots.length}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Checkpoints</span>
                <span className="text-text-primary">
                  {exec.checkpoints.length}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Retries</span>
                <span className="text-text-primary">{exec.retryCount}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Recoveries</span>
                <span className="text-text-primary">
                  {exec.recoveryHistory.length}
                </span>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

      <div className="fixed bottom-0 left-0 right-0 z-10 border-t border-border-default bg-bg-base/95 backdrop-blur">
        <div className="px-6 py-3 flex items-center justify-end gap-2">
          {canResume ? (
            <Button>
              <Play className="h-3.5 w-3.5" />
              Resume execution
            </Button>
          ) : (
            <Button variant="secondary">
              <Repeat className="h-3.5 w-3.5" />
              Replay session
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
