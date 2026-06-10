import { useNavigate } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Briefcase,
  Globe,
  GitBranch,
  Home,
  KeyRound,
  LayoutDashboard,
  PlayCircle,
  RefreshCw,
  Settings,
  TerminalSquare,
  Users,
  Workflow,
} from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Kbd,
  Tag,
} from "@/components/ui";
import { useCommandPaletteStore, useModeStore } from "@/stores";
import {
  useEnvironments,
  useExecutions,
  useTasks,
} from "@/lib/queries";

interface NavItem {
  label: string;
  to: string;
  Icon: typeof Home;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Go to Home", to: "/", Icon: Home },
  { label: "Go to Work", to: "/work", Icon: Briefcase },
  { label: "Go to Accounts", to: "/accounts", Icon: Users },
  { label: "Go to Sessions", to: "/sessions", Icon: PlayCircle },
  { label: "Go to Automations", to: "/automations", Icon: Workflow },
  { label: "Go to Analytics", to: "/analytics", Icon: BarChart3 },
  { label: "Go to Developer Dashboard", to: "/dev", Icon: LayoutDashboard },
  { label: "Go to Identities", to: "/dev/identities", Icon: KeyRound },
  { label: "Go to Environments", to: "/dev/environments", Icon: Globe },
  { label: "Go to Executions", to: "/dev/executions", Icon: Activity },
  { label: "Go to Workflows", to: "/dev/workflows", Icon: GitBranch },
  { label: "Go to Replays", to: "/dev/replays", Icon: RefreshCw },
  { label: "Go to Settings", to: "/dev/settings", Icon: Settings },
];

export function CommandPalette() {
  const open = useCommandPaletteStore((s) => s.open);
  const setOpen = useCommandPaletteStore((s) => s.setOpen);
  const mode = useModeStore((s) => s.mode);
  const toggleMode = useModeStore((s) => s.toggle);
  const navigate = useNavigate();

  const { data: tasks } = useTasks();
  const { data: environments } = useEnvironments();
  const { data: executions } = useExecutions();

  const recentTasks = (tasks ?? []).slice(0, 5);
  const recentEnvs = (environments ?? []).slice(0, 5);
  const recentExecutions = [...(executions ?? [])]
    .sort(
      (a, b) =>
        new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    )
    .slice(0, 5);

  function go(to: string) {
    setOpen(false);
    navigate(to);
  }

  function handleModeToggle() {
    setOpen(false);
    toggleMode();
    navigate(mode === "user" ? "/dev" : "/");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="overflow-hidden p-0 max-w-2xl" aria-describedby={undefined}>
        <DialogTitle className="sr-only">Command Palette</DialogTitle>
        <DialogDescription className="sr-only">
          Search and navigate BrowserMind — type to filter commands, press Enter to run.
        </DialogDescription>
        <Command shouldFilter className="rounded-lg">
          <CommandInput placeholder="Search anything…" />
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>

            <CommandGroup heading="Navigate">
              {NAV_ITEMS.map(({ label, to, Icon }) => (
                <CommandItem
                  key={to}
                  value={label}
                  onSelect={() => go(to)}
                >
                  <Icon className="h-3.5 w-3.5 text-text-muted" />
                  <span>{label}</span>
                </CommandItem>
              ))}
            </CommandGroup>

            <CommandSeparator />

            <CommandGroup heading="Mode">
              <CommandItem
                value={
                  mode === "user"
                    ? "Switch to Developer Mode"
                    : "Switch to User Mode"
                }
                onSelect={handleModeToggle}
              >
                <TerminalSquare className="h-3.5 w-3.5 text-text-muted" />
                <span>
                  {mode === "user"
                    ? "Switch to Developer Mode"
                    : "Switch to User Mode"}
                </span>
              </CommandItem>
            </CommandGroup>

            {recentTasks.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Tasks">
                  {recentTasks.map((task) => (
                    <CommandItem
                      key={task.id}
                      value={`task ${task.goal} ${task.id}`}
                      onSelect={() =>
                        go(
                          mode === "user"
                            ? `/work/${task.id}`
                            : `/dev/tasks/${task.id}`,
                        )
                      }
                    >
                      <Briefcase className="h-3.5 w-3.5 text-text-muted" />
                      <span className="truncate">{task.goal}</span>
                      {task.environmentKey && (
                        <Tag variant="neutral" className="ml-auto">
                          {task.environmentKey}
                        </Tag>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

            {recentEnvs.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Environments">
                  {recentEnvs.map((env) => (
                    <CommandItem
                      key={env.key}
                      value={`env ${env.label} ${env.key}`}
                      onSelect={() =>
                        go(
                          mode === "user"
                            ? `/accounts/${env.key}`
                            : `/dev/environments`,
                        )
                      }
                    >
                      <Globe className="h-3.5 w-3.5 text-text-muted" />
                      <span>{env.label}</span>
                      <span className="ml-auto text-[11px] text-text-subtle">
                        {env.status}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

            {recentExecutions.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Recent Executions">
                  {recentExecutions.map((exec) => (
                    <CommandItem
                      key={exec.id}
                      value={`execution ${exec.id}`}
                      onSelect={() =>
                        go(
                          mode === "user"
                            ? `/sessions/${exec.id}`
                            : `/dev/executions/${exec.id}`,
                        )
                      }
                    >
                      <Activity className="h-3.5 w-3.5 text-text-muted" />
                      <span className="font-mono text-[11px] text-text-muted">
                        {exec.id}
                      </span>
                      <span className="ml-auto text-[11px] text-text-subtle">
                        {exec.state}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>

        <div className="flex items-center gap-3 border-t border-border-default bg-bg-elevated px-3 py-2 text-[11px] text-text-muted">
          <span className="flex items-center gap-1.5">
            <Kbd>↑↓</Kbd> Navigate
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd> Select
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>Esc</Kbd> Dismiss
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default CommandPalette;
