import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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
import { useInspectorStore } from "@/stores";
import type { IdentityStatus } from "@/types";

const ID_VARIANT: Record<
  IdentityStatus,
  "active" | "warning" | "error" | "expired"
> = {
  active: "active",
  expired: "expired",
  revoked: "error",
  requires_2fa: "warning",
};

export default function IdentitiesPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [envFilter, setEnvFilter] = useState<string>("all");
  const setSelected = useInspectorStore((s) => s.setSelected);
  const setOpen = useInspectorStore((s) => s.setOpen);

  const identitiesQ = useQuery({
    queryKey: ["identities", "all"],
    queryFn: () => adapter.identities.list(),
  });
  const personasQ = useQuery({
    queryKey: ["personas"],
    queryFn: () => adapter.personas.list(),
  });
  const envsQ = useQuery({
    queryKey: ["environments"],
    queryFn: () => adapter.environments.list(),
  });

  const personaName = (id: string) =>
    personasQ.data?.find((p) => p.id === id)?.displayName ?? id;

  const filtered = (identitiesQ.data ?? []).filter((i) => {
    if (search && !i.identifier.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (statusFilter !== "all" && i.status !== statusFilter) return false;
    if (envFilter !== "all" && i.environmentKey !== envFilter) return false;
    return true;
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Identities</h1>
          <p className="text-xs text-text-muted">
            Credentials and login state per environment.
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-3.5 w-3.5 mr-1" />
          Provision
        </Button>
      </header>

      <div className="flex items-center gap-2">
        <Input
          placeholder="Search by identifier…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
            <SelectItem value="revoked">Revoked</SelectItem>
            <SelectItem value="requires_2fa">Requires 2FA</SelectItem>
          </SelectContent>
        </Select>
        <Select value={envFilter} onValueChange={setEnvFilter}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All envs</SelectItem>
            {(envsQ.data ?? []).map((e) => (
              <SelectItem key={e.key} value={e.key}>
                {e.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Identifier</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Persona</TableHead>
              <TableHead>Last Used</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {identitiesQ.isLoading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={8}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : filtered.map((i) => (
                  <TableRow
                    key={i.id}
                    className="cursor-pointer"
                    onClick={() => {
                      setSelected({ type: "identity", id: i.id });
                      setOpen(true);
                    }}
                  >
                    <TableCell className="font-mono text-xs">
                      {i.identifier}
                    </TableCell>
                    <TableCell>
                      <Tag variant="neutral">{i.environmentKey}</Tag>
                    </TableCell>
                    <TableCell>
                      <Tag variant={ID_VARIANT[i.status]}>{i.status}</Tag>
                    </TableCell>
                    <TableCell>
                      <Tag variant="neutral">{i.credentialType}</Tag>
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {personaName(i.personaId)}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {i.lastUsedAt ? formatRelative(i.lastUsedAt) : "Never"}
                    </TableCell>
                    <TableCell className="text-xs text-text-muted">
                      {i.expiresAt ? formatRelative(i.expiresAt) : "—"}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          asChild
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Button variant="ghost" size="sm">
                            …
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>Rotate</DropdownMenuItem>
                          <DropdownMenuItem>Reauthenticate</DropdownMenuItem>
                          <DropdownMenuItem>Disable</DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelected({ type: "identity", id: i.id });
                              setOpen(true);
                            }}
                          >
                            Inspect
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
