import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
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
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";
import type { RecoveryCandidate } from "@/lib/adapters/tauri";

type CandidateStatus =
  | "pending"
  | "shadow"
  | "ready"
  | "committed"
  | "rejected"
  | "quarantined";

function statusVariant(
  status: string,
): "warning" | "accent" | "active" | "neutral" | "error" | "expired" {
  switch (status as CandidateStatus) {
    case "pending":
      return "warning";
    case "shadow":
      return "accent";
    case "ready":
      return "active";
    case "committed":
      return "neutral";
    case "rejected":
      return "error";
    case "quarantined":
      return "error";
    default:
      return "neutral";
  }
}

type StatusKey = "pending" | "shadow" | "ready" | "committed" | "rejected" | "quarantined";

const STATUS_LABELS: StatusKey[] = [
  "pending",
  "shadow",
  "ready",
  "committed",
  "rejected",
  "quarantined",
];

export default function RecoveryPage() {
  const queryClient = useQueryClient();
  const [actionLoading, setActionLoading] = useState<Record<string, "approve" | "reject" | null>>({});

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["recovery", "candidates"],
    queryFn: () => adapter.recovery.listCandidates(),
    refetchInterval: 10000,
  });

  const candidates = (data ?? []) as RecoveryCandidate[];

  const statusCounts = STATUS_LABELS.reduce<Record<string, number>>((acc, s) => {
    acc[s] = candidates.filter((c) => c.status === s).length;
    return acc;
  }, {});

  async function handleApprove(id: string) {
    setActionLoading((prev) => ({ ...prev, [id]: "approve" }));
    try {
      await adapter.recovery.approve(id);
      await queryClient.invalidateQueries({ queryKey: ["recovery", "candidates"] });
    } finally {
      setActionLoading((prev) => ({ ...prev, [id]: null }));
    }
  }

  async function handleReject(id: string) {
    setActionLoading((prev) => ({ ...prev, [id]: "reject" }));
    try {
      await adapter.recovery.reject(id);
      await queryClient.invalidateQueries({ queryKey: ["recovery", "candidates"] });
    } finally {
      setActionLoading((prev) => ({ ...prev, [id]: null }));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Recovery</h1>
          <p className="text-xs text-text-muted">
            Mined recovery strategy candidates — approve to promote to the runtime ladder
          </p>
        </div>
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
      </header>

      {/* Status counts */}
      <div className="flex flex-wrap gap-2">
        {STATUS_LABELS.map((s) => (
          <Card key={s} className="flex-1 min-w-[90px]">
            <CardContent className="p-3 flex flex-col items-center gap-1">
              <div className="text-xl font-semibold tabular-nums">
                {isLoading ? (
                  <Skeleton className="h-6 w-8" />
                ) : (
                  statusCounts[s] ?? 0
                )}
              </div>
              <Tag variant={statusVariant(s)} className="capitalize">
                {s}
              </Tag>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Main table */}
      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Primitive</TableHead>
              <TableHead className="text-right">Support</TableHead>
              <TableHead className="text-right">Lift</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={7}>
                    <Skeleton className="h-4 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : isError ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center text-xs text-state-error py-8"
                >
                  Failed to load candidates:{" "}
                  {error instanceof Error ? error.message : "Unknown error"}
                </TableCell>
              </TableRow>
            ) : candidates.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center text-xs text-text-muted py-10"
                >
                  No recovery candidates yet. Run{" "}
                  <code className="font-mono bg-bg-elevated px-1 rounded">
                    bm recovery mine
                  </code>{" "}
                  to generate candidates from failure patterns.
                </TableCell>
              </TableRow>
            ) : (
              candidates.map((c) => {
                const busy = !!actionLoading[c.id];
                const canAct =
                  c.status === "ready" || c.status === "pending";

                return (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium max-w-[180px] truncate">
                      {String(c.name ?? c.id)}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-text-muted">
                      {String(c.primitive ?? "—")}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {typeof c.support === "number"
                        ? c.support.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {typeof c.lift === "number"
                        ? c.lift.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <Tag variant={statusVariant(String(c.status ?? ""))} className="capitalize">
                        {String(c.status ?? "—")}
                      </Tag>
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {c.createdAt ? formatRelative(String(c.createdAt)) : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {canAct && (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busy}
                            onClick={() => void handleApprove(c.id)}
                          >
                            {busy && actionLoading[c.id] === "approve" ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : null}
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={busy}
                            onClick={() => void handleReject(c.id)}
                          >
                            {busy && actionLoading[c.id] === "reject" ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : null}
                            Reject
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
