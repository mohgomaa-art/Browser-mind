import { useNavigate } from "react-router-dom";
import {
  Globe2,
  ExternalLink,
  LogIn,
  Wrench,
  RefreshCcw,
  Plug,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { formatRelative } from "@/lib/utils";
import { useEnvironments } from "@/lib/queries";
import type { Environment, EnvironmentStatus } from "@/types";

const STATUS_LABEL: Record<EnvironmentStatus, string> = {
  connected: "Connected",
  needs_login: "Needs Login",
  error: "Error",
  disconnected: "Disconnected",
};

function statusVariant(status: EnvironmentStatus) {
  switch (status) {
    case "connected":
      return "success" as const;
    case "needs_login":
      return "warning" as const;
    case "error":
      return "error" as const;
    case "disconnected":
      return "neutral" as const;
  }
}

function EnvironmentCard({ env }: { env: Environment }) {
  const navigate = useNavigate();

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/accounts/${env.key}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter") navigate(`/accounts/${env.key}`);
      }}
      className="hover:border-border-strong transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="h-7 w-7 rounded-md bg-bg-elevated border border-border-default flex items-center justify-center shrink-0">
              <Globe2 className="h-3.5 w-3.5 text-text-muted" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary truncate">
                {env.label}
              </div>
              <div className="text-[11px] text-text-muted">{env.family}</div>
            </div>
          </div>
          <Badge variant={statusVariant(env.status)}>
            {STATUS_LABEL[env.status]}
          </Badge>
        </div>

        <div className="flex flex-col gap-1 text-xs text-text-muted">
          <div>
            {env.lastLoginAt
              ? `Last used ${formatRelative(env.lastLoginAt)}`
              : "Never used"}
          </div>
          <div>Cookies: {env.cookieCount ?? 0}</div>
          <div>Replay: {env.replayCompatibility}</div>
        </div>

        <div
          className="flex items-center gap-2 pt-1"
          onClick={(e) => e.stopPropagation()}
        >
          {env.status === "connected" ? (
            <>
              <Button
                size="sm"
                onClick={() => {
                  if (env.startUrl) window.open(env.startUrl, "_blank");
                }}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigate(`/accounts/${env.key}`)}
              >
                <RefreshCcw className="h-3.5 w-3.5" />
                Reconnect
              </Button>
            </>
          ) : null}
          {env.status === "needs_login" ? (
            <Button size="sm" onClick={() => navigate(`/accounts/${env.key}`)}>
              <LogIn className="h-3.5 w-3.5" />
              Sign in
            </Button>
          ) : null}
          {env.status === "error" ? (
            <>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/accounts/${env.key}`)}
              >
                <Wrench className="h-3.5 w-3.5" />
                Diagnose
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigate(`/accounts/${env.key}`)}
              >
                <RefreshCcw className="h-3.5 w-3.5" />
                Reconnect
              </Button>
            </>
          ) : null}
          {env.status === "disconnected" ? (
            <Button
              size="sm"
              onClick={() => navigate(`/accounts/${env.key}`)}
            >
              <Plug className="h-3.5 w-3.5" />
              Connect
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

export default function AccountsPage() {
  const envQuery = useEnvironments();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Accounts</h1>
          <p className="text-xs text-text-muted">
            Browser environments and login state.
          </p>
        </div>
      </header>

      {envQuery.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-lg" />
          ))}
        </div>
      ) : envQuery.isError ? (
        <Card>
          <div className="p-4 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load accounts.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => envQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Card>
      ) : (envQuery.data ?? []).length === 0 ? (
        <Card>
          <div className="p-10 flex flex-col items-center gap-3">
            <Globe2 className="h-6 w-6 text-text-subtle" />
            <p className="text-sm text-text-muted">No accounts yet.</p>
            <Button size="sm">
              <Plug className="h-3.5 w-3.5" />
              Connect first account
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {(envQuery.data ?? []).map((env) => (
            <EnvironmentCard key={env.key} env={env} />
          ))}
        </div>
      )}
    </div>
  );
}
