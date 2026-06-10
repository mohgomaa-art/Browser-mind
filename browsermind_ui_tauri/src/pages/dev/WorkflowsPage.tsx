import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import {
  Button,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from "@/components/ui";
import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { formatRelative, truncate } from "@/lib/utils";
import type { WorkflowStep } from "@/types";

function flatten(steps: WorkflowStep[]): WorkflowStep[] {
  const out: WorkflowStep[] = [];
  for (const s of steps) {
    out.push(s);
    if (s.children?.length) out.push(...flatten(s.children));
  }
  return out;
}

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["workflows"],
    queryFn: () => adapter.workflows.list(),
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Workflows</h1>
          <p className="text-xs text-text-muted">
            Reusable templates compiled from demonstrations.
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-3.5 w-3.5 mr-1" />
          Create Workflow
        </Button>
      </header>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead className="text-right">Steps</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : (data ?? []).map((w) => (
                  <TableRow
                    key={w.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/dev/workflows/${w.id}`)}
                  >
                    <TableCell className="font-medium">{w.name}</TableCell>
                    <TableCell className="text-xs text-text-muted max-w-md truncate">
                      {truncate(w.description, 80)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{w.version}</TableCell>
                    <TableCell>
                      <Tag variant="neutral">{w.environmentKey ?? "—"}</Tag>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {flatten(w.steps).length}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {formatRelative(w.updatedAt)}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
