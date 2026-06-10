import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";
import type { LedgerEvent, LedgerKind } from "@/types";

const TIME_PRESETS = [
  { value: "1h", label: "Last 1h", ms: 60 * 60 * 1000 },
  { value: "24h", label: "Last 24h", ms: 24 * 60 * 60 * 1000 },
  { value: "7d", label: "Last 7d", ms: 7 * 24 * 60 * 60 * 1000 },
  { value: "14d", label: "Last 14d", ms: 14 * 24 * 60 * 60 * 1000 },
  { value: "all", label: "All time", ms: Infinity },
] as const;

const KIND_VARIANT: Record<LedgerKind, "active" | "warning" | "neutral"> = {
  mutation: "neutral",
  execution: "active",
  policy: "warning",
};

export default function LedgerPage() {
  const [open, setOpen] = useState<LedgerEvent | null>(null);
  const [time, setTime] = useState<string>("24h");
  const [kind, setKind] = useState<string>("all");
  const [search, setSearch] = useState("");

  const personasQ = useQuery({
    queryKey: ["personas"],
    queryFn: () => adapter.personas.list(),
  });
  const envsQ = useQuery({
    queryKey: ["environments"],
    queryFn: () => adapter.environments.list(),
  });
  const ledgerQ = useQuery({
    queryKey: ["ledger", "all"],
    queryFn: () => adapter.ledger.list(),
  });

  const filtered = useMemo(() => {
    const preset = TIME_PRESETS.find((p) => p.value === time)!;
    const cutoff = Date.now() - preset.ms;
    return (ledgerQ.data ?? []).filter((e) => {
      if (preset.ms !== Infinity && new Date(e.timestamp).getTime() < cutoff)
        return false;
      if (kind !== "all" && e.kind !== kind) return false;
      if (
        search &&
        !`${e.summary} ${e.entityType} ${e.entityId}`
          .toLowerCase()
          .includes(search.toLowerCase())
      )
        return false;
      return true;
    });
  }, [ledgerQ.data, time, kind, search]);

  const personaName = (id?: string) =>
    id
      ? personasQ.data?.find((p) => p.id === id)?.displayName ?? id
      : "—";
  const envLabel = (key?: string) =>
    key
      ? envsQ.data?.find((e) => e.key === key)?.label ?? key
      : "—";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Ledger</h1>
        <p className="text-xs text-text-muted">
          Append-only event log of every mutation, execution, and policy decision.
        </p>
      </header>

      <div className="flex items-center gap-2 flex-wrap">
        <Select value={time} onValueChange={setTime}>
          <SelectTrigger className="w-32 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIME_PRESETS.map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-36 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All kinds</SelectItem>
            <SelectItem value="mutation">Mutation</SelectItem>
            <SelectItem value="execution">Execution</SelectItem>
            <SelectItem value="policy">Policy</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <span className="text-[11px] text-text-subtle ml-auto">
          {filtered.length} of {ledgerQ.data?.length ?? 0}
        </span>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>ID</TableHead>
              <TableHead>Summary</TableHead>
              <TableHead>Persona</TableHead>
              <TableHead>Env</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ledgerQ.isLoading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : filtered.map((e) => (
                  <TableRow
                    key={e.id}
                    className="cursor-pointer"
                    onClick={() => setOpen(e)}
                  >
                    <TableCell className="font-mono text-[11px] text-text-muted">
                      {formatRelative(e.timestamp)}
                    </TableCell>
                    <TableCell>
                      <Tag variant={KIND_VARIANT[e.kind]}>{e.kind}</Tag>
                    </TableCell>
                    <TableCell className="font-mono text-[11px]">
                      {e.entityType}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-text-subtle">
                      {e.entityId}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted truncate max-w-md">
                      {e.summary}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {personaName(e.personaId)}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {envLabel(e.environmentKey)}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>

      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent side="right" className="w-[640px]">
          {open && (
            <>
              <SheetHeader>
                <SheetTitle>{open.entityType} mutation</SheetTitle>
              </SheetHeader>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Tag variant={KIND_VARIANT[open.kind]}>{open.kind}</Tag>
                  <span className="font-mono text-[11px] text-text-subtle">
                    {open.entityId}
                  </span>
                  <span className="text-[11px] text-text-subtle ml-auto">
                    {formatRelative(open.timestamp)}
                  </span>
                </div>
                <div className="text-text-muted">{open.summary}</div>
                <div className="grid grid-cols-2 gap-3">
                  <Card>
                    <CardContent className="p-3">
                      <div className="text-[11px] uppercase tracking-wider text-text-subtle mb-1">
                        Before
                      </div>
                      <pre className="font-mono text-[11px] text-text-muted whitespace-pre-wrap break-all max-h-72 overflow-auto">
                        {open.before
                          ? JSON.stringify(open.before, null, 2)
                          : "(none)"}
                      </pre>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-3">
                      <div className="text-[11px] uppercase tracking-wider text-text-subtle mb-1">
                        After
                      </div>
                      <pre className="font-mono text-[11px] text-text-muted whitespace-pre-wrap break-all max-h-72 overflow-auto">
                        {open.after
                          ? JSON.stringify(open.after, null, 2)
                          : "(none)"}
                      </pre>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
