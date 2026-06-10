import { createBrowserRouter, Link } from "react-router-dom";
import { RootLayout } from "@/components/layout/RootLayout";

import HomePage from "@/pages/user/HomePage";
import WorkPage from "@/pages/user/WorkPage";
import TaskDetailUserPage from "@/pages/user/TaskDetailPage";
import AccountsPage from "@/pages/user/AccountsPage";
import AccountDetailPage from "@/pages/user/AccountDetailPage";
import SessionsPage from "@/pages/user/SessionsPage";
import SessionTimelinePage from "@/pages/user/SessionTimelinePage";
import AutomationsPage from "@/pages/user/AutomationsPage";
import WorkflowViewerPage from "@/pages/user/WorkflowViewerPage";
import UserAnalyticsPage from "@/pages/user/AnalyticsPage";

import DashboardPage from "@/pages/dev/DashboardPage";
import PrincipalsPage from "@/pages/dev/PrincipalsPage";
import PersonasPage from "@/pages/dev/PersonasPage";
import PersonaDetailPage from "@/pages/dev/PersonaDetailPage";
import IdentitiesPage from "@/pages/dev/IdentitiesPage";
import EnvironmentsPage from "@/pages/dev/EnvironmentsPage";
import DevTasksPage from "@/pages/dev/TasksPage";
import DevTaskDetailPage from "@/pages/dev/TaskDetailPage";
import ExecutionsPage from "@/pages/dev/ExecutionsPage";
import ExecutionDetailPage from "@/pages/dev/ExecutionDetailPage";
import WorkflowsPage from "@/pages/dev/WorkflowsPage";
import WorkflowDetailPage from "@/pages/dev/WorkflowDetailPage";
import ReplaysPage from "@/pages/dev/ReplaysPage";
import ReplayDetailPage from "@/pages/dev/ReplayDetailPage";
import MemoryPage from "@/pages/dev/MemoryPage";
import LedgerPage from "@/pages/dev/LedgerPage";
import DevAnalyticsPage from "@/pages/dev/AnalyticsPage";
import TrainingPage from "@/pages/dev/TrainingPage";
import RecoveryPage from "@/pages/dev/RecoveryPage";
import BenchmarkPage from "@/pages/dev/BenchmarkPage";
import ExplorePage from "@/pages/dev/ExplorePage";
import SettingsPage from "@/pages/dev/SettingsPage";
import StudioPage from "@/pages/StudioPage";

function NotFoundPage() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="text-text-subtle text-[11px] uppercase tracking-wider">
          404
        </div>
        <div className="text-text-primary text-base">Not found</div>
        <div className="text-text-muted text-xs">
          The page you were looking for does not exist.
        </div>
        <Link
          to="/"
          className="text-accent text-xs hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded-sm"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "work", element: <WorkPage /> },
      { path: "work/:taskId", element: <TaskDetailUserPage /> },
      { path: "accounts", element: <AccountsPage /> },
      { path: "accounts/:envKey", element: <AccountDetailPage /> },
      { path: "sessions", element: <SessionsPage /> },
      { path: "sessions/:executionId", element: <SessionTimelinePage /> },
      { path: "automations", element: <AutomationsPage /> },
      { path: "automations/:workflowId", element: <WorkflowViewerPage /> },
      { path: "analytics", element: <UserAnalyticsPage /> },

      { path: "dev", element: <DashboardPage /> },
      { path: "dev/principals", element: <PrincipalsPage /> },
      { path: "dev/personas", element: <PersonasPage /> },
      { path: "dev/personas/:id", element: <PersonaDetailPage /> },
      { path: "dev/identities", element: <IdentitiesPage /> },
      { path: "dev/environments", element: <EnvironmentsPage /> },
      { path: "dev/tasks", element: <DevTasksPage /> },
      { path: "dev/tasks/:id", element: <DevTaskDetailPage /> },
      { path: "dev/executions", element: <ExecutionsPage /> },
      { path: "dev/executions/:id", element: <ExecutionDetailPage /> },
      { path: "dev/workflows", element: <WorkflowsPage /> },
      { path: "dev/workflows/:id", element: <WorkflowDetailPage /> },
      { path: "dev/replays", element: <ReplaysPage /> },
      { path: "dev/replays/:id", element: <ReplayDetailPage /> },
      { path: "dev/memory", element: <MemoryPage /> },
      { path: "dev/ledger", element: <LedgerPage /> },
      { path: "dev/analytics", element: <DevAnalyticsPage /> },
      { path: "dev/training", element: <TrainingPage /> },
      { path: "dev/recovery", element: <RecoveryPage /> },
      { path: "dev/benchmark", element: <BenchmarkPage /> },
      { path: "dev/explore", element: <ExplorePage /> },
      { path: "dev/settings", element: <SettingsPage /> },
      { path: "dev/settings/:section", element: <SettingsPage /> },
      { path: "studio", element: <StudioPage /> },

      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
