import { useNavigate } from "react-router-dom";
import { Workflow, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { formatRelative } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import type { WorkflowTemplate } from "@/types";

function WorkflowCard({
  template,
  envLabel,
}: {
  template: WorkflowTemplate;
  envLabel?: string;
}) {
  const navigate = useNavigate();
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/automations/${template.id}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter") navigate(`/automations/${template.id}`);
      }}
      className="hover:border-border-strong transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="h-7 w-7 rounded-md bg-bg-elevated border border-border-default flex items-center justify-center shrink-0">
              <Workflow className="h-3.5 w-3.5 text-text-muted" />
            </div>
            <div className="text-sm font-medium text-text-primary truncate">
              {template.name}
            </div>
          </div>
          <Badge variant="neutral">v{template.version}</Badge>
        </div>
        <p className="text-xs text-text-muted line-clamp-2">
          {template.description}
        </p>
        <div className="flex items-center justify-between gap-2 pt-1 text-[11px] text-text-muted">
          <div className="flex items-center gap-2">
            {envLabel ? <Badge variant="neutral">{envLabel}</Badge> : null}
            <span>{template.steps.length} steps</span>
          </div>
          <span>Updated {formatRelative(template.updatedAt)}</span>
        </div>
      </div>
    </Card>
  );
}

export default function AutomationsPage() {
  const workflowsQuery = useQuery({
    queryKey: ["workflows"],
    queryFn: () => adapter.workflows.list(),
  });
  const envQuery = useQuery({
    queryKey: ["environments"],
    queryFn: () => adapter.environments.list(),
  });

  const envMap = new Map<string, string>();
  (envQuery.data ?? []).forEach((e) => envMap.set(e.key, e.label));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Automations</h1>
          <p className="text-xs text-text-muted">
            Reusable workflow templates.
          </p>
        </div>
      </header>

      {workflowsQuery.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-lg" />
          ))}
        </div>
      ) : workflowsQuery.isError ? (
        <Card>
          <div className="p-4 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load automations.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => workflowsQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      ) : (workflowsQuery.data ?? []).length === 0 ? (
        <Card>
          <div className="p-10 flex flex-col items-center gap-3">
            <Workflow className="h-6 w-6 text-text-subtle" />
            <p className="text-sm text-text-muted">
              No automations yet — record a session to capture one.
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {(workflowsQuery.data ?? []).map((tpl) => (
            <WorkflowCard
              key={tpl.id}
              template={tpl}
              envLabel={
                tpl.environmentKey ? envMap.get(tpl.environmentKey) : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
