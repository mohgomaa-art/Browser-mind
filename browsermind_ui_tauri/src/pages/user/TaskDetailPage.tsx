import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Play,
  ArrowLeft,
  AlertCircle,
  Globe2,
  Clock3,
  UserCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";
import {
  useTask,
  useExecutions,
  useEnvironments,
  useIdentities,
} from "@/lib/queries";
import type {
  ExecutionEvent,
  TaskState,
} from "@/types";

const STATE_LABEL: Record<TaskState, string> = {
  created: "Created",
  running: "Running",
  paused: "Paused",
  waiting: "Waiting",
  blocked: "Blocked",
  failed: "Failed",
  completed: "Completed",
};

function stateVariant(state: TaskState) {
  switch (state) {
    case "running":
      return "accent" as const;
    case "paused":
    case "waiting":
    case "blocked":
      return "warning" as const;
    case "failed":
      return "error" as const;
    case "completed":
      return "success" as const;
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

export default function TaskDetailPage() {
  const { taskId = "" } = useParams<{ taskId: string }>();
  const queryClient = useQueryClient();
  const taskQuery = useTask(taskId);
  const execsQuery = useExecutions({ taskId });
  const envQuery = useEnvironments();
  const identitiesQuery = useIdentities();
  const [resumePending, setResumePending] = useState(false);
  const [provideResource, setProvideResource] = useState<string | null>(null);

  async function resumeExec() {
    const exec = recentExec;
    if (!exec || resumePending) return;
    setResumePending(true);
    try {
      await adapter.executions.act(exec.id, "resume");
      await queryClient.invalidateQueries({ queryKey: ["executions"] });
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    } finally {
      setResumePending(false);
    }
  }

  const recentExec = useMemo(() => {
    const list = execsQuery.data ?? [];
    if (list.length === 0) return undefined;
    return [...list].sort(
      (a, b) =>
        new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    )[0];
  }, [execsQuery.data]);

  const recentEvents = useMemo<ExecutionEvent[]>(() => {
    if (!recentExec) return [];
    return [...recentExec.events]
      .sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      )
      .slice(0, 6);
  }, [recentExec]);

  const task = taskQuery.data;
  const environment = task?.environmentKey
    ? (envQuery.data ?? []).find((e) => e.key === task.environmentKey)
    : undefined;
  const identity = task?.environmentKey
    ? (identitiesQuery.data ?? []).find(
        (i) =>
          i.environmentKey === task.environmentKey &&
          i.personaId === task.personaId,
      )
    : undefined;

  if (taskQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-64 rounded-md" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 flex flex-col gap-4">
            <Skeleton className="h-32 rounded-lg" />
            <Skeleton className="h-32 rounded-lg" />
          </div>
          <Skeleton className="h-64 rounded-lg" />
        </div>
      </div>
    );
  }

  if (taskQuery.isError || !task) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          to="/work"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-3 w-3" /> Back to work
        </Link>
        <Card>
          <div className="p-6 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load this task.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => taskQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const pct =
    task.progress.total > 0
      ? Math.round((task.progress.current / task.progress.total) * 100)
      : 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/work"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-3 w-3" /> Back to work
        </Link>
        <header className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-2 min-w-0">
            <h1 className="text-xl font-semibold tracking-tight truncate">
              {task.goal}
            </h1>
            <div className="flex items-center gap-2">
              <Badge variant={stateVariant(task.state)}>
                {STATE_LABEL[task.state]}
              </Badge>
              {environment ? (
                <Badge variant="neutral">{environment.label}</Badge>
              ) : null}
            </div>
          </div>
        </header>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Progress</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Progress value={pct} />
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>
                  {task.progress.current} of {task.progress.total} steps
                </span>
                <span>ETA ~ 4 min</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Missing Resources</CardTitle>
            </CardHeader>
            <CardContent>
              {task.missingResources.length === 0 ? (
                <p className="text-xs text-text-muted">
                  Nothing missing. Ready to continue.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {task.missingResources.map((res) => (
                    <li
                      key={res}
                      className="flex items-center justify-between gap-3 rounded-md border border-border-default bg-bg-elevated px-3 py-2"
                    >
                      <span className="text-sm text-text-primary">{res}</span>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setProvideResource(res)}
                      >
                        Provide
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Next Action</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-4">
              <p className="text-base text-text-primary">
                {task.nextAction ?? "No next action recorded."}
              </p>
              <Button
                disabled={resumePending || !recentExec}
                onClick={resumeExec}
              >
                <Play className="h-3.5 w-3.5" />
                {resumePending ? "Resuming…" : "Resume"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent Steps</CardTitle>
            </CardHeader>
            <CardContent>
              {execsQuery.isLoading ? (
                <Skeleton className="h-32 rounded-md" />
              ) : recentEvents.length === 0 ? (
                <p className="text-xs text-text-muted">
                  No events recorded yet.
                </p>
              ) : (
                <ol className="flex flex-col gap-2">
                  {recentEvents.map((ev) => (
                    <li key={ev.id} className="flex items-start gap-3">
                      <div className="flex flex-col items-center pt-1.5">
                        <div
                          className={`h-1.5 w-1.5 rounded-full ${eventDotClass(ev.kind)}`}
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
                      <span className="text-[11px] text-text-subtle whitespace-nowrap">
                        {formatRelative(ev.timestamp)}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe2 className="h-3.5 w-3.5 text-text-muted" />
                Account
              </CardTitle>
            </CardHeader>
            <CardContent>
              {environment ? (
                <Link
                  to={`/accounts/${environment.key}`}
                  className="block rounded-md border border-border-default bg-bg-elevated p-3 hover:border-border-strong transition-colors"
                >
                  <div className="text-sm font-medium text-text-primary">
                    {environment.label}
                  </div>
                  <div className="text-[11px] text-text-muted">
                    {environment.family}
                  </div>
                </Link>
              ) : (
                <p className="text-xs text-text-muted">No environment bound.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock3 className="h-3.5 w-3.5 text-text-muted" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-text-muted">Started</span>
                <span className="text-text-primary">
                  {formatRelative(task.createdAt)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-muted">Last activity</span>
                <span className="text-text-primary">
                  {formatRelative(task.lastEventAt ?? task.updatedAt)}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <UserCheck className="h-3.5 w-3.5 text-text-muted" />
                Identity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {identity ? (
                <div className="rounded-md border border-border-default bg-bg-elevated p-3 flex flex-col gap-1">
                  <div className="text-sm text-text-primary">
                    {identity.identifier}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        identity.status === "active"
                          ? "success"
                          : identity.status === "expired"
                            ? "warning"
                            : "error"
                      }
                    >
                      {identity.status.replace("_", " ")}
                    </Badge>
                    <span className="text-[11px] text-text-muted">
                      {identity.credentialType}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-text-muted">No identity bound.</p>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>

      <Dialog
        open={provideResource !== null}
        onOpenChange={(open) => !open && setProvideResource(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Provide Resource</DialogTitle>
            <DialogDescription>
              Resource required: <strong>{provideResource}</strong>. Supply the
              credential or value in the Accounts section, then resume this task.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
