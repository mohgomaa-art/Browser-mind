import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium leading-none border transition-colors",
  {
    variants: {
      variant: {
        default:
          "bg-bg-elevated border-border-default text-text-primary",
        neutral:
          "bg-bg-elevated border-border-default text-text-muted",
        accent:
          "bg-accent/15 border-accent/30 text-accent",
        success:
          "bg-state-success/15 border-state-success/25 text-state-success",
        warning:
          "bg-state-warning/15 border-state-warning/25 text-state-warning",
        error:
          "bg-state-error/15 border-state-error/25 text-state-error",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
