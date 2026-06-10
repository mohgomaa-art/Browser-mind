import { Fragment, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronDown,
  Play,
  Square,
  GitBranch,
  Diamond,
  Check,
  History,
  Eye,
  Diff,
  AlertCircle,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { adapter } from "@/lib/adapters";
import { useInspectorStore } from "@/stores";
import type { StepKind, WorkflowStep } from "@/types";

function StepIcon({ kind }: { kind: StepKind }) {
  const cls = "h-3.5 w-3.5 text-text-muted";
  switch (kind) {
    case "start":
      return <Play className={cls} />;
    case "step":
      return <Square className={cls} />;
    case "branch":
      return <GitBranch className={cls} />;
    case "condition":
      return <Diamond className={cls} />;
    case "end":
      return <Check className={cls} />;
  }
}

function StepPill({
  step,
  onClick,
}: {
  step: WorkflowStep;
  onClick: () => void;
}) {
  const label = step.semanticName ?? step.actionType ?? step.kind;
  const sub =
    step.actionType && step.targetRole
      ? `${step.actionType} · ${step.targetRole}`
      : step.actionType ?? step.targetRole;
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 px-3 h-9 rounded-md border border-border-default bg-bg-panel text-sm text-text-primary hover:border-border-strong transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent w-full justify-start"
    >
      <StepIcon kind={step.kind} />
      <span className="truncate">{label}</span>
      {sub ? (
        <span className="text-xs text-text-muted truncate">{sub}</span>
      ) : null}
    </button>
  );
}

function Connector() {
  return (
    <div className="flex flex-col items-center" aria-hidden>
      <div className="h-3 w-px bg-border-default" />
      <ChevronDown className="h-3 w-3 text-text-subtle -my-1" />
      <div className="h-3 w-px bg-border-default" />
    </div>
  );
}

export default function WorkflowViewerPage() {
  const { workflowId = "" } = useParams<{ workflowId: string }>();
  const setSelected = useInspectorStore((s) => s.setSelected);
  const setOpen = useInspectorStore((s) => s.setOpen);
  const [dialog, setDialog] = useState<string | null>(null);

  const workflowQuery = useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => adapter.workflows.byId(workflowId),
    enabled: !!workflowId,
  });

  const steps = useMemo(() => {
    const list = workflowQuery.data?.steps ?? [];
    return [...list].sort((a, b) => a.seq - b.seq);
  }, [workflowQuery.data]);

  if (workflowQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-64 rounded-md" />
        <div className="max-w-md mx-auto w-full flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 rounded-md" />
          ))}
        </div>
      </div>
    );
  }

  if (workflowQuery.isError || !workflowQuery.data) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          to="/automations"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-3 w-3" /> Back to automations
        </Link>
        <Card>
          <div className="p-6 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load this workflow.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => workflowQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const workflow = workflowQuery.data;

  const handleStepClick = () => {
    setSelected({ type: "workflow", id: workflow.id });
    setOpen(true);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/automations"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-3 w-3" /> Back to automations
        </Link>
        <header className="flex items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight truncate">
              {workflow.name}
            </h1>
            <p className="text-xs text-text-muted line-clamp-1">
              {workflow.description}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="neutral">v{workflow.version}</Badge>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDialog("Inspect")}
            >
              <Eye className="h-3.5 w-3.5" />
              Inspect
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDialog("Diff")}
            >
              <Diff className="h-3.5 w-3.5" />
              Diff
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDialog("Version History")}
            >
              <History className="h-3.5 w-3.5" />
              History
            </Button>
          </div>
        </header>
      </div>

      <div className="max-w-md mx-auto w-full flex flex-col gap-2 py-4">
        {steps.length === 0 ? (
          <p className="text-xs text-text-muted text-center">
            This workflow has no steps yet.
          </p>
        ) : (
          steps.map((step, idx) => (
            <Fragment key={`${step.seq}-${idx}`}>
              <StepPill step={step} onClick={handleStepClick} />
              {idx < steps.length - 1 ? <Connector /> : null}
            </Fragment>
          ))
        )}
      </div>

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dialog}</DialogTitle>
            <DialogDescription>
              This view is coming soon.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
