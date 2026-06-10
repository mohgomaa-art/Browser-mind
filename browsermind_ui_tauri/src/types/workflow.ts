export type StepKind = 'start' | 'step' | 'branch' | 'condition' | 'end';

export interface WorkflowStep {
  seq: number;
  kind: StepKind;
  semanticName?: string;
  actionType?: string;
  targetRole?: string;
  targetName?: string;
  targetSelector?: string;
  children?: WorkflowStep[];
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  version: string;
  environmentKey?: string;
  steps: WorkflowStep[];
  createdAt: string;
  updatedAt: string;
}
