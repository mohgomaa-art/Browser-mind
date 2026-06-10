import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { useExecution } from "@/lib/queries";
import { formatRelative } from "@/lib/utils";
import type { ExecutionState, Snapshot } from "@/types";

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

const KIND_COLOR: Record<string, string> = {
  navigate: "bg-accent",
  click: "bg-text-primary",
  fill: "bg-accent",
  extract: "bg-text-muted",
  verify: "bg-state-success",
  pause: "bg-state-warning",
  resume: "bg-state-success",
  fail: "bg-state-error",
  snapshot: "bg-text-muted",
};

function duration(start: string, end?: string): string {
  if (!end) return "in progress";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function ExecutionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [actionPending, setActionPending] = useState<string | null>(null);
  const { data, isLoading } = useExecution(id);

  async function act(action: "pause" | "resume" | "retry" | "cancel") {
    if (!id || actionPending) return;
    setActionPending(action);
    try {
      await adapter.executions.act(id, action);
      await queryClient.invalidateQueries({ queryKey: ["execution", id] });
      await queryClient.invalidateQueries({ queryKey: ["executions"] });
    } finally {
      setActionPending(null);
    }
  }

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (!data) {
    return (
      <div>
        <h1 className="text-lg font-semibold">Execution not found</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate("/dev/executions")}>
          ← Back
        </Button>
      </div>
    );
  }

  const totalSteps = Math.max(data.currentStepSeq ?? 0, 8);
  const stepNumbers = Array.from({ length: totalSteps }, (_, i) => i + 1);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Tag variant={EXEC_VARIANT[data.state]}>{data.state}</Tag>
            <span className="text-[11px] text-text-subtle font-mono">{data.id}</span>
          </div>
          <h1 className="text-lg font-semibold tracking-tight">
            Execution — {duration(data.startedAt, data.endedAt)}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {data.state === "running" && (
            <Button
              size="sm"
              variant="secondary"
              disabled={!!actionPending}
              onClick={() => act("pause")}
            >
              {actionPending === "pause" ? "Pausing…" : "Pause"}
            </Button>
          )}
          {(data.state === "paused" || data.state === "waiting") && (
            <Button
              size="sm"
              disabled={!!actionPending}
              onClick={() => act("resume")}
            >
              {actionPending === "resume" ? "Resuming…" : "Resume"}
            </Button>
          )}
          {data.state === "failed" && (
            <Button
              size="sm"
              disabled={!!actionPending}
              onClick={() => act("retry")}
            >
              {actionPending === "retry" ? "Retrying…" : "Retry"}
            </Button>
          )}
          {(data.state === "running" || data.state === "paused" || data.state === "waiting") && (
            <Button
              size="sm"
              variant="destructive"
              disabled={!!actionPending}
              onClick={() => act("cancel")}
            >
              {actionPending === "cancel" ? "Cancelling…" : "Cancel"}
            </Button>
          )}
        </div>
      </header>

      {data.state === "failed" && (
        <div className="rounded-md border border-state-error/40 bg-state-error/10 px-3 py-2 text-xs text-state-error flex items-start gap-2">
          <span className="font-semibold">Execution failed.</span>
          <span className="text-state-error/80">
            {[...data.events].reverse().find((e) => !!e.detail)?.detail ??
              "Check the Events tab for failure details."}
          </span>
        </div>
      )}

      <div className="grid grid-cols-6 gap-3">
        <Metric label="State" value={<Tag variant={EXEC_VARIANT[data.state]}>{data.state}</Tag>} />
        <Metric label="Started" value={formatRelative(data.startedAt)} />
        <Metric label="Ended" value={data.endedAt ? formatRelative(data.endedAt) : "—"} />
        <Metric label="Retries" value={data.retryCount} />
        <Metric label="Snapshots" value={data.snapshots.length} />
        <Metric label="Checkpoints" value={data.checkpoints.length} />
      </div>

      <Tabs defaultValue="graph">
        <TabsList>
          <TabsTrigger value="graph">Graph</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
          <TabsTrigger value="checkpoints">Checkpoints</TabsTrigger>
          <TabsTrigger value="recovery">Recovery</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="meta">Metadata</TabsTrigger>
        </TabsList>

        <TabsContent value="graph" className="mt-4">
          <Card>
            <CardContent className="p-4 overflow-x-auto">
              <div className="flex items-center gap-1 min-w-max">
                <Pill label="Start" />
                <Arrow />
                {stepNumbers.map((n) => (
                  <span key={n} className="flex items-center">
                    <Pill
                      label={`Step ${n}`}
                      active={data.currentStepSeq === n}
                    />
                    {n < stepNumbers.length && <Arrow />}
                  </span>
                ))}
                <Arrow />
                <Pill label={data.state === "completed" ? "End" : "Current"} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <Card>
            <CardContent className="p-4">
              <ul className="space-y-2">
                {data.events.map((e) => (
                  <li key={e.id} className="flex items-start gap-3 text-xs">
                    <span className="font-mono text-text-subtle w-12 shrink-0 pt-0.5">
                      {hhmm(e.timestamp)}
                    </span>
                    <span
                      className={
                        "h-1.5 w-1.5 rounded-full mt-1.5 shrink-0 " +
                        (KIND_COLOR[e.kind] ?? "bg-text-muted")
                      }
                    />
                    <div className="flex-1">
                      <div className="text-sm">{e.summary}</div>
                      {e.detail && (
                        <div className="text-xs text-text-muted mt-0.5">{e.detail}</div>
                      )}
                    </div>
                    <Tag variant="neutral">{e.kind}</Tag>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="snapshots" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Seq</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Timestamp</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.snapshots.map((s) => (
                    <TableRow key={s.id} className="cursor-pointer" onClick={() => setSnap(s)}>
                      <TableCell className="font-mono text-xs">{s.id}</TableCell>
                      <TableCell className="tabular-nums">{s.sequence}</TableCell>
                      <TableCell><Tag variant="neutral">{s.kind}</Tag></TableCell>
                      <TableCell className="text-xs text-text-muted">
                        {formatRelative(s.timestamp)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="checkpoints" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Label</TableHead>
                    <TableHead>Sequence</TableHead>
                    <TableHead>Timestamp</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.checkpoints.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-mono text-xs">{c.id}</TableCell>
                      <TableCell>{c.label}</TableCell>
                      <TableCell className="tabular-nums">{c.sequence}</TableCell>
                      <TableCell className="text-xs text-text-muted">
                        {formatRelative(c.timestamp)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="recovery" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Outcome</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.recoveryHistory.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="text-xs text-text-muted">
                        {formatRelative(r.timestamp)}
                      </TableCell>
                      <TableCell>{r.reason}</TableCell>
                      <TableCell>
                        <Tag variant={r.outcome === "recovered" ? "active" : "error"}>
                          {r.outcome}
                        </Tag>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="events" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Summary</TableHead>
                    <TableHead>Resolver</TableHead>
                    <TableHead>Detail</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.events.map((e) => (
                    <TableRow key={e.id}>
                      <TableCell className="font-mono text-xs text-text-muted">
                        {hhmm(e.timestamp)}
                      </TableCell>
                      <TableCell><Tag variant="neutral">{e.kind}</Tag></TableCell>
                      <TableCell className="text-xs">{e.summary}</TableCell>
                      <TableCell className="text-xs text-text-muted font-mono">
                        {e.resolverStrategy ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs text-text-muted">{e.detail ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="meta" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <pre className="font-mono text-xs bg-bg-elevated p-3 overflow-auto rounded-md max-h-[480px]">
                {JSON.stringify(data, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Sheet open={!!snap} onOpenChange={(o) => !o && setSnap(null)}>
        <SheetContent side="right" className="w-[420px]">
          {snap && (
            <>
              <SheetHeader>
                <SheetTitle>Snapshot {snap.id}</SheetTitle>
              </SheetHeader>
              <div className="mt-4 space-y-3 text-sm">
                {snap.evidenceUri &&
                /\.(png|jpg|jpeg|webp|gif)$/i.test(snap.evidenceUri) ? (
                  <img
                    src={snap.evidenceUri}
                    alt={`Snapshot ${snap.sequence}`}
                    className="w-full rounded-md border border-border-default object-contain max-h-72 bg-bg-elevated"
                  />
                ) : snap.evidenceUri ? (
                  <div className="rounded-md bg-bg-elevated border border-border-default p-2">
                    <a
                      href={snap.evidenceUri}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-[11px] text-accent break-all hover:underline"
                    >
                      {snap.evidenceUri}
                    </a>
                  </div>
                ) : (
                  <div className="h-20 rounded-md bg-bg-elevated border border-border-default flex items-center justify-center text-xs text-text-subtle">
                    No evidence captured
                  </div>
                )}
                <Row label="Sequence" value={String(snap.sequence)} />
                <Row label="Kind" value={<Tag variant="neutral">{snap.kind}</Tag>} />
                <Row label="Timestamp" value={formatRelative(snap.timestamp)} />
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="p-3 flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle">
          {label}
        </div>
        <div className="text-sm">{value}</div>
      </CardContent>
    </Card>
  );
}

function Pill({ label, active }: { label: string; active?: boolean }) {
  return (
    <span
      className={
        "inline-flex items-center justify-center h-7 px-3 rounded-md border text-xs whitespace-nowrap " +
        (active
          ? "border-accent bg-accent/15 text-text-primary"
          : "border-border-default bg-bg-panel text-text-muted")
      }
    >
      {label}
    </span>
  );
}

function Arrow() {
  return <span className="text-text-subtle px-1">→</span>;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-32 text-[11px] uppercase tracking-wider text-text-subtle">
        {label}
      </div>
      <div className="text-sm">{value}</div>
    </div>
  );
}
