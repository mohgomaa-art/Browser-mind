import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Tag } from "@/components/ui";
import { formatNumber, formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { EnvironmentStatus, ReplayCompatibility } from "@/types";

const ENV_VARIANT: Record<
  EnvironmentStatus,
  "active" | "warning" | "error" | "expired"
> = {
  connected: "active",
  needs_login: "warning",
  error: "error",
  disconnected: "expired",
};

const COMPAT_VARIANT: Record<
  ReplayCompatibility,
  "active" | "warning" | "error"
> = {
  full: "active",
  partial: "warning",
  none: "error",
};

export function EnvironmentInspector({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["inspector", "environment", id],
    queryFn: () => adapter.environments.byKey(id),
  });

  if (isLoading) return <LoadingRows />;
  if (!data) return <NotFound kind="Environment" />;

  return (
    <div>
      <Section first label="Label">
        <span className="font-medium text-base">{data.label}</span>
      </Section>
      <Section label="Family">
        <Tag variant="neutral">{data.family}</Tag>
      </Section>
      <Section label="Status">
        <Tag variant={ENV_VARIANT[data.status]}>{data.status}</Tag>
      </Section>
      <Section label="Start URL">
        <span className="font-mono text-xs text-text-muted break-all">
          {data.startUrl}
        </span>
      </Section>
      <Section label="Cookies">
        {data.cookieCount != null ? formatNumber(data.cookieCount) : "—"}
      </Section>
      <Section label="Storage State">
        {data.storageStateBytes != null
          ? `${(data.storageStateBytes / 1024).toFixed(1)} KB`
          : "—"}
      </Section>
      <Section label="Last Login">
        <span className="text-text-muted text-xs">
          {data.lastLoginAt ? formatRelative(data.lastLoginAt) : "Never"}
        </span>
      </Section>
      <Section label="Replay Compatibility">
        <Tag variant={COMPAT_VARIANT[data.replayCompatibility]}>
          {data.replayCompatibility}
        </Tag>
      </Section>
    </div>
  );
}
