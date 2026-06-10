import type {
  AnalyticsMetrics,
  Environment,
  Execution,
  Identity,
  LedgerEvent,
  MemoryEntry,
  Persona,
  Principal,
  ReplayReport,
  Task,
  WorkflowTemplate,
} from "@/types";

// ─── Principals ──────────────────────────────────────────────────────────────
export const SEED_PRINCIPALS: Principal[] = [
  {
    id: "principal_root",
    name: "Mohamed Nile",
    createdAt: "2025-01-12T08:00:00Z",
  },
];

// ─── Personas ────────────────────────────────────────────────────────────────
export const SEED_PERSONAS: Persona[] = [
  {
    id: "persona_mohamed",
    principalId: "principal_root",
    name: "mohamed",
    displayName: "Mohamed",
    avatarUrl: undefined,
    bio: "Primary persona — work, applications, accounts.",
    createdAt: "2025-01-12T08:05:00Z",
  },
  {
    id: "persona_pilot",
    principalId: "principal_root",
    name: "pilot",
    displayName: "Pilot",
    avatarUrl: undefined,
    bio: "Sandbox persona used for replay drills and capability harvesting.",
    createdAt: "2025-02-04T10:30:00Z",
  },
];

// ─── Environments ────────────────────────────────────────────────────────────
export const SEED_ENVIRONMENTS: Environment[] = [
  {
    key: "env_github",
    label: "GitHub",
    family: "code-host",
    startUrl: "https://github.com",
    status: "connected",
    cookieCount: 14,
    storageStateBytes: 48_220,
    lastLoginAt: "2026-06-04T11:21:00Z",
    replayCompatibility: "full",
    iconHint: "github",
  },
  {
    key: "env_linkedin",
    label: "LinkedIn",
    family: "social-pro",
    startUrl: "https://www.linkedin.com",
    status: "connected",
    cookieCount: 22,
    storageStateBytes: 71_802,
    lastLoginAt: "2026-06-05T09:02:00Z",
    replayCompatibility: "partial",
    iconHint: "linkedin",
  },
  {
    key: "env_gmail",
    label: "Gmail",
    family: "email",
    startUrl: "https://mail.google.com",
    status: "needs_login",
    cookieCount: 6,
    storageStateBytes: 12_440,
    lastLoginAt: "2026-05-28T07:10:00Z",
    replayCompatibility: "partial",
    iconHint: "gmail",
  },
  {
    key: "env_openai",
    label: "OpenAI",
    family: "ai-platform",
    startUrl: "https://platform.openai.com",
    status: "connected",
    cookieCount: 11,
    storageStateBytes: 33_180,
    lastLoginAt: "2026-06-06T08:44:00Z",
    replayCompatibility: "full",
    iconHint: "openai",
  },
  {
    key: "env_huggingface",
    label: "Hugging Face",
    family: "ai-platform",
    startUrl: "https://huggingface.co",
    status: "error",
    cookieCount: 4,
    storageStateBytes: 9_120,
    lastLoginAt: "2026-05-19T16:42:00Z",
    replayCompatibility: "none",
    iconHint: "huggingface",
  },
];

// ─── Identities ──────────────────────────────────────────────────────────────
export const SEED_IDENTITIES: Identity[] = [
  {
    id: "ident_github_mohamed",
    personaId: "persona_mohamed",
    environmentKey: "env_github",
    identifier: "mohgomaa-art",
    status: "active",
    credentialType: "session",
    lastUsedAt: "2026-06-04T11:21:00Z",
    expiresAt: "2026-09-04T11:21:00Z",
    createdAt: "2025-08-02T10:00:00Z",
  },
  {
    id: "ident_linkedin_mohamed",
    personaId: "persona_mohamed",
    environmentKey: "env_linkedin",
    identifier: "in/mohamed-nile",
    status: "active",
    credentialType: "session",
    lastUsedAt: "2026-06-05T09:02:00Z",
    expiresAt: "2026-08-05T09:02:00Z",
    createdAt: "2025-09-15T14:25:00Z",
  },
  {
    id: "ident_gmail_mohamed",
    personaId: "persona_mohamed",
    environmentKey: "env_gmail",
    identifier: "mohamed.nile@gmail.com",
    status: "requires_2fa",
    credentialType: "session",
    lastUsedAt: "2026-05-28T07:10:00Z",
    expiresAt: "2026-06-28T07:10:00Z",
    createdAt: "2025-04-11T08:30:00Z",
  },
  {
    id: "ident_openai_mohamed",
    personaId: "persona_mohamed",
    environmentKey: "env_openai",
    identifier: "mohamed.nile@gmail.com",
    status: "active",
    credentialType: "oauth",
    lastUsedAt: "2026-06-06T08:44:00Z",
    expiresAt: "2026-07-06T08:44:00Z",
    createdAt: "2025-11-22T13:00:00Z",
  },
  {
    id: "ident_huggingface_pilot",
    personaId: "persona_pilot",
    environmentKey: "env_huggingface",
    identifier: "pilot-bm",
    status: "expired",
    credentialType: "apikey",
    lastUsedAt: "2026-05-19T16:42:00Z",
    expiresAt: "2026-05-30T00:00:00Z",
    createdAt: "2025-12-01T09:18:00Z",
  },
];

// ─── Tasks ───────────────────────────────────────────────────────────────────
export const SEED_TASKS: Task[] = [
  {
    id: "task_apply_openai",
    personaId: "persona_mohamed",
    environmentKey: "env_openai",
    goal: "Apply to OpenAI",
    state: "paused",
    progress: { current: 8, total: 12 },
    missingResources: ["Resume.pdf"],
    nextAction: "Upload Resume",
    lastEventAt: "2026-06-06T10:17:00Z",
    createdAt: "2026-06-06T10:14:00Z",
    updatedAt: "2026-06-06T10:17:00Z",
  },
  {
    id: "task_github_recovery",
    personaId: "persona_mohamed",
    environmentKey: "env_github",
    goal: "GitHub Account Recovery",
    state: "waiting",
    progress: { current: 1, total: 4 },
    missingResources: [],
    nextAction: "Enter verification code",
    lastEventAt: "2026-06-06T09:42:00Z",
    createdAt: "2026-06-06T09:38:00Z",
    updatedAt: "2026-06-06T09:42:00Z",
  },
  {
    id: "task_linkedin_profile",
    personaId: "persona_mohamed",
    environmentKey: "env_linkedin",
    goal: "LinkedIn Profile Update",
    state: "completed",
    progress: { current: 6, total: 6 },
    missingResources: [],
    nextAction: undefined,
    lastEventAt: "2026-06-05T15:20:00Z",
    createdAt: "2026-06-05T14:50:00Z",
    updatedAt: "2026-06-05T15:20:00Z",
  },
  {
    id: "task_gmail_cleanup",
    personaId: "persona_mohamed",
    environmentKey: "env_gmail",
    goal: "Gmail Cleanup",
    state: "running",
    progress: { current: 2, total: 5 },
    missingResources: [],
    nextAction: "Archive promotional emails",
    lastEventAt: "2026-06-06T10:05:00Z",
    createdAt: "2026-06-06T10:00:00Z",
    updatedAt: "2026-06-06T10:05:00Z",
  },
];

// ─── Executions ──────────────────────────────────────────────────────────────
export const SEED_EXECUTIONS: Execution[] = [
  {
    id: "exec_apply_openai_1",
    taskId: "task_apply_openai",
    workflowId: "wf_openai_apply",
    state: "paused",
    startedAt: "2026-06-06T10:15:00Z",
    endedAt: undefined,
    retryCount: 0,
    currentStepSeq: 4,
    snapshots: [
      {
        id: "snap_aoa_1",
        sequence: 1,
        kind: "pre_step",
        timestamp: "2026-06-06T10:15:00Z",
        evidenceUri: "snapshot://exec_apply_openai_1/1",
      },
      {
        id: "snap_aoa_2",
        sequence: 3,
        kind: "post_step",
        timestamp: "2026-06-06T10:16:30Z",
        evidenceUri: "snapshot://exec_apply_openai_1/3",
      },
      {
        id: "snap_aoa_3",
        sequence: 4,
        kind: "recovery",
        timestamp: "2026-06-06T10:17:05Z",
        evidenceUri: "snapshot://exec_apply_openai_1/4",
      },
    ],
    checkpoints: [
      {
        id: "ckpt_aoa_1",
        label: "Profile filled",
        timestamp: "2026-06-06T10:16:00Z",
        sequence: 3,
      },
    ],
    recoveryHistory: [
      {
        id: "rec_aoa_1",
        timestamp: "2026-06-06T10:17:10Z",
        reason: "Missing resource: Resume.pdf",
        outcome: "failed",
      },
    ],
    events: [
      {
        id: "ev_aoa_1",
        timestamp: "2026-06-06T10:15:00Z",
        kind: "navigate",
        summary: "Opened job page",
        detail: "Navigated to https://openai.com/careers/apply/se-12",
      },
      {
        id: "ev_aoa_2",
        timestamp: "2026-06-06T10:16:00Z",
        kind: "fill",
        summary: "Filled profile",
        detail: "Name, email, location, links populated from persona_mohamed",
      },
      {
        id: "ev_aoa_3",
        timestamp: "2026-06-06T10:17:00Z",
        kind: "fail",
        summary: "Resume missing",
        detail: "Required field 'Resume' has no attached resource for persona_mohamed",
      },
      {
        id: "ev_aoa_4",
        timestamp: "2026-06-06T10:17:10Z",
        kind: "pause",
        summary: "Execution paused",
        detail: "Awaiting user to upload Resume.pdf",
      },
    ],
  },
  {
    id: "exec_github_recovery_1",
    taskId: "task_github_recovery",
    workflowId: "wf_github_recovery",
    state: "waiting",
    startedAt: "2026-06-06T09:38:00Z",
    retryCount: 0,
    currentStepSeq: 2,
    snapshots: [
      {
        id: "snap_ghr_1",
        sequence: 1,
        kind: "pre_step",
        timestamp: "2026-06-06T09:38:30Z",
      },
    ],
    checkpoints: [],
    recoveryHistory: [],
    events: [
      {
        id: "ev_ghr_1",
        timestamp: "2026-06-06T09:38:00Z",
        kind: "navigate",
        summary: "Opened recovery page",
      },
      {
        id: "ev_ghr_2",
        timestamp: "2026-06-06T09:42:00Z",
        kind: "pause",
        summary: "Waiting for verification code",
      },
    ],
  },
  {
    id: "exec_linkedin_profile_1",
    taskId: "task_linkedin_profile",
    workflowId: "wf_linkedin_profile",
    state: "completed",
    startedAt: "2026-06-05T14:50:00Z",
    endedAt: "2026-06-05T15:20:00Z",
    retryCount: 0,
    currentStepSeq: 6,
    snapshots: [
      {
        id: "snap_lip_1",
        sequence: 1,
        kind: "pre_step",
        timestamp: "2026-06-05T14:50:30Z",
      },
      {
        id: "snap_lip_2",
        sequence: 6,
        kind: "post_step",
        timestamp: "2026-06-05T15:19:50Z",
      },
    ],
    checkpoints: [
      {
        id: "ckpt_lip_1",
        label: "Headline updated",
        timestamp: "2026-06-05T15:00:00Z",
        sequence: 2,
      },
    ],
    recoveryHistory: [],
    events: [
      {
        id: "ev_lip_1",
        timestamp: "2026-06-05T14:50:00Z",
        kind: "navigate",
        summary: "Opened profile editor",
      },
      {
        id: "ev_lip_2",
        timestamp: "2026-06-05T15:00:00Z",
        kind: "fill",
        summary: "Headline updated",
      },
      {
        id: "ev_lip_3",
        timestamp: "2026-06-05T15:20:00Z",
        kind: "verify",
        summary: "Save confirmed",
      },
    ],
  },
  {
    id: "exec_gmail_cleanup_1",
    taskId: "task_gmail_cleanup",
    workflowId: "wf_gmail_cleanup",
    state: "running",
    startedAt: "2026-06-06T10:00:00Z",
    retryCount: 0,
    currentStepSeq: 2,
    snapshots: [
      {
        id: "snap_gmc_1",
        sequence: 1,
        kind: "pre_step",
        timestamp: "2026-06-06T10:00:30Z",
      },
    ],
    checkpoints: [],
    recoveryHistory: [],
    events: [
      {
        id: "ev_gmc_1",
        timestamp: "2026-06-06T10:00:00Z",
        kind: "navigate",
        summary: "Opened inbox",
      },
      {
        id: "ev_gmc_2",
        timestamp: "2026-06-06T10:05:00Z",
        kind: "extract",
        summary: "Identified 18 promotional emails",
      },
    ],
  },
  {
    id: "exec_apply_openai_0",
    taskId: "task_apply_openai",
    workflowId: "wf_openai_apply",
    state: "failed",
    startedAt: "2026-06-05T18:00:00Z",
    endedAt: "2026-06-05T18:04:12Z",
    retryCount: 1,
    currentStepSeq: 2,
    snapshots: [
      {
        id: "snap_aoa0_1",
        sequence: 1,
        kind: "pre_step",
        timestamp: "2026-06-05T18:00:10Z",
      },
    ],
    checkpoints: [],
    recoveryHistory: [
      {
        id: "rec_aoa0_1",
        timestamp: "2026-06-05T18:03:50Z",
        reason: "Target drift: Apply button selector changed",
        outcome: "failed",
      },
    ],
    events: [
      {
        id: "ev_aoa0_1",
        timestamp: "2026-06-05T18:00:00Z",
        kind: "navigate",
        summary: "Opened careers page",
      },
      {
        id: "ev_aoa0_2",
        timestamp: "2026-06-05T18:04:00Z",
        kind: "fail",
        summary: "Apply button not found",
      },
    ],
  },
  {
    id: "exec_linkedin_profile_0",
    taskId: "task_linkedin_profile",
    workflowId: "wf_linkedin_profile",
    state: "completed",
    startedAt: "2026-05-30T10:00:00Z",
    endedAt: "2026-05-30T10:22:00Z",
    retryCount: 0,
    currentStepSeq: 6,
    snapshots: [],
    checkpoints: [],
    recoveryHistory: [],
    events: [
      {
        id: "ev_lip0_1",
        timestamp: "2026-05-30T10:00:00Z",
        kind: "navigate",
        summary: "Opened profile editor",
      },
      {
        id: "ev_lip0_2",
        timestamp: "2026-05-30T10:22:00Z",
        kind: "verify",
        summary: "Save confirmed",
      },
    ],
  },
  {
    id: "exec_gmail_cleanup_0",
    taskId: "task_gmail_cleanup",
    workflowId: "wf_gmail_cleanup",
    state: "completed",
    startedAt: "2026-06-04T09:30:00Z",
    endedAt: "2026-06-04T09:55:00Z",
    retryCount: 0,
    currentStepSeq: 5,
    snapshots: [],
    checkpoints: [],
    recoveryHistory: [],
    events: [
      {
        id: "ev_gmc0_1",
        timestamp: "2026-06-04T09:30:00Z",
        kind: "navigate",
        summary: "Opened inbox",
      },
      {
        id: "ev_gmc0_2",
        timestamp: "2026-06-04T09:55:00Z",
        kind: "verify",
        summary: "Archived 42 emails",
      },
    ],
  },
  {
    id: "exec_github_recovery_0",
    taskId: "task_github_recovery",
    workflowId: "wf_github_recovery",
    state: "failed",
    startedAt: "2026-06-05T08:00:00Z",
    endedAt: "2026-06-05T08:09:00Z",
    retryCount: 2,
    currentStepSeq: 3,
    snapshots: [],
    checkpoints: [],
    recoveryHistory: [
      {
        id: "rec_ghr0_1",
        timestamp: "2026-06-05T08:08:00Z",
        reason: "Identity requires 2FA",
        outcome: "failed",
      },
    ],
    events: [
      {
        id: "ev_ghr0_1",
        timestamp: "2026-06-05T08:00:00Z",
        kind: "navigate",
        summary: "Opened recovery page",
      },
      {
        id: "ev_ghr0_2",
        timestamp: "2026-06-05T08:09:00Z",
        kind: "fail",
        summary: "2FA challenge",
      },
    ],
  },
];

// ─── Workflows ───────────────────────────────────────────────────────────────
export const SEED_WORKFLOWS: WorkflowTemplate[] = [
  {
    id: "wf_openai_apply",
    name: "Apply to OpenAI",
    description: "Submit a job application on the OpenAI careers portal.",
    version: "1.4.0",
    environmentKey: "env_openai",
    createdAt: "2026-04-12T10:00:00Z",
    updatedAt: "2026-06-01T09:30:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Job Page",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Software Engineer",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Fill Profile",
        actionType: "fill",
        targetRole: "form",
        targetName: "Applicant Profile",
      },
      {
        seq: 3,
        kind: "step",
        semanticName: "Upload Resume",
        actionType: "upload",
        targetRole: "button",
        targetName: "Upload Resume",
      },
      {
        seq: 4,
        kind: "step",
        semanticName: "Answer Questions",
        actionType: "fill",
        targetRole: "form",
        targetName: "Screening Questions",
      },
      {
        seq: 5,
        kind: "step",
        semanticName: "Submit",
        actionType: "click",
        targetRole: "button",
        targetName: "Submit Application",
      },
      {
        seq: 6,
        kind: "step",
        semanticName: "Confirmation",
        actionType: "verify",
        targetRole: "heading",
        targetName: "Application received",
      },
      { seq: 7, kind: "end", semanticName: "End" },
    ],
  },
  {
    id: "wf_github_recovery",
    name: "GitHub Account Recovery",
    description: "Recover access via verification code flow.",
    version: "1.1.0",
    environmentKey: "env_github",
    createdAt: "2026-03-20T08:00:00Z",
    updatedAt: "2026-05-22T14:00:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Recovery Page",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Forgot password?",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Request Code",
        actionType: "click",
        targetRole: "button",
        targetName: "Send code",
      },
      {
        seq: 3,
        kind: "step",
        semanticName: "Enter Code",
        actionType: "fill",
        targetRole: "textbox",
        targetName: "Verification code",
      },
      {
        seq: 4,
        kind: "step",
        semanticName: "Reset Password",
        actionType: "fill",
        targetRole: "textbox",
        targetName: "New password",
      },
      { seq: 5, kind: "end", semanticName: "End" },
    ],
  },
  {
    id: "wf_linkedin_profile",
    name: "LinkedIn Profile Update",
    description: "Update headline, summary, and current role.",
    version: "2.0.1",
    environmentKey: "env_linkedin",
    createdAt: "2026-02-08T11:00:00Z",
    updatedAt: "2026-06-01T12:30:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Profile",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Me",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Edit Headline",
        actionType: "fill",
        targetRole: "textbox",
        targetName: "Headline",
      },
      {
        seq: 3,
        kind: "step",
        semanticName: "Edit Summary",
        actionType: "fill",
        targetRole: "textbox",
        targetName: "About",
      },
      {
        seq: 4,
        kind: "step",
        semanticName: "Save Changes",
        actionType: "click",
        targetRole: "button",
        targetName: "Save",
      },
      {
        seq: 5,
        kind: "step",
        semanticName: "Verify Saved",
        actionType: "verify",
        targetRole: "status",
        targetName: "Profile updated",
      },
      { seq: 6, kind: "end", semanticName: "End" },
    ],
  },
  {
    id: "wf_gmail_cleanup",
    name: "Gmail Cleanup",
    description: "Archive promotional emails older than 14 days.",
    version: "1.0.3",
    environmentKey: "env_gmail",
    createdAt: "2026-01-30T09:00:00Z",
    updatedAt: "2026-05-15T10:00:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Inbox",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Inbox",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Filter Promotions",
        actionType: "click",
        targetRole: "tab",
        targetName: "Promotions",
      },
      {
        seq: 3,
        kind: "step",
        semanticName: "Select All",
        actionType: "click",
        targetRole: "checkbox",
        targetName: "Select all",
      },
      {
        seq: 4,
        kind: "step",
        semanticName: "Archive",
        actionType: "click",
        targetRole: "button",
        targetName: "Archive",
      },
      { seq: 5, kind: "end", semanticName: "End" },
    ],
  },
  {
    id: "wf_openai_billing_check",
    name: "OpenAI Billing Check",
    description: "Pull current usage and remaining quota from OpenAI dashboard.",
    version: "1.0.0",
    environmentKey: "env_openai",
    createdAt: "2026-05-10T08:00:00Z",
    updatedAt: "2026-05-10T08:00:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Billing",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Billing",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Extract Usage",
        actionType: "extract",
        targetRole: "region",
        targetName: "Monthly usage",
      },
      { seq: 3, kind: "end", semanticName: "End" },
    ],
  },
  {
    id: "wf_huggingface_login",
    name: "Hugging Face Login",
    description: "Authenticate via personal access token.",
    version: "0.9.0",
    environmentKey: "env_huggingface",
    createdAt: "2026-02-15T08:00:00Z",
    updatedAt: "2026-04-10T09:00:00Z",
    steps: [
      { seq: 0, kind: "start", semanticName: "Start" },
      {
        seq: 1,
        kind: "step",
        semanticName: "Open Login",
        actionType: "navigate",
        targetRole: "link",
        targetName: "Sign in",
      },
      {
        seq: 2,
        kind: "step",
        semanticName: "Submit Token",
        actionType: "fill",
        targetRole: "textbox",
        targetName: "Access token",
      },
      { seq: 3, kind: "end", semanticName: "End" },
    ],
  },
];

// ─── Replays ─────────────────────────────────────────────────────────────────
function makeStepOutcomes(total: number, resolved: number): { seq: number; outcome: "RESOLVED_CORRECT" | "TARGET_CHANGED" | "AMBIGUOUS_TARGET" }[] {
  const out: { seq: number; outcome: "RESOLVED_CORRECT" | "TARGET_CHANGED" | "AMBIGUOUS_TARGET" }[] = [];
  for (let i = 1; i <= total; i++) {
    if (i <= resolved) {
      out.push({ seq: i, outcome: "RESOLVED_CORRECT" });
    } else if (i === resolved + 1) {
      out.push({ seq: i, outcome: "TARGET_CHANGED" });
    } else {
      out.push({ seq: i, outcome: "AMBIGUOUS_TARGET" });
    }
  }
  return out;
}

export const SEED_REPLAYS: ReplayReport[] = [
  {
    id: "replay_001",
    executionId: "exec_apply_openai_1",
    workflowId: "wf_openai_apply",
    environmentKey: "env_openai",
    status: "OK",
    resolutionRate: 0.92,
    falsePositiveRate: 0.03,
    taskCompletionRate: 0.83,
    criticalPath: ["Open Job Page", "Fill Profile", "Upload Resume", "Submit"],
    totalSteps: 7,
    resolvedSteps: 6,
    attemptedSteps: 7,
    stepOutcomes: makeStepOutcomes(7, 6),
    createdAt: "2026-06-06T10:30:00Z",
  },
  {
    id: "replay_002",
    workflowId: "wf_github_recovery",
    environmentKey: "env_github",
    status: "BLOCKED",
    resolutionRate: 0.5,
    falsePositiveRate: null,
    taskCompletionRate: null,
    criticalPath: ["Open Recovery Page", "Enter Code"],
    failureCategory: "IDENTITY_REQUIRES_2FA",
    failureReason: "User identity required 2FA challenge",
    totalSteps: 5,
    resolvedSteps: 2,
    attemptedSteps: 3,
    stepOutcomes: makeStepOutcomes(5, 2),
    createdAt: "2026-06-05T08:15:00Z",
  },
  {
    id: "replay_003",
    workflowId: "wf_linkedin_profile",
    environmentKey: "env_linkedin",
    status: "OK",
    resolutionRate: 0.96,
    falsePositiveRate: 0.02,
    taskCompletionRate: 0.94,
    criticalPath: ["Open Profile", "Edit Headline", "Save Changes"],
    totalSteps: 6,
    resolvedSteps: 6,
    attemptedSteps: 6,
    stepOutcomes: makeStepOutcomes(6, 6),
    createdAt: "2026-06-05T15:30:00Z",
  },
  {
    id: "replay_004",
    workflowId: "wf_gmail_cleanup",
    environmentKey: "env_gmail",
    status: "OK",
    resolutionRate: 0.88,
    falsePositiveRate: 0.05,
    taskCompletionRate: 0.8,
    criticalPath: ["Open Inbox", "Filter Promotions", "Archive"],
    totalSteps: 5,
    resolvedSteps: 4,
    attemptedSteps: 5,
    stepOutcomes: makeStepOutcomes(5, 4),
    createdAt: "2026-06-04T10:00:00Z",
  },
  {
    id: "replay_005",
    workflowId: "wf_openai_apply",
    environmentKey: "env_openai",
    status: "FAIL",
    resolutionRate: 0.45,
    falsePositiveRate: 0.08,
    taskCompletionRate: 0.2,
    criticalPath: ["Open Job Page", "Fill Profile"],
    failureCategory: "TARGET_DRIFT",
    failureReason: "Apply button selector changed across versions",
    totalSteps: 7,
    resolvedSteps: 3,
    attemptedSteps: 5,
    stepOutcomes: makeStepOutcomes(7, 3),
    createdAt: "2026-06-03T17:40:00Z",
  },
  {
    id: "replay_006",
    workflowId: "wf_openai_billing_check",
    environmentKey: "env_openai",
    status: "OK",
    resolutionRate: 0.94,
    falsePositiveRate: 0.01,
    taskCompletionRate: 0.92,
    criticalPath: ["Open Billing", "Extract Usage"],
    totalSteps: 3,
    resolvedSteps: 3,
    attemptedSteps: 3,
    stepOutcomes: makeStepOutcomes(3, 3),
    createdAt: "2026-06-02T12:00:00Z",
  },
  {
    id: "replay_007",
    workflowId: "wf_huggingface_login",
    environmentKey: "env_huggingface",
    status: "FAIL",
    resolutionRate: 0.33,
    falsePositiveRate: 0.1,
    taskCompletionRate: 0.0,
    criticalPath: ["Open Login"],
    failureCategory: "IDENTITY_EXPIRED",
    failureReason: "Personal access token expired",
    totalSteps: 3,
    resolvedSteps: 1,
    attemptedSteps: 2,
    stepOutcomes: makeStepOutcomes(3, 1),
    createdAt: "2026-05-30T16:20:00Z",
  },
  {
    id: "replay_008",
    workflowId: "wf_linkedin_profile",
    environmentKey: "env_linkedin",
    status: "OK",
    resolutionRate: 0.82,
    falsePositiveRate: 0.06,
    taskCompletionRate: 0.75,
    criticalPath: ["Open Profile", "Edit Summary"],
    totalSteps: 6,
    resolvedSteps: 5,
    attemptedSteps: 6,
    stepOutcomes: makeStepOutcomes(6, 5),
    createdAt: "2026-05-28T13:00:00Z",
  },
  {
    id: "replay_009",
    workflowId: "wf_gmail_cleanup",
    environmentKey: "env_gmail",
    status: "FAIL",
    resolutionRate: 0.5,
    falsePositiveRate: 0.12,
    taskCompletionRate: 0.3,
    criticalPath: ["Open Inbox"],
    failureCategory: "NAME_DRIFT",
    failureReason: "Promotions tab name changed",
    totalSteps: 5,
    resolvedSteps: 2,
    attemptedSteps: 4,
    stepOutcomes: makeStepOutcomes(5, 2),
    createdAt: "2026-05-26T09:30:00Z",
  },
  {
    id: "replay_010",
    workflowId: "wf_openai_apply",
    environmentKey: "env_openai",
    status: "OK",
    resolutionRate: 0.86,
    falsePositiveRate: 0.04,
    taskCompletionRate: 0.78,
    criticalPath: ["Open Job Page", "Fill Profile", "Upload Resume"],
    totalSteps: 7,
    resolvedSteps: 6,
    attemptedSteps: 7,
    stepOutcomes: makeStepOutcomes(7, 6),
    createdAt: "2026-05-24T11:00:00Z",
  },
  {
    id: "replay_011",
    workflowId: "wf_github_recovery",
    environmentKey: "env_github",
    status: "OK",
    resolutionRate: 0.78,
    falsePositiveRate: 0.07,
    taskCompletionRate: 0.65,
    criticalPath: ["Open Recovery Page", "Request Code"],
    totalSteps: 5,
    resolvedSteps: 4,
    attemptedSteps: 5,
    stepOutcomes: makeStepOutcomes(5, 4),
    createdAt: "2026-05-22T14:30:00Z",
  },
  {
    id: "replay_012",
    workflowId: "wf_linkedin_profile",
    environmentKey: "env_linkedin",
    status: "FAIL",
    resolutionRate: 0.6,
    falsePositiveRate: 0.09,
    taskCompletionRate: 0.4,
    criticalPath: ["Open Profile"],
    failureCategory: "PORTAL_FAILURE",
    failureReason: "Portal returned 503 mid-flow",
    totalSteps: 6,
    resolvedSteps: 3,
    attemptedSteps: 5,
    stepOutcomes: makeStepOutcomes(6, 3),
    createdAt: "2026-05-20T10:15:00Z",
  },
];

// ─── Ledger ──────────────────────────────────────────────────────────────────
function genLedger(): LedgerEvent[] {
  const events: LedgerEvent[] = [];
  const kinds: Array<"mutation" | "execution" | "policy"> = [
    "mutation",
    "execution",
    "policy",
  ];
  const entityTypes = [
    "task",
    "execution",
    "identity",
    "environment",
    "workflow",
    "persona",
  ];
  const taskIds = SEED_TASKS.map((t) => t.id);
  const execIds = SEED_EXECUTIONS.map((e) => e.id);
  const identIds = SEED_IDENTITIES.map((i) => i.id);
  const envKeys = SEED_ENVIRONMENTS.map((e) => e.key);
  const wfIds = SEED_WORKFLOWS.map((w) => w.id);
  const personaIds = SEED_PERSONAS.map((p) => p.id);

  const start = new Date("2026-06-06T10:30:00Z").getTime();
  for (let i = 0; i < 50; i++) {
    const ts = new Date(start - i * 6 * 60 * 60 * 1000).toISOString();
    const kind = kinds[i % kinds.length]!;
    const entityType = entityTypes[i % entityTypes.length]!;
    let entityId = "unknown";
    let environmentKey: string | undefined;
    const personaId = personaIds[i % personaIds.length];
    switch (entityType) {
      case "task":
        entityId = taskIds[i % taskIds.length]!;
        break;
      case "execution":
        entityId = execIds[i % execIds.length]!;
        break;
      case "identity":
        entityId = identIds[i % identIds.length]!;
        environmentKey = envKeys[i % envKeys.length];
        break;
      case "environment":
        entityId = envKeys[i % envKeys.length]!;
        environmentKey = entityId;
        break;
      case "workflow":
        entityId = wfIds[i % wfIds.length]!;
        break;
      case "persona":
        entityId = personaIds[i % personaIds.length]!;
        break;
    }
    events.push({
      id: `ledger_${String(i + 1).padStart(3, "0")}`,
      timestamp: ts,
      kind,
      entityType,
      entityId,
      personaId,
      environmentKey,
      summary: `${kind} on ${entityType} ${entityId}`,
    });
  }
  return events;
}

export const SEED_LEDGER: LedgerEvent[] = genLedger();

// ─── Memory ──────────────────────────────────────────────────────────────────
export const SEED_MEMORY: MemoryEntry[] = [
  {
    id: "mem_001",
    type: "episodic",
    title: "Applied to OpenAI SE role",
    content:
      "Started application to Software Engineer role on 2026-06-06. Paused at resume upload.",
    relatedEntities: [
      { type: "task", id: "task_apply_openai", label: "Apply to OpenAI" },
      { type: "environment", id: "env_openai", label: "OpenAI" },
    ],
    tags: ["job-application", "openai"],
    createdAt: "2026-06-06T10:17:30Z",
  },
  {
    id: "mem_002",
    type: "semantic",
    title: "OpenAI portal: Apply button drifts under hash builds",
    content:
      "Selector `button[data-test-id=apply]` is unstable across weekly hash builds; prefer accessible role.",
    relatedEntities: [
      { type: "workflow", id: "wf_openai_apply", label: "Apply to OpenAI" },
    ],
    tags: ["target-drift", "openai"],
    createdAt: "2026-06-03T18:00:00Z",
  },
  {
    id: "mem_003",
    type: "procedural",
    title: "Recover GitHub access via SMS code",
    content:
      "Step sequence: open recovery → request code → enter code → reset password. Requires phone access.",
    relatedEntities: [
      { type: "workflow", id: "wf_github_recovery", label: "GitHub Account Recovery" },
    ],
    tags: ["recovery", "github"],
    createdAt: "2026-05-22T14:00:00Z",
  },
  {
    id: "mem_004",
    type: "episodic",
    title: "Updated LinkedIn headline",
    content:
      "Headline changed to 'Building BrowserMind — a personal digital OS'. Save confirmed at 15:20 UTC.",
    relatedEntities: [
      { type: "task", id: "task_linkedin_profile", label: "LinkedIn Profile Update" },
    ],
    tags: ["linkedin", "profile"],
    createdAt: "2026-06-05T15:21:00Z",
  },
  {
    id: "mem_005",
    type: "semantic",
    title: "Gmail Promotions tab can be renamed by experiments",
    content:
      "A/B experiments rename 'Promotions' → 'Updates'. Use role+name fuzzy match.",
    relatedEntities: [
      { type: "workflow", id: "wf_gmail_cleanup", label: "Gmail Cleanup" },
    ],
    tags: ["name-drift", "gmail"],
    createdAt: "2026-05-26T10:00:00Z",
  },
  {
    id: "mem_006",
    type: "procedural",
    title: "Standard application form fill order",
    content:
      "Fill name → email → location → portfolio links → resume → screening questions, in that order.",
    relatedEntities: [
      { type: "workflow", id: "wf_openai_apply", label: "Apply to OpenAI" },
    ],
    tags: ["form-fill"],
    createdAt: "2026-04-12T10:30:00Z",
  },
  {
    id: "mem_007",
    type: "episodic",
    title: "Hugging Face token expired",
    content:
      "Personal access token for pilot expired on 2026-05-30. Need to regenerate.",
    relatedEntities: [
      { type: "identity", id: "ident_huggingface_pilot", label: "pilot-bm @ HF" },
    ],
    tags: ["identity", "expired"],
    createdAt: "2026-05-30T16:21:00Z",
  },
  {
    id: "mem_008",
    type: "semantic",
    title: "Gmail requires 2FA after extended cookie drift",
    content:
      "Once Gmail session age > 7 days without interactive use, 2FA challenge re-arms.",
    relatedEntities: [
      { type: "environment", id: "env_gmail", label: "Gmail" },
    ],
    tags: ["2fa", "gmail"],
    createdAt: "2026-05-28T07:30:00Z",
  },
  {
    id: "mem_009",
    type: "procedural",
    title: "Save → Verify pattern",
    content:
      "After any save action, follow with a verify step that asserts the saved state via accessible status role.",
    relatedEntities: [],
    tags: ["pattern", "verify"],
    createdAt: "2026-02-08T11:30:00Z",
  },
  {
    id: "mem_010",
    type: "episodic",
    title: "Archived 42 promotional emails",
    content: "Gmail cleanup completed: archived 42 emails older than 14 days.",
    relatedEntities: [
      { type: "task", id: "task_gmail_cleanup", label: "Gmail Cleanup" },
    ],
    tags: ["gmail", "cleanup"],
    createdAt: "2026-06-04T09:55:30Z",
  },
  {
    id: "mem_011",
    type: "semantic",
    title: "OpenAI requires resume PDF, not DOCX",
    content:
      "Upload control validates extension client-side; only .pdf, .doc, .docx accepted; prefer .pdf.",
    relatedEntities: [
      { type: "workflow", id: "wf_openai_apply", label: "Apply to OpenAI" },
    ],
    tags: ["validation", "openai"],
    createdAt: "2026-06-06T10:18:00Z",
  },
  {
    id: "mem_012",
    type: "procedural",
    title: "Re-login via session storage replay",
    content:
      "On `needs_login`, attempt cookie replay first, then OAuth, then password.",
    relatedEntities: [],
    tags: ["login", "pattern"],
    createdAt: "2026-03-12T08:00:00Z",
  },
  {
    id: "mem_013",
    type: "episodic",
    title: "GitHub recovery blocked by 2FA",
    content:
      "Recovery flow on 2026-06-05 blocked at 2FA gate; no SMS available at the time.",
    relatedEntities: [
      { type: "execution", id: "exec_github_recovery_0", label: "GitHub Recovery #0" },
    ],
    tags: ["github", "2fa"],
    createdAt: "2026-06-05T08:10:00Z",
  },
  {
    id: "mem_014",
    type: "semantic",
    title: "LinkedIn 503s are transient",
    content:
      "Portal 503 mid-flow usually clears within 60s; retry with backoff before flagging PORTAL_FAILURE.",
    relatedEntities: [
      { type: "environment", id: "env_linkedin", label: "LinkedIn" },
    ],
    tags: ["linkedin", "retry"],
    createdAt: "2026-05-20T10:30:00Z",
  },
  {
    id: "mem_015",
    type: "procedural",
    title: "Snapshot before any destructive click",
    content:
      "Always take a pre_step snapshot before clicks that mutate server state.",
    relatedEntities: [],
    tags: ["snapshot", "safety"],
    createdAt: "2026-01-30T09:30:00Z",
  },
  {
    id: "mem_016",
    type: "episodic",
    title: "First Pilot persona task run",
    content: "Pilot persona executed first replay drill on Hugging Face.",
    relatedEntities: [
      { type: "persona", id: "persona_pilot", label: "Pilot" },
    ],
    tags: ["pilot", "drill"],
    createdAt: "2026-02-05T09:00:00Z",
  },
  {
    id: "mem_017",
    type: "semantic",
    title: "Critical path predicts task completion within 3%",
    content:
      "Across last 60 runs, critical-path resolution rate predicts final task completion within ±3%.",
    relatedEntities: [],
    tags: ["analytics", "replay"],
    createdAt: "2026-06-01T08:00:00Z",
  },
  {
    id: "mem_018",
    type: "procedural",
    title: "When paused, surface missing resources first",
    content:
      "In USER mode, paused tasks should show a single primary action that resolves the first missing resource.",
    relatedEntities: [],
    tags: ["ux", "user-mode"],
    createdAt: "2026-05-15T12:00:00Z",
  },
  {
    id: "mem_019",
    type: "episodic",
    title: "Billing check baseline established",
    content: "OpenAI billing check workflow ran clean; usage at 38% of monthly quota.",
    relatedEntities: [
      { type: "workflow", id: "wf_openai_billing_check", label: "OpenAI Billing Check" },
    ],
    tags: ["billing", "openai"],
    createdAt: "2026-06-02T12:05:00Z",
  },
  {
    id: "mem_020",
    type: "semantic",
    title: "Identity drift correlates with weekend gaps",
    content:
      "Sessions unused for >48h over weekends show 2.3x higher 2FA re-arm rate.",
    relatedEntities: [],
    tags: ["identity", "drift"],
    createdAt: "2026-05-10T08:00:00Z",
  },
];

// ─── Analytics ───────────────────────────────────────────────────────────────
function genTrend(): { date: string; resolutionRate: number; fpr: number }[] {
  const out: { date: string; resolutionRate: number; fpr: number }[] = [];
  const baseRR = 0.82;
  const baseFPR = 0.04;
  const end = new Date("2026-06-06T00:00:00Z").getTime();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(end - i * 24 * 60 * 60 * 1000);
    const wobble = ((i * 7) % 5) / 100;
    out.push({
      date: d.toISOString().slice(0, 10),
      resolutionRate: Math.round((baseRR + wobble - 0.02) * 1000) / 1000,
      fpr: Math.round((baseFPR + wobble / 4) * 1000) / 1000,
    });
  }
  return out;
}

export const SEED_ANALYTICS: AnalyticsMetrics = {
  replayResolutionRate: 0.82,
  falsePositiveRate: 0.04,
  taskCompletionRate: 0.71,
  identityDrift: 0.06,
  replayCeiling: 0.94,
  environmentStability: 0.88,
  failureOntology: [
    { category: "TARGET_DRIFT", share: 0.12 },
    { category: "NAME_DRIFT", share: 0.04 },
    { category: "PORTAL_FAILURE", share: 0.02 },
    { category: "AMBIGUOUS_TARGET", share: 0.03 },
    { category: "NO_VISIBLE_SIGNAL", share: 0.02 },
    { category: "IDENTITY_EXPIRED", share: 0.02 },
    { category: "IDENTITY_REQUIRES_2FA", share: 0.015 },
    { category: "ENVIRONMENT_FAILURE", share: 0.01 },
    { category: "OTHER", share: 0.015 },
  ],
  trend: genTrend(),
};

