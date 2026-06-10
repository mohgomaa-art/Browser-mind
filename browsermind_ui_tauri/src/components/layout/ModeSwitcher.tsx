import { useNavigate } from "react-router-dom";
import { useModeStore, type AppMode } from "@/stores";
import { cn } from "@/lib/cn";

export function ModeSwitcher() {
  const navigate = useNavigate();
  const mode = useModeStore((s) => s.mode);
  const setMode = useModeStore((s) => s.setMode);

  const select = (next: AppMode) => {
    if (next === mode) return;
    setMode(next);
    navigate(next === "developer" ? "/dev" : "/");
  };

  return (
    <div
      role="tablist"
      aria-label="App mode"
      className="inline-flex h-7 items-center rounded-md border border-border-default bg-bg-base p-0.5 text-[11px] uppercase tracking-wider"
    >
      <button
        role="tab"
        aria-selected={mode === "user"}
        onClick={() => select("user")}
        className={cn(
          "h-6 rounded-[5px] px-2.5 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
          mode === "user"
            ? "bg-bg-elevated text-text-primary"
            : "text-text-subtle hover:text-text-primary",
        )}
      >
        User
      </button>
      <button
        role="tab"
        aria-selected={mode === "developer"}
        onClick={() => select("developer")}
        className={cn(
          "h-6 rounded-[5px] px-2.5 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
          mode === "developer"
            ? "bg-bg-elevated text-text-primary"
            : "text-text-subtle hover:text-text-primary",
        )}
      >
        Dev
      </button>
    </div>
  );
}
