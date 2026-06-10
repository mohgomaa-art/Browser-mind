import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Switch,
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
import { formatRelative } from "@/lib/utils";
import { useInspectorStore } from "@/stores";
import type { IdentityStatus, TaskState } from "@/types";

const TASK_VARIANT: Record<
  TaskState,
  "active" | "warning" | "error" | "neutral" | "expired"
> = {
  created: "neutral",
  running: "active",
  paused: "warning",
  waiting: "warning",
  blocked: "warning",
  failed: "error",
  completed: "active",
};

const ID_VARIANT: Record<
  IdentityStatus,
  "active" | "warning" | "error" | "expired"
> = {
  active: "active",
  expired: "expired",
  revoked: "error",
  requires_2fa: "warning",
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function PersonaDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const setSelected = useInspectorStore((s) => s.setSelected);
  const setOpen = useInspectorStore((s) => s.setOpen);

  const personaQ = useQuery({
    queryKey: ["persona", id],
    queryFn: () => adapter.personas.byId(id!),
    enabled: !!id,
  });
  const identitiesQ = useQuery({
    queryKey: ["identities", id],
    queryFn: () => adapter.identities.list(id!),
    enabled: !!id,
  });
  const envsQ = useQuery({
    queryKey: ["environments"],
    queryFn: () => adapter.environments.list(),
  });
  const tasksQ = useQuery({
    queryKey: ["tasks", { personaId: id }],
    queryFn: () => adapter.tasks.list({ personaId: id! }),
    enabled: !!id,
  });
  const memoryQ = useQuery({
    queryKey: ["memory", "all"],
    queryFn: () => adapter.memory.list(),
  });

  if (personaQ.isLoading) return <Skeleton className="h-32 w-full" />;
  const persona = personaQ.data;
  if (!persona) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold">Persona not found</h1>
        <Button variant="ghost" size="sm" onClick={() => navigate("/dev/personas")}>
          ← Back to personas
        </Button>
      </div>
    );
  }

  const identities = identitiesQ.data ?? [];
  const envKeys = new Set(identities.map((i) => i.environmentKey));
  const envsForPersona = (envsQ.data ?? []).filter((e) => envKeys.has(e.key));
  const tasks = tasksQ.data ?? [];
  const memoryForPersona = (memoryQ.data ?? []).filter((m) =>
    m.relatedEntities.some((r) => r.id === persona.id),
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center gap-4">
        <Avatar className="h-12 w-12">
          {persona.avatarUrl && (
            <AvatarImage src={persona.avatarUrl} alt={persona.displayName} />
          )}
          <AvatarFallback>{initials(persona.displayName)}</AvatarFallback>
        </Avatar>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            {persona.displayName}
          </h1>
          <p className="text-xs text-text-muted font-mono">{persona.name}</p>
        </div>
      </header>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="identities">Identities</TabsTrigger>
          <TabsTrigger value="environments">Environments</TabsTrigger>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="memory">Memory</TabsTrigger>
          <TabsTrigger value="trust">Trust Policies</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <Card>
            <CardContent className="p-4 space-y-3 text-sm">
              <Row label="ID" value={<span className="font-mono text-xs">{persona.id}</span>} />
              <Row label="Principal" value={<span className="font-mono text-xs">{persona.principalId}</span>} />
              <Row label="Created" value={formatRelative(persona.createdAt)} />
              {persona.bio && <Row label="Bio" value={persona.bio} />}
              <div className="pt-2 flex gap-2">
                <Button size="sm" variant="secondary">Edit</Button>
                <Button size="sm" variant="destructive">Delete</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="identities" className="mt-4">
          <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Identifier</TableHead>
                  <TableHead>Environment</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Last Used</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {identities.map((i) => (
                  <TableRow
                    key={i.id}
                    className="cursor-pointer"
                    onClick={() => {
                      setSelected({ type: "identity", id: i.id });
                      setOpen(true);
                    }}
                  >
                    <TableCell className="font-mono text-xs">{i.identifier}</TableCell>
                    <TableCell><Tag variant="neutral">{i.environmentKey}</Tag></TableCell>
                    <TableCell><Tag variant={ID_VARIANT[i.status]}>{i.status}</Tag></TableCell>
                    <TableCell><Tag variant="neutral">{i.credentialType}</Tag></TableCell>
                    <TableCell className="text-text-muted text-xs">
                      {i.lastUsedAt ? formatRelative(i.lastUsedAt) : "Never"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="environments" className="mt-4">
          <div className="grid grid-cols-3 gap-3">
            {envsForPersona.map((e) => (
              <Card key={e.key}>
                <CardHeader>
                  <CardTitle>{e.label}</CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-text-muted space-y-1">
                  <div>Family: {e.family}</div>
                  <div>Status: <Tag variant="neutral">{e.status}</Tag></div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="tasks" className="mt-4">
          <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Goal</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Environment</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((t) => (
                  <TableRow
                    key={t.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/dev/tasks/${t.id}`)}
                  >
                    <TableCell className="font-medium">{t.goal}</TableCell>
                    <TableCell><Tag variant={TASK_VARIANT[t.state]}>{t.state}</Tag></TableCell>
                    <TableCell><Tag variant="neutral">{t.environmentKey ?? "—"}</Tag></TableCell>
                    <TableCell className="text-text-muted text-xs">{formatRelative(t.updatedAt)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="memory" className="mt-4">
          <div className="space-y-2">
            {memoryForPersona.length === 0 && (
              <div className="text-sm text-text-subtle">No memory entries linked.</div>
            )}
            {memoryForPersona.map((m) => (
              <Card key={m.id}>
                <CardContent className="p-3 flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{m.title}</div>
                    <div className="text-xs text-text-muted truncate">{m.content}</div>
                  </div>
                  <Tag variant="neutral">{m.type}</Tag>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="trust" className="mt-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              <PolicyRow
                title="Auto-resume on transient failures"
                desc="Re-run a step automatically when a network or DOM glitch is detected."
                defaultChecked
              />
              <PolicyRow
                title="Require confirmation before destructive actions"
                desc="Pause and ask before any irreversible action."
                defaultChecked
              />
              <PolicyRow
                title="Allow cross-environment data flow"
                desc="Permit sharing of resources between environments."
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-32 text-[11px] uppercase tracking-wider text-text-subtle">
        {label}
      </div>
      <div className="text-sm">{value}</div>
    </div>
  );
}

function PolicyRow({
  title,
  desc,
  defaultChecked,
}: {
  title: string;
  desc: string;
  defaultChecked?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border-default last:border-b-0 pb-3 last:pb-0">
      <div>
        <div className="text-sm">{title}</div>
        <div className="text-xs text-text-muted">{desc}</div>
      </div>
      <Switch defaultChecked={defaultChecked} />
    </div>
  );
}
