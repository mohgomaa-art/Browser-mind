import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { formatRelative, formatNumber } from "@/lib/utils";
import {
  useEnvironments,
  useIdentities,
  useExecutions,
  useTasks,
} from "@/lib/queries";
import type {
  EnvironmentStatus,
  IdentityStatus,
  ExecutionState,
} from "@/types";

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

function identityVariant(status: IdentityStatus) {
  switch (status) {
    case "active":
      return "success" as const;
    case "expired":
      return "warning" as const;
    case "requires_2fa":
      return "warning" as const;
    case "revoked":
      return "error" as const;
  }
}

function execVariant(state: ExecutionState) {
  switch (state) {
    case "running":
      return "accent" as const;
    case "paused":
    case "waiting":
      return "warning" as const;
    case "failed":
      return "error" as const;
    case "completed":
      return "success" as const;
    case "cancelled":
      return "neutral" as const;
    default:
      return "neutral" as const;
  }
}

export default function AccountDetailPage() {
  const { envKey = "" } = useParams<{ envKey: string }>();
  const navigate = useNavigate();
  const envQuery = useEnvironments();
  const identitiesQuery = useIdentities();
  const tasksQuery = useTasks();
  const execsQuery = useExecutions();

  const [actionDialog, setActionDialog] = useState<string | null>(null);

  const env = (envQuery.data ?? []).find((e) => e.key === envKey);
  const identity = (identitiesQuery.data ?? []).find(
    (i) => i.environmentKey === envKey,
  );

  const taskEnvMap = useMemo(() => {
    const m = new Map<string, string | undefined>();
    (tasksQuery.data ?? []).forEach((t) => m.set(t.id, t.environmentKey));
    return m;
  }, [tasksQuery.data]);

  const sessions = useMemo(() => {
    return (execsQuery.data ?? [])
      .filter((e) => taskEnvMap.get(e.taskId) === envKey)
      .sort(
        (a, b) =>
          new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
      )
      .slice(0, 10);
  }, [execsQuery.data, taskEnvMap, envKey]);

  if (envQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-64 rounded-md" />
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  if (envQuery.isError || !env) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          to="/accounts"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-3 w-3" /> Back to accounts
        </Link>
        <Card>
          <div className="p-6 flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-state-error" />
            <span className="text-sm text-text-muted">
              Couldn't load this account.
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
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/accounts"
          className="text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-3 w-3" /> Back to accounts
        </Link>
        <header className="flex items-end justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              {env.label}
            </h1>
            <p className="text-xs text-text-muted">{env.family}</p>
          </div>
          <Badge variant={statusVariant(env.status)}>
            {STATUS_LABEL[env.status]}
          </Badge>
        </header>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="identity">Identity</TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <Card>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 p-4 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Status</span>
                <Badge variant={statusVariant(env.status)}>
                  {STATUS_LABEL[env.status]}
                </Badge>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Start URL</span>
                <span className="font-mono text-xs text-text-primary truncate max-w-[16rem]">
                  {env.startUrl}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Last login</span>
                <span className="text-text-primary">
                  {env.lastLoginAt ? formatRelative(env.lastLoginAt) : "—"}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Cookies</span>
                <span className="text-text-primary">
                  {formatNumber(env.cookieCount ?? 0)}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Storage state</span>
                <span className="text-text-primary">
                  {env.storageStateBytes
                    ? `${(env.storageStateBytes / 1024).toFixed(1)} KB`
                    : "—"}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Replay</span>
                <Badge variant="neutral">{env.replayCompatibility}</Badge>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="identity" className="mt-4">
          {identity ? (
            <Card>
              <CardHeader>
                <CardTitle>{identity.identifier}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Status</span>
                    <Badge variant={identityVariant(identity.status)}>
                      {identity.status.replace("_", " ")}
                    </Badge>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Credential</span>
                    <span className="text-text-primary">
                      {identity.credentialType}
                    </span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Last used</span>
                    <span className="text-text-primary">
                      {identity.lastUsedAt
                        ? formatRelative(identity.lastUsedAt)
                        : "—"}
                    </span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Expires</span>
                    <span className="text-text-primary">
                      {identity.expiresAt
                        ? formatRelative(identity.expiresAt)
                        : "—"}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => setActionDialog("Provision")}
                  >
                    Provision
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setActionDialog("Rotate")}
                  >
                    Rotate
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setActionDialog("Reauthenticate")}
                  >
                    Reauthenticate
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setActionDialog("Disable")}
                  >
                    Disable
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <div className="p-6 text-center">
                <p className="text-sm text-text-muted">
                  No identity bound to this account yet.
                </p>
              </div>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          {sessions.length === 0 ? (
            <Card>
              <div className="p-6 text-center">
                <p className="text-sm text-text-muted">No sessions yet.</p>
              </div>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-2">
                <ul className="divide-y divide-border-default/60">
                  {sessions.map((s) => (
                    <li
                      key={s.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => navigate(`/sessions/${s.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") navigate(`/sessions/${s.id}`);
                      }}
                      className="flex items-center justify-between gap-3 py-2 px-2 rounded-md hover:bg-bg-elevated cursor-pointer"
                    >
                      <span className="text-sm text-text-primary">
                        {formatRelative(s.startedAt)}
                      </span>
                      <Badge variant={execVariant(s.state)}>{s.state}</Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <Card>
            <CardContent className="p-4 flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-text-muted">Storage path</label>
                <Input
                  defaultValue={`./agent_vault/${env.key}/storage.json`}
                  className="font-mono text-xs"
                />
              </div>
              <div className="flex items-center justify-between gap-3 rounded-md border border-border-default bg-bg-elevated p-3">
                <div>
                  <div className="text-sm text-text-primary">Headless</div>
                  <div className="text-xs text-text-muted">
                    Run this account's browser without a visible window.
                  </div>
                </div>
                <Switch />
              </div>
              <div>
                <Button variant="secondary" size="sm">
                  Reset state
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog
        open={actionDialog !== null}
        onOpenChange={(open) => !open && setActionDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{actionDialog}</DialogTitle>
            <DialogDescription>
              {actionDialog === "Provision" &&
                "Provisioning creates a fresh identity and stores credentials in the vault. Run `bm identity provision` from the CLI to complete this action."}
              {actionDialog === "Rotate" &&
                "Rotation replaces the active credential with a new one. Run `bm identity rotate` from the CLI or re-run the login flow in the Sessions tab."}
              {actionDialog === "Reauthenticate" &&
                "Launch a new browser session for this account to capture a fresh login state. Use the New Task dialog on the Home page with this environment selected."}
              {actionDialog === "Disable" &&
                "Disabling prevents this identity from being used in future executions. Run `bm identity disable` from the CLI."}
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
