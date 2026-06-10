import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  CheckCircle2,
  FlaskConical,
  Info,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
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
import { SIDECAR_BASE } from "@/lib/adapters/tauri";
import { formatRelative, formatPercent } from "@/lib/utils";

interface ObjectiveScoreResult {
  [executionId: string]: {
    aggregate: number;
    transferability: number;
    workflow_depth: number;
    resource_acquisition_value: number;
    capability_rarity: number;
    success_outcome: number;
  };
}

export default function TrainingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [trainLoading, setTrainLoading] = useState(false);
  const [selfTrainLoading, setSelfTrainLoading] = useState(false);
  const [trainMsg, setTrainMsg] = useState<string | null>(null);
  const [selfTrainMsg, setSelfTrainMsg] = useState<string | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreData, setScoreData] = useState<ObjectiveScoreResult | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["training", "status"],
    queryFn: () => adapter.training.status(),
    refetchInterval: 5000,
  });

  async function handleTrain() {
    setTrainLoading(true);
    setTrainMsg(null);
    try {
      await adapter.training.startTrain();
      setTrainMsg("BC training job started.");
      void queryClient.invalidateQueries({ queryKey: ["training", "status"] });
    } catch (e) {
      setTrainMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTrainLoading(false);
    }
  }

  async function handleSelfTrain() {
    setSelfTrainLoading(true);
    setSelfTrainMsg(null);
    try {
      await adapter.training.startSelfTrain();
      setSelfTrainMsg("Self-train loop started.");
      void queryClient.invalidateQueries({ queryKey: ["training", "status"] });
    } catch (e) {
      setSelfTrainMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSelfTrainLoading(false);
    }
  }

  async function handleScoreExectuions() {
    setScoreLoading(true);
    setScoreError(null);
    try {
      const r = await fetch(`${SIDECAR_BASE}/api/objective/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ min_steps: 3 }),
      });
      if (!r.ok) throw new Error(`sidecar error: ${r.status}`);
      const json = await r.json();
      setScoreData((json.scores ?? json) as ObjectiveScoreResult);
    } catch (e) {
      setScoreError(e instanceof Error ? e.message : String(e));
    } finally {
      setScoreLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Training</h1>
        <p className="text-xs text-text-muted">
          Behavioral Cloning pipeline — dataset, model, and training controls
        </p>
      </header>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="text-[11px] uppercase tracking-wider text-text-subtle">
              Dataset
            </div>
            {isLoading ? (
              <Skeleton className="h-7 w-24 mt-1" />
            ) : (
              <>
                <div className="text-2xl font-semibold tabular-nums">
                  {data?.episodeCount ?? "—"}
                </div>
                <div className="text-[11px] text-text-subtle">
                  Training Episodes
                </div>
                <div className="text-[11px] text-text-subtle mt-0.5">
                  success_only=True filter applied
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="text-[11px] uppercase tracking-wider text-text-subtle">
              Checkpoint
            </div>
            {isLoading ? (
              <Skeleton className="h-7 w-24 mt-1" />
            ) : (
              <>
                <div className="flex items-center gap-2 mt-0.5">
                  {data?.checkpointLoaded ? (
                    <Tag variant="active">
                      <CheckCircle2 className="h-3 w-3" />
                      Loaded
                    </Tag>
                  ) : (
                    <Tag variant="error">
                      <XCircle className="h-3 w-3" />
                      Missing
                    </Tag>
                  )}
                </div>
                <div className="text-[11px] text-text-subtle mt-1">
                  Action Acc:{" "}
                  <span className="text-text-primary tabular-nums">
                    {data != null ? formatPercent(data.actionAcc) : "—"}
                  </span>
                </div>
                <div className="text-[11px] text-text-subtle">
                  Val Loss:{" "}
                  <span className="text-text-primary tabular-nums">
                    {data?.valLoss != null
                      ? data.valLoss.toFixed(4)
                      : "—"}
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Model details */}
      <Card>
        <CardHeader>
          <CardTitle>Model Details</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-48" />
            </div>
          ) : isError ? (
            <p className="text-xs text-state-error">
              Failed to load training status:{" "}
              {error instanceof Error ? error.message : "Unknown error"}
            </p>
          ) : (
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-xs">
              <dt className="text-text-subtle">Checkpoint path</dt>
              <dd className="font-mono text-text-primary truncate">
                {data?.checkpointPath || "—"}
              </dd>
              <dt className="text-text-subtle">Last trained</dt>
              <dd className="text-text-primary">
                {data?.lastTrainedAt
                  ? formatRelative(data.lastTrainedAt)
                  : "—"}
              </dd>
            </dl>
          )}
        </CardContent>
      </Card>

      {/* Action buttons */}
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              onClick={handleTrain}
              disabled={trainLoading || selfTrainLoading}
            >
              {trainLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Brain className="h-3.5 w-3.5" />
              )}
              Train BC Model
            </Button>
            {trainMsg && (
              <span className="text-xs text-text-muted">{trainMsg}</span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="secondary"
              onClick={handleSelfTrain}
              disabled={trainLoading || selfTrainLoading}
            >
              {selfTrainLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Self-Train Loop
            </Button>
            {selfTrainMsg && (
              <span className="text-xs text-text-muted">{selfTrainMsg}</span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate("/dev/benchmark")}
            >
              <FlaskConical className="h-3.5 w-3.5" />
              Run Benchmark
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Objective Score Explorer */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Objective Score Explorer</span>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleScoreExectuions}
              disabled={scoreLoading}
            >
              {scoreLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Score Executions
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {scoreError && (
            <p className="text-xs text-state-error mb-2">{scoreError}</p>
          )}
          {!scoreData && !scoreLoading && (
            <p className="text-xs text-text-muted">
              Click "Score Executions" to compute TaskValueScore for all corpus executions.
            </p>
          )}
          {scoreData && (
            <div className="rounded-lg border border-border-default overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Execution ID</TableHead>
                    <TableHead className="text-right">Aggregate</TableHead>
                    <TableHead className="text-right">Transfer</TableHead>
                    <TableHead className="text-right">Depth</TableHead>
                    <TableHead className="text-right">Resource</TableHead>
                    <TableHead className="text-right">Rarity</TableHead>
                    <TableHead className="text-right">Success</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(scoreData)
                    .sort(([, a], [, b]) => b.aggregate - a.aggregate)
                    .map(([execId, sc]) => (
                      <TableRow key={execId}>
                        <TableCell className="font-mono text-xs">{execId}</TableCell>
                        <TableCell className="text-right tabular-nums font-semibold">
                          {formatPercent(sc.aggregate)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-text-muted">
                          {formatPercent(sc.transferability)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-text-muted">
                          {formatPercent(sc.workflow_depth)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-text-muted">
                          {formatPercent(sc.resource_acquisition_value)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-text-muted">
                          {formatPercent(sc.capability_rarity)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-text-muted">
                          {formatPercent(sc.success_outcome)}
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info box */}
      <div className="flex items-start gap-2 rounded-md border border-border-default bg-bg-elevated px-3 py-2.5 text-xs text-text-muted">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-accent" />
        <span>
          Training runs in the background. Check the{" "}
          <button
            className="text-accent underline underline-offset-2 hover:no-underline"
            onClick={() => navigate("/dev/benchmark")}
          >
            Benchmark page
          </button>{" "}
          for results.
        </span>
      </div>
    </div>
  );
}
