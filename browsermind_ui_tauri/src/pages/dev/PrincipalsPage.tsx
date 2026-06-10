import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
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
import { useInspectorStore } from "@/stores";

export default function PrincipalsPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["principals"],
    queryFn: () => adapter.principals.list(),
  });
  const setSelected = useInspectorStore((s) => s.setSelected);
  const setOpen = useInspectorStore((s) => s.setOpen);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Principals</h1>
          <p className="text-xs text-text-muted">
            The top-level identity that owns all personas.
          </p>
        </div>
      </header>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 1 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={4}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : (data ?? []).map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-mono text-xs text-text-muted">
                      {p.id}
                    </TableCell>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="text-text-muted text-xs">
                      {formatRelative(p.createdAt)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setSelected({ type: "persona", id: p.id });
                          setOpen(true);
                          navigate("/dev/personas");
                        }}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
