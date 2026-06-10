import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui";
import { formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { TaskState } from "@/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function PersonaInspector({ id }: { id: string }) {
  const personaQ = useQuery({
    queryKey: ["inspector", "persona", id],
    queryFn: () => adapter.personas.byId(id),
  });
  const identitiesQ = useQuery({
    queryKey: ["inspector", "persona", id, "identities"],
    queryFn: () => adapter.identities.list(id),
    enabled: !!personaQ.data,
  });
  const tasksQ = useQuery({
    queryKey: ["inspector", "persona", id, "tasks"],
    queryFn: () => adapter.tasks.list({ personaId: id }),
    enabled: !!personaQ.data,
  });

  if (personaQ.isLoading) return <LoadingRows />;
  const data = personaQ.data;
  if (!data) return <NotFound kind="Persona" />;

  const identitiesCount = identitiesQ.data?.length ?? 0;
  const tasks = tasksQ.data ?? [];
  const tasksByState = tasks.reduce<Record<TaskState, number>>(
    (acc, t) => {
      acc[t.state] = (acc[t.state] ?? 0) + 1;
      return acc;
    },
    {
      created: 0,
      running: 0,
      paused: 0,
      waiting: 0,
      blocked: 0,
      failed: 0,
      completed: 0,
    },
  );
  const breakdown = (Object.entries(tasksByState) as [TaskState, number][])
    .filter(([, n]) => n > 0)
    .map(([s, n]) => `${n} ${s}`)
    .join(" • ");

  return (
    <div>
      <Section first label="Persona">
        <div className="flex items-center gap-3">
          <Avatar className="h-9 w-9">
            {data.avatarUrl && (
              <AvatarImage src={data.avatarUrl} alt={data.displayName} />
            )}
            <AvatarFallback>{initials(data.displayName)}</AvatarFallback>
          </Avatar>
          <div className="flex flex-col">
            <span className="font-medium text-sm">{data.displayName}</span>
            <span className="text-xs text-text-subtle font-mono">
              {data.name}
            </span>
          </div>
        </div>
      </Section>
      {data.bio && (
        <Section label="Bio">
          <span className="text-sm text-text-muted">{data.bio}</span>
        </Section>
      )}
      <Section label="Principal ID">
        <span className="font-mono text-xs text-text-subtle break-all">
          {data.principalId}
        </span>
      </Section>
      <Section label="Identities">{identitiesCount}</Section>
      <Section label="Tasks">
        <div className="flex flex-col gap-0.5">
          <span>{tasks.length}</span>
          {breakdown && (
            <span className="text-[11px] text-text-subtle">{breakdown}</span>
          )}
        </div>
      </Section>
      <Section label="Created">
        <span className="text-text-muted text-xs">
          {formatRelative(data.createdAt)}
        </span>
      </Section>
      <Section label="ID">
        <span className="font-mono text-xs text-text-subtle break-all">
          {data.id}
        </span>
      </Section>
    </div>
  );
}
