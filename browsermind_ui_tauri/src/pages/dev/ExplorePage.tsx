import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Compass,
  Loader2,
  RefreshCw,
  Play,
  BookOpen,
  Sparkles,
} from "lucide-react";
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
import { formatRelative } from "@/lib/utils";
import type { ExploreRun } from "@/lib/adapters/tauri";

function statusVariant(
  status: ExploreRun["status"],
): "active" | "warning" | "error" | "neutral" {
  if (status === "complete") return "active";
  if (status === "running") return "warning";
  if (status === "error") return "error";
  return "neutral";
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: React.ElementType;
}) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-1">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-text-subtle">
          {Icon && <Icon size={12} />}
          {label}
        </div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="text-[11px] text-text-subtle">{hint}</div>}
      </CardContent>
    </Card>
  );
}

export default function ExplorePage() {
  const queryClient = useQueryClient();

  const [siteKey, setSiteKey] = useState("github");
  const [budget, setBudget] = useState(50);
  const [headless, setHeadless] = useState(false);
  const [personaName, setPersonaName] = useState("validator");
  const [launching, setLaunching] = useState(false);
  const [launchMsg, setLaunchMsg] = useState<string | null>(null);

  const { data: runs, isLoading: runsLoading, refetch, isFetching } = useQuery({
    queryKey: ["explore", "runs"],
    queryFn: () => adapter.explore.listRuns(),
    refetchInterval: 5000,
  });

  const { data: live } = useQuery({
    queryKey: ["explore", "live"],
    queryFn: () => adapter.explore.liveState(),
    refetchInterval: 1000,
  });

  const { data: ledger } = useQuery({
    queryKey: ["explore", "ledger"],
    queryFn: () => adapter.explore.ledgerStats(),
    refetchInterval: 10000,
  });

  const { data: vocab } = useQuery({
    queryKey: ["explore", "vocab"],
    queryFn: () => adapter.explore.vocabProposals(),
    refetchInterval: 10000,
  });

  async function handleLaunch() {
    setLaunching(true);
    setLaunchMsg(null);
    try {
      await adapter.explore.start(siteKey, budget, headless, personaName);
      setLaunchMsg("Exploration started.");
      void queryClient.invalidateQueries({ queryKey: ["explore"] });
    } catch (e) {
      setLaunchMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLaunching(false);
    }
  }

  const runList = runs ?? [];
  const isRunning = live?.status === "running";

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Explore</h1>
          <p className="text-xs text-text-muted">
            Discover capability hypotheses by exploring sites with ExplorationHarness
          </p>
        </div>
        <div className="flex items-center gap-2">
          {launchMsg && (
            <span className="text-xs text-text-muted max-w-xs truncate">
              {launchMsg}
            </span>
          )}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            {isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Refresh
          </Button>
        </div>
      </header>

      {/* Live status banner */}
      {isRunning && live && (
        <div className="flex items-center gap-3 rounded-lg border border-state-warning bg-state-warning/10 px-4 py-3">
          <Loader2 className="h-4 w-4 animate-spin text-state-warning shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium">
              Exploring <span className="font-mono">{live.siteKey}</span>
            </span>
            <span className="ml-3 text-xs text-text-muted">
              {live.stepsExecuted} steps &middot;{" "}
              {live.experiencesDiscovered.length} experiences discovered
            </span>
          </div>
          <Tag variant="warning">running</Tag>
        </div>
      )}

      {/* Launch form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Compass size={16} />
            Launch Exploration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-text-subtle">
                Site Key
              </label>
              <input
                type="text"
                value={siteKey}
                onChange={(e) => setSiteKey(e.target.value)}
                placeholder="e.g. github"
                className="h-8 rounded-md border border-border-default bg-bg-input px-3 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-text-subtle">
                Budget (steps)
              </label>
              <input
                type="number"
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                min={1}
                max={500}
                className="h-8 rounded-md border border-border-default bg-bg-input px-3 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-text-subtle">
                Persona
              </label>
              <input
                type="text"
                value={personaName}
                onChange={(e) => setPersonaName(e.target.value)}
                placeholder="validator"
                className="h-8 rounded-md border border-border-default bg-bg-input px-3 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-text-subtle">
                Options
              </label>
              <label className="flex h-8 items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={headless}
                  onChange={(e) => setHeadless(e.target.checked)}
                  className="accent-accent"
                />
                <span className="text-sm text-text-muted">Headless</span>
              </label>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button
              size="sm"
              onClick={handleLaunch}
              disabled={launching || isRunning || !siteKey}
            >
              {launching ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {launching ? "Starting…" : isRunning ? "Running…" : "Launch"}
            </Button>
            {isRunning && (
              <span className="text-xs text-text-subtle">
                Wait for the current run to complete before starting another.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Discovery stats */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total Runs"
          value={runsLoading ? "—" : runList.length}
          hint="all time"
          icon={Compass}
        />
        <StatCard
          label="Fallback Fragments"
          value={ledger?.uniqueFragments ?? "—"}
          hint={`${ledger?.totalObservations ?? 0} observations`}
          icon={BookOpen}
        />
        <StatCard
          label="Multi-site Fragments"
          value={ledger?.multiSiteFragments ?? "—"}
          hint="seen on 2+ sites"
        />
        <StatCard
          label="Vocab Proposals"
          value={vocab?.total ?? "—"}
          hint={`${(vocab?.byStatus as Record<string, number> | undefined)?.["PROPOSED"] ?? 0} pending review`}
          icon={Sparkles}
        />
      </div>

      {/* Top fallback fragments */}
      {ledger && ledger.topFragments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen size={15} />
              Top Fallback Fragments
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="rounded-b-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Fragment</TableHead>
                    <TableHead className="text-right">Freq</TableHead>
                    <TableHead className="text-right">Sites</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledger.topFragments.map((f: { fragment: string; freq: number; sites: number }) => (
                    <TableRow key={f.fragment}>
                      <TableCell className="font-mono text-xs">
                        {f.fragment}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {f.freq}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {f.sites}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run history */}
      <Card>
        <CardHeader>
          <CardTitle>Run History</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="rounded-b-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Site</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Steps</TableHead>
                  <TableHead>Experiences</TableHead>
                  <TableHead className="text-right">Hypotheses</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead>Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runsLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={7}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : runList.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="py-12 text-center text-xs text-text-subtle"
                    >
                      No runs yet. Launch an exploration above.
                    </TableCell>
                  </TableRow>
                ) : (
                  runList.map((run: ExploreRun) => (
                    <TableRow key={run.runId}>
                      <TableCell className="font-mono text-xs font-medium">
                        {run.siteKey}
                      </TableCell>
                      <TableCell>
                        <Tag variant={statusVariant(run.status)}>
                          {run.status}
                        </Tag>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {run.stepsExecuted}
                      </TableCell>
                      <TableCell className="text-xs text-text-muted max-w-[200px] truncate">
                        {run.experiencesDiscovered.join(", ") || "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {run.hypothesisCount}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {run.durationSeconds.toFixed(1)}s
                      </TableCell>
                      <TableCell className="text-xs text-text-muted">
                        {formatRelative(run.startedAt)}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
