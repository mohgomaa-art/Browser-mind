import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const tagVariants = cva(
  "inline-flex items-center gap-1 rounded px-1.5 h-[18px] text-[11px] font-medium leading-none border",
  {
    variants: {
      variant: {
        active:
          "bg-state-success/15 border-state-success/25 text-state-success",
        expired:
          "bg-bg-elevated border-border-default text-text-muted",
        error:
          "bg-state-error/15 border-state-error/25 text-state-error",
        warning:
          "bg-state-warning/15 border-state-warning/25 text-state-warning",
        neutral:
          "bg-bg-elevated border-border-default text-text-primary",
        accent:
          "bg-accent/15 border-accent/25 text-accent",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

export interface TagProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof tagVariants> {}

function Tag({ className, variant, ...props }: TagProps) {
  return (
    <span className={cn(tagVariants({ variant }), className)} {...props} />
  );
}

export { Tag, tagVariants };
