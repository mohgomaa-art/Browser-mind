import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play, ExternalLink, AlertCircle, Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/utils";
import {
  useExecutions,
  useTasks,
  useEnvironments,
} from "@/lib/queries";
import type { Execution, ExecutionState } from "@/types";

type StateFilter = "all" | "running" | "paused" | "failed" | "completed";

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

function duration(exec: Execution): string {
  const start = new Date(exec.startedAt).getTime();
  const end = exec.endedAt ? new Date(exec.endedAt).getTime() : Date.now();
  const ms = Math.max(0, end - start);
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const execsQuery = useExecutions();
  const tasksQuery = useTasks();
  const envQuery = useEnvironments();

  const [stateFilter, setStateFilter] = useState<StateFilter>("all");
  const [envFilter, setEnvFilter] = useState<string>("all");

  const taskMap = useMemo(() => {
    const m = new Map<string, { goal: string; environmentKey?: string }>();
    (tasksQuery.data ?? []).forEach((t) =>
      m.set(t.id, { goal: t.goal, environmentKey: t.environmentKey }),
    );
    return m;
  }, [tasksQuery.data]);

  const envMap = useMemo(() => {
    const m = new Map<string, string>();
    (envQuery.data ?? []).forEach((e) => m.set(e.key, e.label));
    return m;
  }, [envQuery.data]);

  const filtered = useMemo(() => {
    return (execsQuery.data ?? [])
      .filter((e) => {
        if (stateFilter === "all") return true;
        return e.state === stateFilter;
      })
      .filter((e) => {
        if (envFilter === "all") return true;
        const t = taskMap.get(e.taskId);
        return t?.environmentKey === envFilter;
      })
      .sort(
        (a, b) =>
          new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
      );
  }, [execsQuery.data, stateFilter, envFilter, taskMap]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Sessions</h1>
          <p className="text-xs text-text-muted">
            Browser sessions across executions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex items-center rounded-md border border-border-default bg-bg-panel p-0.5">
            {(
              ["all", "running", "paused", "failed", "completed"] as StateFilter[]
            ).map((f) => (
              <button
                key={f}
                onClick={() => setStateFilter(f)}
                className={cn(
                  "px-2.5 h-7 rounded text-xs font-medium capitalize transition-colors",
                  stateFilter === f
                    ? "bg-bg-elevated text-text-primary"
                    : "text-text-muted hover:text-text-primary",
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <Select value={envFilter} onValueChange={setEnvFilter}>
            <SelectTrigger className="w-48 h-8">
              <SelectValue placeholder="All environments" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All environments</SelectItem>
              {(envQuery.data ?? []).map((e) => (
                <SelectItem key={e.key} value={e.key}>
                  {e.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {execsQuery.isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : execsQuery.isError ? (
        <Card>
          <div className="p-4 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load sessions.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => execsQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <div className="p-10 flex flex-col items-center gap-3">
            <Inbox className="h-6 w-6 text-text-subtle" />
            <p className="text-sm text-text-muted">No sessions match.</p>
          </div>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((session) => {
            const task = taskMap.get(session.taskId);
            const envLabel = task?.environmentKey
              ? envMap.get(task.environmentKey)
              : undefined;
            const canResume =
              session.state === "paused" || session.state === "waiting";
            return (
              <Card
                key={session.id}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/sessions/${session.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter")
                    navigate(`/sessions/${session.id}`);
                }}
                className="hover:border-border-strong transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <div className="p-3 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-text-primary truncate">
                      {task?.goal ?? "Untitled session"}
                    </div>
                    <div className="text-[11px] text-text-muted">
                      Started {formatRelative(session.startedAt)} ·{" "}
                      {duration(session)}
                    </div>
                  </div>
                  {envLabel ? (
                    <Badge variant="neutral">{envLabel}</Badge>
                  ) : null}
                  <Badge variant={execVariant(session.state)}>
                    {session.state}
                  </Badge>
                  <Button
                    size="sm"
                    variant={canResume ? "default" : "ghost"}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/sessions/${session.id}`);
                    }}
                  >
                    {canResume ? (
                      <>
                        <Play className="h-3.5 w-3.5" />
                        Resume
                      </>
                    ) : (
                      <>
                        <ExternalLink className="h-3.5 w-3.5" />
                        Timeline
                      </>
                    )}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
