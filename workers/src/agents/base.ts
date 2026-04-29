import type { Message, MessageType, Agent } from '../types';
import type { LLMClient, ChatMessage } from '../llm';
import { getWindowedMessages } from '../services/tokens';

export abstract class BaseAgent {
  id: string;
  name: string;
  type: Agent['type'];
  emoji: string;

  constructor(
    id: string,
    name: string,
    type: Agent['type'],
    emoji: string = '👤'
  ) {
    this.id = id;
    this.name = name;
    this.type = type;
    this.emoji = emoji;
  }

  abstract generateResponse(
    llm: LLMClient,
    context: ChatMessage[],
    systemPrompt: string,
    model?: string
  ): Promise<string>;

  protected createMessage(
    content: string,
    type: MessageType,
    agentName: string
  ): Message {
    return {
      id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      agentId: this.id,
      agentName,
      content,
      timestamp: new Date().toISOString(),
      type,
    };
  }

  protected getContext(
    messages: Message[],
    agentId: string,
    maxTokens: number = 8000
  ): ChatMessage[] {
    const filtered = messages
      .filter(m => m.type === 'AGENT' || m.type === 'MODERATOR')
      .map(m => ({
        role: (m.agentId === agentId ? 'assistant' : 'user') as 'assistant' | 'user',
        content: `[${m.type}] ${m.content}`,
      }));
    return getWindowedMessages(filtered, maxTokens);
  }
}
