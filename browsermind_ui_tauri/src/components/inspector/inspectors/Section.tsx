import * as React from "react";
import { cn } from "@/lib/cn";

export function Section({
  label,
  children,
  className,
  first,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  first?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        !first && "border-t border-border-default pt-3 mt-3",
        className,
      )}
    >
      <div className="text-[11px] uppercase tracking-wider text-text-subtle">
        {label}
      </div>
      <div className="text-sm text-text-primary">{children}</div>
    </div>
  );
}

export function NotFound({ kind }: { kind: string }) {
  return <div className="text-text-muted text-sm">{kind} not found</div>;
}

export function LoadingRows({ count = 5 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1.5">
          <div className="h-2 w-16 rounded bg-bg-elevated animate-pulse" />
          <div className="h-3 w-full rounded bg-bg-elevated animate-pulse" />
        </div>
      ))}
    </div>
  );
}
