import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatNumber, formatRelative } from "@/lib/utils";
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
> = { full: "active", partial: "warning", none: "error" };

export default function EnvironmentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["environments"],
    queryFn: () => adapter.environments.list(),
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Environments</h1>
          <p className="text-xs text-text-muted">
            Browser environments and persistent state.
          </p>
        </div>
      </header>

      {isLoading ? (
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {(data ?? []).map((e) => (
            <Card key={e.key}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <CardTitle>{e.label}</CardTitle>
                    <span className="text-[11px] text-text-subtle font-mono">
                      {e.family}
                    </span>
                  </div>
                  <Tag variant={ENV_VARIANT[e.status]}>{e.status}</Tag>
                </div>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <Metric
                    label="Cookies"
                    value={e.cookieCount != null ? formatNumber(e.cookieCount) : "—"}
                  />
                  <Metric
                    label="Storage"
                    value={
                      e.storageStateBytes != null
                        ? `${(e.storageStateBytes / 1024).toFixed(1)} KB`
                        : "—"
                    }
                  />
                  <Metric
                    label="Last Login"
                    value={e.lastLoginAt ? formatRelative(e.lastLoginAt) : "Never"}
                  />
                  <Metric
                    label="Replay"
                    value={
                      <Tag variant={COMPAT_VARIANT[e.replayCompatibility]}>
                        {e.replayCompatibility}
                      </Tag>
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  <Button size="sm" variant="secondary">Open</Button>
                  <Button size="sm" variant="ghost">Login</Button>
                  <Button size="sm" variant="ghost">Export</Button>
                  <Button size="sm" variant="ghost">Clear</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-text-subtle">
        {label}
      </div>
      <div className="text-xs text-text-primary mt-0.5">{value}</div>
    </div>
  );
}
