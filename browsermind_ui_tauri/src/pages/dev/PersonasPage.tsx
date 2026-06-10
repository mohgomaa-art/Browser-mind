import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Button,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function PersonasPage() {
  const navigate = useNavigate();
  const personasQ = useQuery({
    queryKey: ["personas"],
    queryFn: () => adapter.personas.list(),
  });
  const identitiesQ = useQuery({
    queryKey: ["identities", "all"],
    queryFn: () => adapter.identities.list(),
  });
  const tasksQ = useQuery({
    queryKey: ["tasks", "all"],
    queryFn: () => adapter.tasks.list(),
  });

  const personas = personasQ.data ?? [];
  const identitiesByPersona = (identitiesQ.data ?? []).reduce<
    Record<string, number>
  >((acc, i) => {
    acc[i.personaId] = (acc[i.personaId] ?? 0) + 1;
    return acc;
  }, {});
  const tasksByPersona = (tasksQ.data ?? []).reduce<Record<string, number>>(
    (acc, t) => {
      acc[t.personaId] = (acc[t.personaId] ?? 0) + 1;
      return acc;
    },
    {},
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Personas</h1>
          <p className="text-xs text-text-muted">
            Distinct selves with their own identities and memory.
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-3.5 w-3.5 mr-1" />
          Create Persona
        </Button>
      </header>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead></TableHead>
              <TableHead>Display Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Principal</TableHead>
              <TableHead className="text-right">Identities</TableHead>
              <TableHead className="text-right">Tasks</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {personasQ.isLoading
              ? Array.from({ length: 2 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : personas.map((p) => (
                  <TableRow
                    key={p.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/dev/personas/${p.id}`)}
                  >
                    <TableCell>
                      <Avatar className="h-7 w-7">
                        {p.avatarUrl && (
                          <AvatarImage src={p.avatarUrl} alt={p.displayName} />
                        )}
                        <AvatarFallback>
                          {initials(p.displayName)}
                        </AvatarFallback>
                      </Avatar>
                    </TableCell>
                    <TableCell className="font-medium">
                      {p.displayName}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-text-muted">
                      {p.name}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-text-subtle">
                      {p.principalId}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {identitiesByPersona[p.id] ?? 0}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {tasksByPersona[p.id] ?? 0}
                    </TableCell>
                    <TableCell className="text-text-muted text-xs">
                      {formatRelative(p.createdAt)}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
