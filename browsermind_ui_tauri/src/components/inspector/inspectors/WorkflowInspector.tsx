import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Tag } from "@/components/ui";
import { formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { StepKind, WorkflowStep } from "@/types";

function flattenSteps(steps: WorkflowStep[]): WorkflowStep[] {
  const out: WorkflowStep[] = [];
  for (const s of steps) {
    out.push(s);
    if (s.children?.length) out.push(...flattenSteps(s.children));
  }
  return out;
}

export function WorkflowInspector({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["inspector", "workflow", id],
    queryFn: () => adapter.workflows.byId(id),
  });

  if (isLoading) return <LoadingRows />;
  if (!data) return <NotFound kind="Workflow" />;

  const flat = flattenSteps(data.steps);
  const byKind = flat.reduce<Record<StepKind, number>>(
    (acc, s) => {
      acc[s.kind] = (acc[s.kind] ?? 0) + 1;
      return acc;
    },
    { start: 0, step: 0, branch: 0, condition: 0, end: 0 },
  );
  const breakdown = (Object.entries(byKind) as [StepKind, number][])
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${k}`)
    .join(" • ");

  return (
    <div>
      <Section first label="Name">
        <span className="font-medium text-base">{data.name}</span>
      </Section>
      <Section label="Description">
        <span className="text-sm text-text-muted">{data.description}</span>
      </Section>
      <Section label="Version">
        <span className="font-mono text-xs">{data.version}</span>
      </Section>
      {data.environmentKey && (
        <Section label="Environment">
          <Tag variant="neutral">{data.environmentKey}</Tag>
        </Section>
      )}
      <Section label="Step Count">{flat.length}</Section>
      <Section label="Step Kinds">
        <span className="text-xs text-text-muted">{breakdown}</span>
      </Section>
      <Section label="Created">
        <span className="text-text-muted text-xs">
          {formatRelative(data.createdAt)}
        </span>
      </Section>
      <Section label="Updated">
        <span className="text-text-muted text-xs">
          {formatRelative(data.updatedAt)}
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
