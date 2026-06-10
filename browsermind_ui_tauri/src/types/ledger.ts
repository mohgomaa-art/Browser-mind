export type LedgerKind = 'mutation' | 'execution' | 'policy';

export interface LedgerEvent {
  id: string;
  timestamp: string;
  kind: LedgerKind;
  entityType: string;
  entityId: string;
  personaId?: string;
  environmentKey?: string;
  before?: unknown;
  after?: unknown;
  summary: string;
}
