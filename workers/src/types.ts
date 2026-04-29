export type MessageType = 'AGENT' | 'MODERATOR' | 'FACT_CHECK' | 'SYSTEM';

export interface Message {
  id: string;
  agentId: string;
  agentName: string;
  content: string;
  timestamp: string;
  type: MessageType;
  sourceUrl?: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  background: string;
  stance: string;
  type: 'PERSONA' | 'MODERATOR' | 'FACT_CHECKER';
  emoji?: string;
}

export interface DiscussionConfig {
  maxMessages: number;
  factCheckEnabled: boolean;
  consensusMode: boolean;
  model?: string;
}

export type DiscussionState = 'GENERATING' | 'PANEL_READY' | 'DISCUSSION' | 'PAUSED' | 'COMPLETED' | 'ERROR';

export interface SessionData {
  id: string;
  topic: string;
  state: DiscussionState;
  phase: 'INTRODUCTION' | 'DISCUSSION' | 'COMPLETED';
  config: DiscussionConfig;
  agents: Agent[];
  messages: Message[];
  synthesis: string;
  moderatorName: string;
  createdAt: string;
  updatedAt: string;
  generationStatus: string;
  generationMessage: string;
}

export interface StartDiscussionRequest {
  topic: string;
  max_messages?: number;
  model?: string;
  fact_check_enabled?: boolean;
  consensus_mode?: boolean;
}

export interface PersonaUpdateRequest {
  name: string;
  role: string;
  background: string;
  stance: string;
  emoji?: string;
}
