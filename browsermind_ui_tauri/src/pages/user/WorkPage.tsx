import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Search,
  Play,
  RefreshCcw,
  Eye,
  Inbox,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { cn } from "@/lib/cn";
import { useTasks } from "@/lib/queries";
import { useInspectorStore } from "@/stores";
import type { Task, TaskState } from "@/types";

type Filter = "all" | "active" | "completed";

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

function isActive(state: TaskState): boolean {
  return state !== "completed" && state !== "failed";
}

function TaskCard({ task }: { task: Task }) {
  const navigate = useNavigate();
  const setSelected = useInspectorStore((s) => s.setSelected);
  const setOpen = useInspectorStore((s) => s.setOpen);

  const handleInspect = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected({ type: "task", id: task.id });
    setOpen(true);
  };

  const showResume = task.state === "paused" || task.state === "waiting";
  const showRetry = task.state === "failed";

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/work/${task.id}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter") navigate(`/work/${task.id}`);
      }}
      className="hover:border-border-strong transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div className="p-4 flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <Badge variant={stateVariant(task.state)}>
            {STATE_LABEL[task.state]}
          </Badge>
          <div className="text-base font-medium text-text-primary truncate">
            {task.goal}
          </div>
          {task.environmentKey ? (
            <Badge variant="neutral">{task.environmentKey}</Badge>
          ) : null}
          <div className="ml-auto flex items-center gap-1">
            {showResume ? (
              <Button
                size="sm"
                variant="default"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/work/${task.id}`);
                }}
              >
                <Play className="h-3.5 w-3.5" />
                Resume
              </Button>
            ) : null}
            {showRetry ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/work/${task.id}`);
                }}
              >
                <RefreshCcw className="h-3.5 w-3.5" />
                Retry
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={handleInspect}>
              <Eye className="h-3.5 w-3.5" />
              Inspect
            </Button>
          </div>
        </div>
        <div className="text-xs text-text-muted flex flex-wrap items-center gap-x-3">
          <span>
            Progress {task.progress.current}/{task.progress.total}
          </span>
          {task.missingResources.length > 0 ? (
            <span className="text-state-warning">
              Missing: {task.missingResources.join(", ")}
            </span>
          ) : null}
          {task.nextAction ? <span>Next: {task.nextAction}</span> : null}
        </div>
      </div>
    </Card>
  );
}

export default function WorkPage() {
  const tasksQuery = useTasks();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo<Task[]>(() => {
    const all = tasksQuery.data ?? [];
    const lowered = query.trim().toLowerCase();
    return all
      .filter((t) => {
        if (filter === "active") return isActive(t.state);
        if (filter === "completed") return t.state === "completed";
        return true;
      })
      .filter((t) =>
        lowered.length === 0 ? true : t.goal.toLowerCase().includes(lowered),
      );
  }, [tasksQuery.data, filter, query]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Work</h1>
          <p className="text-xs text-text-muted">
            Tasks across all your accounts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex items-center rounded-md border border-border-default bg-bg-panel p-0.5">
            {(["all", "active", "completed"] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "px-2.5 h-7 rounded text-xs font-medium capitalize transition-colors",
                  filter === f
                    ? "bg-bg-elevated text-text-primary"
                    : "text-text-muted hover:text-text-primary",
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="relative w-64">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-subtle" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tasks…"
              className="pl-8 h-8"
            />
          </div>
        </div>
      </header>

      {tasksQuery.isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
      ) : tasksQuery.isError ? (
        <Card>
          <div className="p-4 flex items-center gap-3">
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
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <div className="p-10 flex flex-col items-center gap-3">
            <Inbox className="h-6 w-6 text-text-subtle" />
            <p className="text-sm text-text-muted">No tasks match.</p>
            <Link
              to="/"
              className="text-xs text-accent hover:underline underline-offset-4"
            >
              Start a new task from Home
            </Link>
          </div>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </div>
      )}
    </div>
  );
}
