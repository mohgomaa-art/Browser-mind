import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Plus,
  Globe2,
  Workflow,
  Clock3,
  Activity,
  AlertCircle,
  Loader2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";

import { formatRelative } from "@/lib/utils";
import { adapter } from "@/lib/adapters";
import {
  useTasks,
  useEnvironments,
} from "@/lib/queries";
import { usePersonaStore } from "@/stores";
import type { LedgerEvent, Task, TaskState, WorkflowTemplate } from "@/types";
import { useQuery } from "@tanstack/react-query";

function greeting(hour: number): string {
  if (hour < 5) return "Good Evening";
  if (hour < 12) return "Good Morning";
  if (hour < 18) return "Good Afternoon";
  return "Good Evening";
}

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
      return "warning" as const;
    case "waiting":
      return "warning" as const;
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

function subtextForTask(task: Task): string {
  if (task.state === "paused")
    return `Paused ${formatRelative(task.updatedAt)}`;
  if (task.state === "waiting")
    return task.nextAction
      ? `Waiting — ${task.nextAction}`
      : "Waiting for input";
  if (task.state === "running")
    return task.nextAction ? `Running — ${task.nextAction}` : "Running";
  return formatRelative(task.updatedAt);
}

function ContinueCard({ task }: { task: Task }) {
  const pct =
    task.progress.total > 0
      ? Math.round((task.progress.current / task.progress.total) * 100)
      : 0;
  return (
    <Link
      to={`/work/${task.id}`}
      className="group block rounded-lg border border-border-default bg-bg-panel hover:border-border-strong transition-colors"
    >
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <Badge variant={stateVariant(task.state)}>
            {STATE_LABEL[task.state]}
          </Badge>
          <ArrowRight className="h-3.5 w-3.5 text-text-subtle opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <div>
          <div className="text-sm font-medium text-text-primary line-clamp-2">
            {task.goal}
          </div>
          <div className="text-xs text-text-muted mt-1">
            {subtextForTask(task)}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <div className="h-1 rounded-full bg-bg-elevated overflow-hidden">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-[11px] text-text-subtle">
            {task.progress.current}/{task.progress.total} steps
          </div>
        </div>
      </div>
    </Link>
  );
}

function ActivityRow({ event }: { event: LedgerEvent }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-accent shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-sm text-text-primary truncate">
          {event.summary}
        </div>
        <div className="text-[11px] text-text-muted">
          {formatRelative(event.timestamp)}
        </div>
      </div>
      <Badge variant="neutral" className="shrink-0">
        {event.entityType}
      </Badge>
    </div>
  );
}

export default function HomePage() {
  const personaId = usePersonaStore((s) => s.currentPersonaId);
  const tasksQuery = useTasks();
  const envQuery = useEnvironments();
  const navigate = useNavigate();

  const activityQuery = useQuery({
    queryKey: ["ledger", "execution"],
    queryFn: () => adapter.ledger.list({ kind: "execution" }),
  });

  const workflowsQuery = useQuery<WorkflowTemplate[]>({
    queryKey: ["workflows"],
    queryFn: () => adapter.workflows.list(),
  });

  // New Task dialog state
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newTaskTemplate, setNewTaskTemplate] = useState("");
  const [newTaskEnv, setNewTaskEnv] = useState("");
  const [newTaskHeadless, setNewTaskHeadless] = useState(true);
  const [newTaskPending, setNewTaskPending] = useState(false);

  const continueTasks = useMemo<Task[]>(() => {
    const all = tasksQuery.data ?? [];
    return all
      .filter((t) =>
        t.state === "paused" || t.state === "waiting" || t.state === "running",
      )
      .sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      )
      .slice(0, 6);
  }, [tasksQuery.data]);

  const openTaskCount = useMemo(
    () =>
      (tasksQuery.data ?? []).filter(
        (t) => t.state !== "completed" && t.state !== "failed",
      ).length,
    [tasksQuery.data],
  );

  const personaName = personaId ? "Mohamed" : "Mohamed";
  const hour = new Date().getHours();

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          {greeting(hour)}, {personaName}
        </h1>
        <p className="text-sm text-text-muted">
          You have {openTaskCount} open task{openTaskCount === 1 ? "" : "s"}{" "}
          across {envQuery.data?.length ?? 0} account
          {envQuery.data?.length === 1 ? "" : "s"}.
        </p>
      </header>

      <section className="flex flex-col gap-3">
        <div className="flex items-end justify-between">
          <h2 className="text-sm font-semibold text-text-primary">
            Continue Previous Work
          </h2>
          <Link
            to="/work"
            className="text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            View all
          </Link>
        </div>
        {tasksQuery.isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-lg" />
            ))}
          </div>
        ) : tasksQuery.isError ? (
          <div className="rounded-lg border border-border-default bg-bg-panel p-4 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load tasks.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => tasksQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        ) : continueTasks.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-default bg-bg-panel p-8 flex flex-col items-center gap-2">
            <Clock3 className="h-5 w-5 text-text-subtle" />
            <p className="text-sm text-text-muted">
              Nothing in flight. Start something new below.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {continueTasks.map((task) => (
              <ContinueCard key={task.id} task={task} />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-text-primary">
          Quick Actions
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => setNewTaskOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            New Task
          </Button>
          <Button
            variant="secondary"
            onClick={() => navigate("/accounts")}
          >
            <Globe2 className="h-3.5 w-3.5" />
            Open Environment
          </Button>
          <Button
            variant="secondary"
            onClick={() => navigate("/work")}
          >
            <Workflow className="h-3.5 w-3.5" />
            Resume Workflow
          </Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-text-primary">
          Recent Activity
        </h2>
        <Card>
          <CardContent className="p-2">
            {activityQuery.isLoading ? (
              <div className="flex flex-col gap-2 p-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 rounded-md" />
                ))}
              </div>
            ) : activityQuery.isError ? (
              <div className="p-4 flex items-center gap-3">
                <AlertCircle className="h-4 w-4 text-state-error" />
                <span className="text-sm text-text-muted">
                  Couldn't load activity.
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => activityQuery.refetch()}
                >
                  Retry
                </Button>
              </div>
            ) : (activityQuery.data ?? []).length === 0 ? (
              <div className="p-6 flex flex-col items-center gap-2">
                <Activity className="h-5 w-5 text-text-subtle" />
                <p className="text-sm text-text-muted">No recent events.</p>
              </div>
            ) : (
              <div className="divide-y divide-border-default/60 px-2">
                {(activityQuery.data ?? []).slice(0, 8).map((event) => (
                  <ActivityRow key={event.id} event={event} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* New Task dialog */}
      <Dialog open={newTaskOpen} onOpenChange={(open) => { if (!newTaskPending) setNewTaskOpen(open); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Task</DialogTitle>
            <DialogDescription>
              Select a workflow and target environment to start a replay.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 pt-1">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Workflow</label>
              <Select value={newTaskTemplate} onValueChange={setNewTaskTemplate}>
                <SelectTrigger>
                  <SelectValue placeholder={workflowsQuery.isLoading ? "Loading…" : "Select workflow"} />
                </SelectTrigger>
                <SelectContent>
                  {(workflowsQuery.data ?? []).map((w) => (
                    <SelectItem key={w.id} value={w.name}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Environment</label>
              <Select value={newTaskEnv} onValueChange={setNewTaskEnv}>
                <SelectTrigger>
                  <SelectValue placeholder={envQuery.isLoading ? "Loading…" : "Select environment"} />
                </SelectTrigger>
                <SelectContent>
                  {(envQuery.data ?? []).map((e) => (
                    <SelectItem key={e.key} value={e.key}>
                      {e.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-text-muted">Headless</label>
              <Switch
                checked={newTaskHeadless}
                onCheckedChange={setNewTaskHeadless}
              />
            </div>
            <Button
              disabled={!newTaskTemplate || !newTaskEnv || newTaskPending}
              onClick={async () => {
                setNewTaskPending(true);
                try {
                  await adapter.replay.start(newTaskTemplate, newTaskEnv, "replay_agent", newTaskHeadless);
                  setNewTaskOpen(false);
                  setNewTaskTemplate("");
                  setNewTaskEnv("");
                  navigate("/dev/replays");
                } catch (_err) {
                  // keep dialog open on error
                } finally {
                  setNewTaskPending(false);
                }
              }}
            >
              {newTaskPending ? (
                <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Starting…</>
              ) : (
                "Start"
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
