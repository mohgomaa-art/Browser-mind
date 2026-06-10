import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  Input,
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
import { useEnvironments, useTasks } from "@/lib/queries";
import { formatRelative, truncate } from "@/lib/utils";
import type { Task, TaskState } from "@/types";

const TASK_STATES: TaskState[] = [
  "created",
  "running",
  "paused",
  "waiting",
  "blocked",
  "failed",
  "completed",
];
const STATE_VARIANT: Record<
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

type ViewMode = "list" | "kanban" | "timeline";

export default function TasksPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<ViewMode>("list");
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [envFilter, setEnvFilter] = useState<string>("all");

  const tasksQ = useTasks();
  const envsQ = useEnvironments();

  const filtered = useMemo(() => {
    return (tasksQ.data ?? []).filter((t) => {
      if (search && !t.goal.toLowerCase().includes(search.toLowerCase()))
        return false;
      if (stateFilter !== "all" && t.state !== stateFilter) return false;
      if (envFilter !== "all" && t.environmentKey !== envFilter) return false;
      return true;
    });
  }, [tasksQ.data, search, stateFilter, envFilter]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Tasks</h1>
          <p className="text-xs text-text-muted">
            Goals broken down across personas and environments.
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-3.5 w-3.5 mr-1" />
          New Task
        </Button>
      </header>

      <div className="flex items-center gap-2">
        <Input
          placeholder="Search goals…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            {TASK_STATES.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={envFilter} onValueChange={setEnvFilter}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All envs</SelectItem>
            {(envsQ.data ?? []).map((e) => (
              <SelectItem key={e.key} value={e.key}>{e.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="ml-auto inline-flex rounded-md border border-border-default p-0.5">
          {(["list", "kanban", "timeline"] as ViewMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={
                "px-2.5 h-7 text-[11px] uppercase tracking-wider rounded-sm " +
                (view === v
                  ? "bg-bg-elevated text-text-primary"
                  : "text-text-subtle hover:text-text-primary")
              }
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {tasksQ.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : view === "list" ? (
        <ListView tasks={filtered} onClick={(id) => navigate(`/dev/tasks/${id}`)} />
      ) : view === "kanban" ? (
        <KanbanView tasks={filtered} onClick={(id) => navigate(`/dev/tasks/${id}`)} />
      ) : (
        <TimelineView tasks={filtered} onClick={(id) => navigate(`/dev/tasks/${id}`)} />
      )}
    </div>
  );
}

function ListView({ tasks, onClick }: { tasks: Task[]; onClick: (id: string) => void }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Goal</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Env</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>Missing</TableHead>
            <TableHead>Next Action</TableHead>
            <TableHead>Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tasks.map((t) => {
            const pct =
              t.progress.total > 0
                ? Math.round((t.progress.current / t.progress.total) * 100)
                : 0;
            return (
              <TableRow
                key={t.id}
                className="cursor-pointer"
                onClick={() => onClick(t.id)}
              >
                <TableCell className="font-medium max-w-xs truncate">
                  {t.goal}
                </TableCell>
                <TableCell>
                  <Tag variant={STATE_VARIANT[t.state]}>{t.state}</Tag>
                </TableCell>
                <TableCell>
                  <Tag variant="neutral">{t.environmentKey ?? "—"}</Tag>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1 min-w-[80px]">
                    <span className="text-[11px] text-text-muted tabular-nums">
                      {t.progress.current}/{t.progress.total}
                    </span>
                    <div className="h-1 rounded-full bg-bg-elevated overflow-hidden">
                      <div
                        className="h-full bg-accent"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-xs text-text-muted">
                  {t.missingResources.length}
                </TableCell>
                <TableCell className="text-xs text-text-muted">
                  {truncate(t.nextAction ?? "—", 40)}
                </TableCell>
                <TableCell className="text-xs text-text-subtle">
                  {formatRelative(t.updatedAt)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function KanbanView({ tasks, onClick }: { tasks: Task[]; onClick: (id: string) => void }) {
  const grouped: Record<TaskState, Task[]> = {
    created: [], running: [], paused: [], waiting: [],
    blocked: [], failed: [], completed: [],
  };
  for (const t of tasks) grouped[t.state].push(t);
  return (
    <div className="grid grid-cols-7 gap-3">
      {TASK_STATES.map((state) => (
        <div
          key={state}
          className="rounded-lg border border-border-default bg-bg-panel overflow-hidden flex flex-col min-h-[300px]"
        >
          <div className="flex items-center justify-between px-3 h-9 border-b border-border-default">
            <span className="text-[11px] uppercase tracking-wider text-text-muted">
              {state}
            </span>
            <span className="text-[11px] text-text-subtle tabular-nums">
              {grouped[state].length}
            </span>
          </div>
          <div className="flex-1 p-2 flex flex-col gap-2 overflow-auto">
            {grouped[state].map((t) => {
              const pct = t.progress.total > 0
                ? Math.round((t.progress.current / t.progress.total) * 100)
                : 0;
              return (
                <Card
                  key={t.id}
                  className="cursor-pointer hover:border-border-strong"
                  onClick={() => onClick(t.id)}
                >
                  <CardContent className="p-3 flex flex-col gap-2">
                    <div className="text-xs font-medium leading-tight">
                      {truncate(t.goal, 60)}
                    </div>
                    <div className="flex items-center justify-between">
                      <Tag variant="neutral">{t.environmentKey ?? "—"}</Tag>
                      <span className="text-[11px] text-text-subtle tabular-nums">
                        {pct}%
                      </span>
                    </div>
                    <div className="h-1 rounded-full bg-bg-elevated overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function TimelineView({ tasks, onClick }: { tasks: Task[]; onClick: (id: string) => void }) {
  const sorted = [...tasks].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
  return (
    <div className="rounded-lg border border-border-default bg-bg-panel">
      <ul>
        {sorted.map((t) => (
          <li
            key={t.id}
            onClick={() => onClick(t.id)}
            className="flex items-center gap-4 px-4 py-2 border-b border-border-default last:border-b-0 hover:bg-bg-elevated cursor-pointer"
          >
            <span className="font-mono text-[11px] text-text-subtle w-24 shrink-0">
              {formatRelative(t.updatedAt)}
            </span>
            <Tag variant={STATE_VARIANT[t.state]}>{t.state}</Tag>
            <span className="flex-1 truncate text-sm">{t.goal}</span>
            <Tag variant="neutral">{t.environmentKey ?? "—"}</Tag>
          </li>
        ))}
      </ul>
    </div>
  );
}
