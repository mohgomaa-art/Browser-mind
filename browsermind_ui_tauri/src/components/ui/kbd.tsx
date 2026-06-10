import * as React from "react";
import { cn } from "@/lib/cn";

const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 py-0.5 text-[11px] font-mono font-medium rounded border border-border-default bg-bg-elevated text-text-muted",
        className,
      )}
      {...props}
    />
  ),
);
Kbd.displayName = "Kbd";

export { Kbd };
