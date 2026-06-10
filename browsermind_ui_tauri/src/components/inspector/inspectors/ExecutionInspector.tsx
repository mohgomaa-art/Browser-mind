import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Tag } from "@/components/ui";
import { formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { ExecutionState } from "@/types";

const STATE_VARIANT: Record<
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

function formatDuration(start: string, end?: string): string {
  if (!end) return "in progress";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m}m ${rs}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

function formatHHMM(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function ExecutionInspector({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["inspector", "execution", id],
    queryFn: () => adapter.executions.byId(id),
  });

  if (isLoading) return <LoadingRows />;
  if (!data) return <NotFound kind="Execution" />;

  const events = data.events.slice(-5).reverse();

  return (
    <div>
      <Section first label="ID">
        <span className="font-mono text-xs text-text-subtle break-all">
          {data.id}
        </span>
      </Section>
      <Section label="State">
        <Tag variant={STATE_VARIANT[data.state]}>{data.state}</Tag>
      </Section>
      <Section label="Started">
        <span className="text-text-muted text-xs">
          {formatRelative(data.startedAt)}
        </span>
      </Section>
      <Section label="Ended">
        <span className="text-text-muted text-xs">
          {data.endedAt ? formatRelative(data.endedAt) : "—"}
        </span>
      </Section>
      <Section label="Duration">
        <span className="text-text-muted text-xs">
          {formatDuration(data.startedAt, data.endedAt)}
        </span>
      </Section>
      <Section label="Retry Count">{data.retryCount}</Section>
      <Section label="Current Step">
        {data.currentStepSeq ?? "—"}
      </Section>
      <Section label="Snapshots">{data.snapshots.length}</Section>
      <Section label="Checkpoints">{data.checkpoints.length}</Section>
      <Section label="Recent Events">
        {events.length === 0 ? (
          <span className="text-text-subtle text-xs">No events</span>
        ) : (
          <ul className="space-y-1">
            {events.map((e) => (
              <li key={e.id} className="flex gap-2 text-xs">
                <span className="text-text-subtle font-mono">
                  {formatHHMM(e.timestamp)}
                </span>
                <span className="text-text-muted">{e.summary}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
