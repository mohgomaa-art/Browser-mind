import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, Diamond, GitBranch, Play, Square } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";
import type { StepKind, WorkflowStep } from "@/types";

const KIND_ICON: Record<StepKind, typeof Play> = {
  start: Play,
  step: Square,
  branch: GitBranch,
  condition: Diamond,
  end: Check,
};

function flatten(steps: WorkflowStep[]): WorkflowStep[] {
  const out: WorkflowStep[] = [];
  for (const s of steps) {
    out.push(s);
    if (s.children?.length) out.push(...flatten(s.children));
  }
  return out;
}

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => adapter.workflows.byId(id!),
    enabled: !!id,
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) {
    return (
      <div>
        <h1 className="text-lg font-semibold">Workflow not found</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate("/dev/workflows")}>
          ← Back
        </Button>
      </div>
    );
  }

  const flat = flatten(data.steps);
  const counts = flat.reduce<Record<StepKind, number>>(
    (acc, s) => {
      acc[s.kind] = (acc[s.kind] ?? 0) + 1;
      return acc;
    },
    { start: 0, step: 0, branch: 0, condition: 0, end: 0 },
  );
  const breakdown = (Object.entries(counts) as [StepKind, number][])
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${k}`)
    .join(" • ");
  const selected = flat.find((s) => s.seq === selectedSeq);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Tag variant="neutral">v{data.version}</Tag>
            <Tag variant="neutral">{data.environmentKey ?? "—"}</Tag>
          </div>
          <h1 className="text-lg font-semibold tracking-tight">{data.name}</h1>
          <p className="text-xs text-text-muted">{data.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost">Inspect</Button>
          <Button size="sm" variant="ghost">Diff</Button>
          <Button size="sm" variant="ghost">Versions</Button>
        </div>
      </header>

      <div className="text-xs text-text-muted">{breakdown}</div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Graph</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center gap-1.5 max-w-md mx-auto py-4">
              {flat.map((s, i) => {
                const Icon = KIND_ICON[s.kind];
                const active = s.seq === selectedSeq;
                return (
                  <div key={s.seq} className="w-full flex flex-col items-center gap-1.5">
                    <button
                      onClick={() => setSelectedSeq(s.seq)}
                      className={
                        "w-full inline-flex items-center gap-2 px-3 h-9 rounded-md border text-left text-sm transition-colors " +
                        (active
                          ? "border-accent bg-accent/10"
                          : "border-border-default bg-bg-panel hover:border-border-strong")
                      }
                    >
                      <span className="text-text-subtle font-mono text-[11px] w-6 text-right">
                        {s.seq}
                      </span>
                      <Icon className="h-3.5 w-3.5 text-text-muted" />
                      <span className="flex-1 truncate">
                        {s.semanticName ?? s.actionType ?? s.kind}
                      </span>
                      <span className="text-[11px] text-text-subtle">
                        {[s.actionType, s.targetRole].filter(Boolean).join(" / ")}
                      </span>
                    </button>
                    {i < flat.length - 1 && (
                      <span className="h-3 w-px bg-border-default" />
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>{selected ? `Step ${selected.seq}` : "Step Inspector"}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-3">
            {selected ? (
              <>
                <Row label="Kind" value={<Tag variant="neutral">{selected.kind}</Tag>} />
                <Row label="Semantic Name" value={selected.semanticName ?? "—"} />
                <Row label="Action Type" value={<Tag variant="neutral">{selected.actionType ?? "—"}</Tag>} />
                <Row label="Target Role" value={<Tag variant="neutral">{selected.targetRole ?? "—"}</Tag>} />
                <Row label="Target Name" value={selected.targetName ?? "—"} />
                <Row
                  label="Selector"
                  value={
                    <span className="font-mono text-xs text-text-muted break-all">
                      {selected.targetSelector ?? "—"}
                    </span>
                  }
                />
              </>
            ) : (
              <span className="text-xs text-text-subtle">
                Click a step to inspect.
              </span>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="text-[11px] text-text-subtle">
        Updated {formatRelative(data.updatedAt)} • Created {formatRelative(data.createdAt)} • <span className="font-mono">{data.id}</span>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-24 text-[11px] uppercase tracking-wider text-text-subtle pt-0.5">
        {label}
      </div>
      <div className="text-sm flex-1 min-w-0">{value}</div>
    </div>
  );
}
