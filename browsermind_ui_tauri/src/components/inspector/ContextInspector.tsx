import {
  Activity,
  CheckSquare,
  GitBranch,
  Globe,
  KeyRound,
  MousePointer2,
  UserCircle,
  X,
} from "lucide-react";
import { ScrollArea } from "@/components/ui";
import { useInspectorStore, type InspectorEntityType } from "@/stores";
import { TaskInspector } from "./inspectors/TaskInspector";
import { ExecutionInspector } from "./inspectors/ExecutionInspector";
import { IdentityInspector } from "./inspectors/IdentityInspector";
import { EnvironmentInspector } from "./inspectors/EnvironmentInspector";
import { WorkflowInspector } from "./inspectors/WorkflowInspector";
import { PersonaInspector } from "./inspectors/PersonaInspector";

const TYPE_META: Record<
  Exclude<InspectorEntityType, null>,
  { label: string; Icon: typeof CheckSquare }
> = {
  task: { label: "Task", Icon: CheckSquare },
  execution: { label: "Execution", Icon: Activity },
  identity: { label: "Identity", Icon: KeyRound },
  environment: { label: "Environment", Icon: Globe },
  workflow: { label: "Workflow", Icon: GitBranch },
  persona: { label: "Persona", Icon: UserCircle },
};

export function ContextInspector() {
  const { selected, setOpen } = useInspectorStore();

  if (!selected.type || !selected.id) {
    return (
      <aside className="h-full bg-bg-panel border-l border-border-default flex flex-col">
        <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
          <MousePointer2 className="h-5 w-5 text-text-subtle" />
          <div className="text-sm text-text-muted">
            Select an item to inspect
          </div>
          <div className="text-xs text-text-subtle">
            Click a row, card, or step to see details here.
          </div>
        </div>
      </aside>
    );
  }

  const meta = TYPE_META[selected.type];
  const Icon = meta.Icon;

  return (
    <aside className="h-full bg-bg-panel border-l border-border-default flex flex-col">
      <header className="flex items-center justify-between border-b border-border-default px-4 h-10 shrink-0">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-text-muted" />
          <div className="text-[11px] uppercase tracking-wider text-text-muted">
            {meta.label}
          </div>
        </div>
        <button
          onClick={() => setOpen(false)}
          className="text-text-muted hover:text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded-sm"
          aria-label="Close inspector"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <ScrollArea className="flex-1">
        <div className="p-4">
          {selected.type === "task" && <TaskInspector id={selected.id} />}
          {selected.type === "execution" && (
            <ExecutionInspector id={selected.id} />
          )}
          {selected.type === "identity" && (
            <IdentityInspector id={selected.id} />
          )}
          {selected.type === "environment" && (
            <EnvironmentInspector id={selected.id} />
          )}
          {selected.type === "workflow" && (
            <WorkflowInspector id={selected.id} />
          )}
          {selected.type === "persona" && (
            <PersonaInspector id={selected.id} />
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}

export default ContextInspector;
