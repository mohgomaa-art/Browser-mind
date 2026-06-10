import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
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
import { formatPercent } from "@/lib/utils";
import type { ReplayStatus, StepOutcome } from "@/types";

const STATUS_VARIANT: Record<ReplayStatus, "active" | "warning" | "error"> = {
  OK: "active",
  BLOCKED: "warning",
  FAIL: "error",
};

const OUTCOME_VARIANT: Record<
  StepOutcome["outcome"],
  "active" | "warning" | "error" | "neutral"
> = {
  RESOLVED_CORRECT: "active",
  RESOLVED_UNJUDGED: "neutral",
  RESOLVED_INCORRECT: "error",
  NO_VISIBLE_SIGNAL: "warning",
  ORPHANED_SEMANTIC_SIGNAL: "warning",
  TARGET_CHANGED: "warning",
  AMBIGUOUS_TARGET: "warning",
  AMBIGUOUS_IDENTITY: "warning",
  ENVIRONMENT_FAILURE: "error",
  SKIPPED: "neutral",
  UNKNOWN: "neutral",
};

export default function ReplayDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["replay", id],
    queryFn: () => adapter.replays.byId(id!),
    enabled: !!id,
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) {
    return (
      <div>
        <h1 className="text-lg font-semibold">Replay not found</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate("/dev/replays")}>
          ← Back
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Tag variant={STATUS_VARIANT[data.status]}>{data.status}</Tag>
            <span className="text-[11px] text-text-subtle font-mono">{data.id}</span>
          </div>
          <h1 className="text-lg font-semibold tracking-tight">
            Replay {data.id}
          </h1>
        </div>
      </header>

      <div className="grid grid-cols-6 gap-3">
        <Metric label="Resolution" value={formatPercent(data.resolutionRate)} />
        <Metric
          label="FPR"
          value={
            data.falsePositiveRate != null
              ? formatPercent(data.falsePositiveRate)
              : "—"
          }
        />
        <Metric
          label="Task Completion"
          value={
            data.taskCompletionRate != null
              ? formatPercent(data.taskCompletionRate)
              : "—"
          }
        />
        <Metric label="Total Steps" value={data.totalSteps} />
        <Metric label="Resolved" value={data.resolvedSteps} />
        <Metric label="Attempted" value={data.attemptedSteps} />
      </div>

      <Tabs defaultValue="outcomes">
        <TabsList>
          <TabsTrigger value="outcomes">Step Outcomes</TabsTrigger>
          <TabsTrigger value="critical">Critical Path</TabsTrigger>
          <TabsTrigger value="failure">Failure</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
        </TabsList>

        <TabsContent value="outcomes" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">Seq</TableHead>
                    <TableHead>Outcome</TableHead>
                    <TableHead>Target Role</TableHead>
                    <TableHead>Target Name</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.stepOutcomes.map((s) => (
                    <TableRow key={s.seq}>
                      <TableCell className="tabular-nums">{s.seq}</TableCell>
                      <TableCell>
                        <Tag variant={OUTCOME_VARIANT[s.outcome]}>{s.outcome}</Tag>
                      </TableCell>
                      <TableCell className="text-xs text-text-muted">
                        {s.targetRole ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs text-text-muted">
                        {s.targetName ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="critical" className="mt-4">
          <Card>
            <CardContent className="p-4">
              {data.criticalPath.length === 0 ? (
                <span className="text-xs text-text-subtle">No critical path</span>
              ) : (
                <ol className="space-y-2 text-sm">
                  {data.criticalPath.map((seq, i) => {
                    const outcome = data.stepOutcomes.find(
                      (s) => String(s.seq) === seq,
                    );
                    return (
                      <li key={i} className="flex items-center gap-3">
                        <span className="font-mono text-xs text-text-subtle w-8 text-right">
                          {seq}
                        </span>
                        {outcome && (
                          <Tag variant={OUTCOME_VARIANT[outcome.outcome]}>
                            {outcome.outcome}
                          </Tag>
                        )}
                        <span className="text-text-muted text-xs truncate">
                          {outcome?.targetName ?? "—"}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="failure" className="mt-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              {data.failureCategory ? (
                <>
                  <Tag variant="error">{data.failureCategory}</Tag>
                  <pre className="font-mono text-xs bg-bg-elevated p-3 rounded-md whitespace-pre-wrap">
                    {data.failureReason ?? "(no reason recorded)"}
                  </pre>
                </>
              ) : (
                <span className="text-xs text-text-subtle">No failure recorded.</span>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="json" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <pre className="font-mono text-xs bg-bg-elevated p-3 rounded-md max-h-[480px] overflow-auto">
                {JSON.stringify(data, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="p-3 flex flex-col gap-1">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle">
          {label}
        </div>
        <div className="text-base font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
