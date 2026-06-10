import { NavLink } from "react-router-dom";
import {
  Home,
  Briefcase,
  Users,
  PlayCircle,
  Workflow,
  BarChart3,
  LayoutDashboard,
  Crown,
  UserCircle,
  KeyRound,
  Globe,
  CheckSquare,
  Activity,
  GitBranch,
  RefreshCw,
  Brain,
  Scroll,
  LineChart,
  Settings as SettingsIcon,
  Terminal,
  ArrowLeft,
  BrainCircuit,
  ShieldCheck,
  BarChart2,
  Compass,
  Clapperboard,
  type LucideIcon,
} from "lucide-react";
import { useModeStore } from "@/stores";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const USER_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/work", label: "Work", icon: Briefcase },
  { to: "/accounts", label: "Accounts", icon: Users },
  { to: "/sessions", label: "Sessions", icon: PlayCircle },
  { to: "/automations", label: "Automations", icon: Workflow },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
] as const;

const DEV_ITEMS: readonly NavItem[] = [
  { to: "/dev", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/dev/principals", label: "Principals", icon: Crown },
  { to: "/dev/personas", label: "Personas", icon: UserCircle },
  { to: "/dev/identities", label: "Identities", icon: KeyRound },
  { to: "/dev/environments", label: "Environments", icon: Globe },
  { to: "/dev/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/dev/executions", label: "Executions", icon: Activity },
  { to: "/dev/workflows", label: "Workflows", icon: GitBranch },
  { to: "/dev/replays", label: "Replays", icon: RefreshCw },
  { to: "/dev/memory", label: "Memory", icon: Brain },
  { to: "/dev/ledger", label: "Ledger", icon: Scroll },
  { to: "/dev/analytics", label: "Analytics", icon: LineChart },
  { to: "/dev/training", label: "Training", icon: BrainCircuit },
  { to: "/dev/recovery", label: "Recovery", icon: ShieldCheck },
  { to: "/dev/benchmark", label: "Benchmark", icon: BarChart2 },
  { to: "/dev/explore", label: "Explore", icon: Compass },
  { to: "/studio", label: "Studio", icon: Clapperboard },
  { to: "/dev/settings", label: "Settings", icon: SettingsIcon },
] as const;

interface SidebarItemProps {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

function SidebarItem({ to, label, icon: Icon, end }: SidebarItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex h-8 items-center gap-2.5 rounded-md px-3 text-sm transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
          isActive
            ? "border-l-2 border-accent bg-bg-elevated text-text-primary"
            : "border-l-2 border-transparent text-text-muted hover:bg-bg-elevated hover:text-text-primary",
        )
      }
    >
      <Icon size={16} className="shrink-0" />
      <span className="truncate">{label}</span>
    </NavLink>
  );
}

export function Sidebar() {
  const mode = useModeStore((s) => s.mode);
  const toggleMode = useModeStore((s) => s.toggle);
  const items = mode === "developer" ? DEV_ITEMS : USER_ITEMS;

  return (
    <aside
      className="flex h-full w-[260px] flex-col border-r border-border-default bg-bg-panel p-2"
      aria-label="Primary navigation"
    >
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto">
        {items.map((item) => (
          <SidebarItem key={item.to} {...item} />
        ))}
      </nav>
      <div className="mt-2 border-t border-border-default pt-2">
        <button
          type="button"
          onClick={toggleMode}
          className={cn(
            "flex h-7 w-full items-center gap-2 rounded-md px-3 text-xs text-text-subtle transition-colors duration-150",
            "hover:bg-bg-elevated hover:text-text-primary",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
          )}
        >
          {mode === "user" ? (
            <>
              <Terminal size={14} className="shrink-0" />
              <span>Switch to Developer</span>
            </>
          ) : (
            <>
              <ArrowLeft size={14} className="shrink-0" />
              <span>User mode</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
