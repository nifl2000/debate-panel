// Discussion State Enum
export enum DiscussionState {
  ACTIVE = 'ACTIVE',
  PAUSED = 'PAUSED',
  COMPLETED = 'COMPLETED',
  ERROR = 'ERROR',
}

// Discussion Configuration
export interface DiscussionConfig {
  maxMessages: number;
  language: string;
  model: string;
}

// Agent Type Enum
export enum AgentType {
  PERSONA = 'PERSONA',
  MODERATOR = 'MODERATOR',
  FACT_CHECKER = 'FACT_CHECKER',
}

// Agent
export interface Agent {
  id: string;
  name: string;
  role: string;
  background: string;
  stance: string;
  type: AgentType;
}

// Message Type Enum
export enum MessageType {
  AGENT = 'AGENT',
  FACT_CHECK = 'FACT_CHECK',
  MODERATOR = 'MODERATOR',
  SYSTEM = 'SYSTEM',
}

// Message
export interface Message {
  id: string;
  agentId: string;
  content: string;
  timestamp: string;
  type: MessageType;
}

// Discussion Session
export interface DiscussionSession {
  id: string;
  topic: string;
  state: DiscussionState;
  conversationLog: Message[];
  agents: Agent[];
  config: DiscussionConfig;
}

// Export Format Enum
export enum ExportFormat {
  TEXT = 'TEXT',
  MARKDOWN = 'MARKDOWN',
  PDF = 'PDF',
}