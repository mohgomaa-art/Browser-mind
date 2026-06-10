import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Progress,
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
import { useExecutions, useTask } from "@/lib/queries";
import { formatRelative } from "@/lib/utils";
import type { ExecutionState, TaskState } from "@/types";

const TASK_VARIANT: Record<
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

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const taskQ = useTask(id);
  const execsQ = useExecutions({ taskId: id });
  const personasQ = useQuery({
    queryKey: ["personas"],
    queryFn: () => adapter.personas.list(),
    enabled: !!taskQ.data,
  });

  if (taskQ.isLoading) return <Skeleton className="h-32 w-full" />;
  const task = taskQ.data;
  if (!task) {
    return (
      <div>
        <h1 className="text-lg font-semibold">Task not found</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate("/dev/tasks")}>
          ← Back
        </Button>
      </div>
    );
  }

  const persona = personasQ.data?.find((p) => p.id === task.personaId);
  const pct =
    task.progress.total > 0
      ? Math.round((task.progress.current / task.progress.total) * 100)
      : 0;
  const recentExecs = (execsQ.data ?? [])
    .slice()
    .sort(
      (a, b) =>
        new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    )
    .slice(0, 5);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Tag variant={TASK_VARIANT[task.state]}>{task.state}</Tag>
            <Tag variant="neutral">{task.environmentKey ?? "—"}</Tag>
          </div>
          <h1 className="text-lg font-semibold tracking-tight">{task.goal}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary">Pause</Button>
          <Button size="sm">Resume</Button>
          <Button size="sm" variant="ghost">Retry</Button>
          <Button size="sm" variant="destructive">Cancel</Button>
        </div>
      </header>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 flex flex-col gap-4">
          <Card>
            <CardHeader><CardTitle>Goal</CardTitle></CardHeader>
            <CardContent className="text-sm">{task.goal}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Progress</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-muted">{task.progress.current} of {task.progress.total} steps</span>
                <span className="text-text-subtle tabular-nums">{pct}%</span>
              </div>
              <Progress value={pct} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Missing Resources</CardTitle></CardHeader>
            <CardContent>
              {task.missingResources.length === 0 ? (
                <span className="text-xs text-text-subtle">None</span>
              ) : (
                <ul className="space-y-1">
                  {task.missingResources.map((r) => (
                    <li
                      key={r}
                      className="flex items-center justify-between text-sm py-1 border-b border-border-default last:border-b-0"
                    >
                      <span>{r}</span>
                      <Button size="sm" variant="ghost">Provide</Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          {task.nextAction && (
            <Card>
              <CardHeader><CardTitle>Next Action</CardTitle></CardHeader>
              <CardContent>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-base">{task.nextAction}</span>
                  <Button size="sm">Resume</Button>
                </div>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader><CardTitle>Recent Executions</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Retries</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentExecs.map((e) => (
                    <TableRow
                      key={e.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/dev/executions/${e.id}`)}
                    >
                      <TableCell className="font-mono text-xs">{e.id}</TableCell>
                      <TableCell><Tag variant={EXEC_VARIANT[e.state]}>{e.state}</Tag></TableCell>
                      <TableCell className="text-text-muted text-xs">{formatRelative(e.startedAt)}</TableCell>
                      <TableCell className="tabular-nums">{e.retryCount}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <div className="col-span-1 flex flex-col gap-4">
          <Card>
            <CardHeader><CardTitle>Persona</CardTitle></CardHeader>
            <CardContent className="text-sm">
              {persona?.displayName ?? task.personaId}
              <div className="text-xs text-text-subtle font-mono mt-0.5">
                {task.personaId}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Timestamps</CardTitle></CardHeader>
            <CardContent className="text-xs text-text-muted space-y-1">
              <div>Created: {formatRelative(task.createdAt)}</div>
              <div>Updated: {formatRelative(task.updatedAt)}</div>
              {task.lastEventAt && <div>Last event: {formatRelative(task.lastEventAt)}</div>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>ID</CardTitle></CardHeader>
            <CardContent className="font-mono text-xs text-text-subtle break-all">
              {task.id}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
