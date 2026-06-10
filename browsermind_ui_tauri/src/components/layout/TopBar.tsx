import { Link, useNavigate } from "react-router-dom";
import { Bell, Settings as SettingsIcon, Search } from "lucide-react";
import {
  Avatar,
  AvatarFallback,
  Badge,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Kbd,
  Tag,
} from "@/components/ui";
import { useCommandPaletteStore, useEnvironmentStore } from "@/stores";
import { useEnvironments } from "@/lib/queries";
import { cn } from "@/lib/cn";
import { ModeSwitcher } from "./ModeSwitcher";

const STATUS_DOT: Record<string, string> = {
  connected: "bg-state-success",
  needs_login: "bg-state-warning",
  error: "bg-state-error",
  disconnected: "bg-text-subtle",
};

export function TopBar() {
  const navigate = useNavigate();
  const openPalette = useCommandPaletteStore((s) => s.setOpen);
  const currentEnvKey = useEnvironmentStore((s) => s.currentEnvironmentKey);
  const { data: environments } = useEnvironments();
  const currentEnv = environments?.find((e) => e.key === currentEnvKey);

  return (
    <header
      className="flex h-11 items-center gap-3 border-b border-border-default bg-bg-panel px-4"
      role="banner"
    >
      <Link
        to="/"
        className="font-mono text-sm font-semibold tracking-tight text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded-sm"
      >
        BrowserMind
      </Link>

      <ModeSwitcher />

      <div className="flex-1" />

      <button
        type="button"
        onClick={() => openPalette(true)}
        className={cn(
          "group flex h-7 w-full max-w-md items-center gap-2 rounded-md border border-border-default bg-bg-base px-2.5 text-xs text-text-muted transition-colors",
          "hover:border-border-strong hover:text-text-primary",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
        )}
        aria-label="Open command palette"
      >
        <Search size={14} className="shrink-0" />
        <span className="flex-1 truncate text-left">Search anything…</span>
        <Kbd>⌘K</Kbd>
      </button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex h-7 items-center gap-2 rounded-md border border-transparent px-1.5 text-xs text-text-muted transition-colors hover:border-border-default hover:text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            aria-label="Persona menu"
          >
            <Avatar className="h-5 w-5">
              <AvatarFallback>You</AvatarFallback>
            </Avatar>
            <span className="hidden md:inline">You</span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => navigate("/dev/personas")}>
            Switch persona
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => navigate("/dev/personas")}>
            Profile
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {currentEnv && (
        <Tag>
          <span
            className={cn(
              "mr-1.5 inline-block h-1.5 w-1.5 rounded-full",
              STATUS_DOT[currentEnv.status] ?? "bg-text-subtle",
            )}
            aria-hidden
          />
          <span className="truncate max-w-[140px]">{currentEnv.label}</span>
        </Tag>
      )}

      <button
        type="button"
        className="relative flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        aria-label="Notifications"
      >
        <Bell size={14} />
        <span className="absolute -right-0.5 -top-0.5">
          <Badge variant="default">
            <span className="text-[9px] leading-none">·</span>
          </Badge>
        </span>
      </button>

      <Link
        to="/dev/settings"
        className="flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        aria-label="Settings"
      >
        <SettingsIcon size={14} />
      </Link>
    </header>
  );
}

