import { NavLink, useParams } from "react-router-dom";
import {
  Button,
  Card,
  CardContent,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
} from "@/components/ui";
import { cn } from "@/lib/cn";

const SECTIONS = [
  { key: "general", label: "General" },
  { key: "storage", label: "Storage" },
  { key: "runtime", label: "Runtime" },
  { key: "security", label: "Security" },
  { key: "replay", label: "Replay" },
  { key: "experimental", label: "Experimental" },
  { key: "developer", label: "Developer Tools" },
] as const;

export default function SettingsPage() {
  const { section } = useParams<{ section?: string }>();
  const active = section ?? "general";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
        <p className="text-xs text-text-muted">
          Configure runtime, storage, and experimental flags.
        </p>
      </header>

      <div className="grid grid-cols-[200px_1fr] gap-6">
        <nav className="flex flex-col gap-0.5">
          {SECTIONS.map((s) => (
            <NavLink
              key={s.key}
              to={`/dev/settings/${s.key}`}
              className={({ isActive }) =>
                cn(
                  "h-8 px-3 rounded-md text-sm flex items-center transition-colors",
                  (isActive || active === s.key)
                    ? "bg-bg-elevated text-text-primary"
                    : "text-text-muted hover:bg-bg-elevated hover:text-text-primary",
                )
              }
              end
            >
              {s.label}
            </NavLink>
          ))}
        </nav>

        <div>
          {active === "general" && <GeneralSettings />}
          {active === "storage" && <StorageSettings />}
          {active === "runtime" && <RuntimeSettings />}
          {active === "security" && <SecuritySettings />}
          {active === "replay" && <ReplaySettings />}
          {active === "experimental" && <ExperimentalSettings />}
          {active === "developer" && <DeveloperSettings />}
        </div>
      </div>
    </div>
  );
}

function FormRow({
  title,
  desc,
  control,
}: {
  title: string;
  desc?: string;
  control: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-4 border-b border-border-default last:border-b-0">
      <div className="flex flex-col gap-1 min-w-0">
        <div className="text-sm">{title}</div>
        {desc && <div className="text-xs text-text-muted">{desc}</div>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-[11px] uppercase tracking-wider text-text-subtle mb-2">
          {title}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function GeneralSettings() {
  return (
    <Section title="General">
      <FormRow
        title="Theme"
        desc="The interface uses a dark theme only."
        control={
          <Select defaultValue="dark" disabled>
            <SelectTrigger className="w-32 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="dark">Dark</SelectItem>
            </SelectContent>
          </Select>
        }
      />
      <FormRow
        title="Language"
        desc="Display language."
        control={
          <Select defaultValue="en">
            <SelectTrigger className="w-32 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en">English</SelectItem>
              <SelectItem value="ar">Arabic</SelectItem>
            </SelectContent>
          </Select>
        }
      />
      <FormRow
        title="Telemetry"
        desc="Send anonymous usage events. Off by default."
        control={<Switch />}
      />
    </Section>
  );
}

function StorageSettings() {
  return (
    <Section title="Storage">
      <FormRow
        title="Storage path"
        desc="Where personas, identities, and ledgers live."
        control={
          <Input
            defaultValue="~/.browsermind"
            className="w-72 font-mono text-xs"
          />
        }
      />
      <FormRow
        title="Vacuum DB"
        desc="Compact the on-disk store."
        control={
          <Button size="sm" variant="secondary">
            Vacuum
          </Button>
        }
      />
      <FormRow
        title="Reset state"
        desc="Delete all persisted state. This cannot be undone."
        control={
          <Button size="sm" variant="destructive">
            Reset
          </Button>
        }
      />
    </Section>
  );
}

function RuntimeSettings() {
  return (
    <Section title="Runtime">
      <FormRow
        title="Concurrent executions"
        desc="Maximum executions running at once."
        control={
          <Input
            type="number"
            defaultValue={3}
            className="w-24 text-right tabular-nums"
          />
        }
      />
      <FormRow
        title="Headless default"
        desc="Run browsers without UI when launching."
        control={<Switch />}
      />
      <FormRow
        title="Recovery on transient errors"
        desc="Auto-retry failed steps that look transient."
        control={<Switch defaultChecked />}
      />
    </Section>
  );
}

function SecuritySettings() {
  return (
    <Section title="Security">
      <FormRow
        title="Auto-lock vault"
        desc="Lock the vault on inactivity."
        control={<Switch defaultChecked />}
      />
      <FormRow
        title="Vault timeout"
        desc="Idle period before re-prompting for unlock."
        control={
          <Select defaultValue="15m">
            <SelectTrigger className="w-32 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5m">5 minutes</SelectItem>
              <SelectItem value="15m">15 minutes</SelectItem>
              <SelectItem value="1h">1 hour</SelectItem>
              <SelectItem value="never">Never</SelectItem>
            </SelectContent>
          </Select>
        }
      />
      <FormRow
        title="Audit log retention"
        desc="How long to keep ledger entries."
        control={
          <Select defaultValue="90d">
            <SelectTrigger className="w-32 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">7 days</SelectItem>
              <SelectItem value="30d">30 days</SelectItem>
              <SelectItem value="90d">90 days</SelectItem>
              <SelectItem value="forever">Forever</SelectItem>
            </SelectContent>
          </Select>
        }
      />
    </Section>
  );
}

function ReplaySettings() {
  return (
    <Section title="Replay">
      <FormRow
        title="Default replay budget"
        desc="Maximum steps per replay run."
        control={
          <Input
            type="number"
            defaultValue={50}
            className="w-24 text-right tabular-nums"
          />
        }
      />
      <FormRow
        title="Auto-retry"
        desc="Retry the failing step once before reporting."
        control={<Switch defaultChecked />}
      />
      <FormRow
        title="Capture screenshots"
        desc="Take a snapshot on each step."
        control={<Switch defaultChecked />}
      />
    </Section>
  );
}

function ExperimentalSettings() {
  return (
    <Section title="Experimental">
      <FormRow
        title="Multi-tab workspace"
        desc="Open executions in separate workspace tabs."
        control={<Switch />}
      />
      <FormRow
        title="New executor"
        desc="Use the next-generation executor pipeline."
        control={<Switch />}
      />
      <FormRow
        title="Memory recall"
        desc="Use semantic memory to suggest next actions."
        control={<Switch />}
      />
    </Section>
  );
}

function DeveloperSettings() {
  return (
    <Section title="Developer Tools">
      <FormRow
        title="Show internal IDs"
        desc="Display UUIDs alongside human labels."
        control={<Switch defaultChecked />}
      />
      <FormRow
        title="Tauri command logging"
        desc="Log every IPC call in the console."
        control={<Switch />}
      />
      <FormRow
        title="Open devtools"
        desc="Open the underlying webview developer tools."
        control={
          <Button size="sm" variant="secondary">
            Open
          </Button>
        }
      />
    </Section>
  );
}
