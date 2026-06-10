import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Progress, Tag } from "@/components/ui";
import { formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { TaskState } from "@/types";

const STATE_VARIANT: Record<TaskState, "active" | "warning" | "error" | "neutral" | "expired"> = {
  created: "neutral",
  running: "active",
  paused: "warning",
  waiting: "warning",
  blocked: "warning",
  failed: "error",
  completed: "active",
};

export function TaskInspector({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["inspector", "task", id],
    queryFn: () => adapter.tasks.byId(id),
  });

  if (isLoading) return <LoadingRows />;
  if (!data) return <NotFound kind="Task" />;

  const pct =
    data.progress.total > 0
      ? Math.round((data.progress.current / data.progress.total) * 100)
      : 0;

  return (
    <div>
      <Section first label="Goal">
        <span className="font-medium">{data.goal}</span>
      </Section>
      <Section label="State">
        <Tag variant={STATE_VARIANT[data.state]}>{data.state}</Tag>
      </Section>
      <Section label="Progress">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-muted">
              {data.progress.current} of {data.progress.total}
            </span>
            <span className="text-text-subtle">{pct}%</span>
          </div>
          <Progress value={pct} />
        </div>
      </Section>
      {data.environmentKey && (
        <Section label="Environment">
          <Tag variant="neutral">{data.environmentKey}</Tag>
        </Section>
      )}
      <Section label="Missing Resources">
        {data.missingResources.length === 0 ? (
          <span className="text-text-subtle text-xs">None</span>
        ) : (
          <ul className="list-disc list-inside text-xs text-text-muted space-y-0.5">
            {data.missingResources.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
      </Section>
      {data.nextAction && (
        <Section label="Next Action">{data.nextAction}</Section>
      )}
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
