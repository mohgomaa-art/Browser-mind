import { Outlet } from "react-router-dom";
import { ScrollArea } from "@/components/ui";
import { useInspectorStore } from "@/stores";
import { cn } from "@/lib/cn";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { ContextInspector } from "@/components/inspector/ContextInspector";
import { CommandPalette } from "@/components/command-palette/CommandPalette";
import { KeyboardShortcuts } from "@/components/layout/KeyboardShortcuts";
import { useSidecar } from "@/lib/sidecar";

export function RootLayout() {
  const open = useInspectorStore((s) => s.open);
  useSidecar();

  return (
    <div
      className={cn(
        "grid h-screen w-screen overflow-hidden bg-bg-base text-text-primary",
        "grid-rows-[44px_1fr_24px]",
        open
          ? "grid-cols-[260px_1fr_360px]"
          : "grid-cols-[260px_1fr]",
      )}
      style={{
        gridTemplateAreas: open
          ? `"topbar topbar topbar" "sidebar workspace inspector" "statusbar statusbar statusbar"`
          : `"topbar topbar" "sidebar workspace" "statusbar statusbar"`,
      }}
    >
      <div style={{ gridArea: "topbar" }} className="min-w-0">
        <TopBar />
      </div>
      <div style={{ gridArea: "sidebar" }} className="min-w-0 overflow-hidden">
        <Sidebar />
      </div>
      <main
        style={{ gridArea: "workspace" }}
        className="min-w-0 overflow-hidden"
      >
        <ScrollArea className="h-full w-full">
          <div className="p-6">
            <Outlet />
          </div>
        </ScrollArea>
      </main>
      {open && (
        <div
          style={{ gridArea: "inspector" }}
          className="min-w-0 overflow-hidden"
        >
          <ContextInspector />
        </div>
      )}
      <div style={{ gridArea: "statusbar" }} className="min-w-0">
        <StatusBar />
      </div>

      <CommandPalette />
      <KeyboardShortcuts />
    </div>
  );
}
