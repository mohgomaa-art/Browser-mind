export type MemoryType = 'episodic' | 'semantic' | 'procedural';

export interface MemoryRelation {
  type: string;
  id: string;
  label: string;
}

export interface MemoryEntry {
  id: string;
  type: MemoryType;
  title: string;
  content: string;
  relatedEntities: MemoryRelation[];
  tags?: string[];
  createdAt: string;
}
