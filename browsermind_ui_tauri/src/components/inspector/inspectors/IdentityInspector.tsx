import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { Tag } from "@/components/ui";
import { formatRelative } from "@/lib/utils";
import { LoadingRows, NotFound, Section } from "./Section";
import type { IdentityStatus } from "@/types";

const STATE_VARIANT: Record<
  IdentityStatus,
  "active" | "warning" | "error" | "expired"
> = {
  active: "active",
  expired: "expired",
  revoked: "error",
  requires_2fa: "warning",
};

export function IdentityInspector({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["inspector", "identity", id],
    queryFn: () => adapter.identities.byId(id),
  });

  if (isLoading) return <LoadingRows />;
  if (!data) return <NotFound kind="Identity" />;

  return (
    <div>
      <Section first label="Identifier">
        <span className="font-mono">{data.identifier}</span>
      </Section>
      <Section label="Status">
        <Tag variant={STATE_VARIANT[data.status]}>{data.status}</Tag>
      </Section>
      <Section label="Credential Type">
        <Tag variant="neutral">{data.credentialType}</Tag>
      </Section>
      <Section label="Environment">
        <Tag variant="neutral">{data.environmentKey}</Tag>
      </Section>
      <Section label="Last Used">
        <span className="text-text-muted text-xs">
          {data.lastUsedAt ? formatRelative(data.lastUsedAt) : "Never"}
        </span>
      </Section>
      <Section label="Expires">
        <span className="text-text-muted text-xs">
          {data.expiresAt ? formatRelative(data.expiresAt) : "—"}
        </span>
      </Section>
      <Section label="Created">
        <span className="text-text-muted text-xs">
          {formatRelative(data.createdAt)}
        </span>
      </Section>
      <Section label="ID">
        <span className="font-mono text-xs text-text-subtle break-all">
          {data.id}
        </span>
      </Section>
    </div>
  );
}
