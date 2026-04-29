import { BaseAgent } from './base';
import type { Agent, Message } from '../types';
import type { LLMClient, ChatMessage } from '../llm';
import { personaIntroductionPrompt, personaResponsePrompt } from '../prompts';
import { detectLanguage } from '../services/language';

export interface PersonaData {
  id: string;
  name: string;
  role: string;
  background: string;
  stance: string;
  emoji?: string;
}

export class PersonaAgent extends BaseAgent {
  constructor(
    private data: PersonaData,
    private topic: string,
    private consensusMode: boolean = false
  ) {
    super(data.id, data.name, 'PERSONA', data.emoji || '👤');
  }

  toAgentModel(): Agent {
    return {
      id: this.data.id,
      name: this.data.name,
      role: this.data.role,
      background: this.data.background,
      stance: this.data.stance,
      type: 'PERSONA',
      emoji: this.data.emoji,
    };
  }

  async generateIntroduction(llm: LLMClient, model?: string): Promise<string> {
    const language = detectLanguage(this.topic);
    const prompt = personaIntroductionPrompt({
      name: this.data.name,
      role: this.data.role,
      background: this.data.background,
      stance: this.data.stance,
      topic: this.topic,
      language,
      consensusMode: this.consensusMode,
    });

    return llm.complete([{ role: 'system', content: prompt }], { model });
  }

  async generateResponse(
    llm: LLMClient,
    context: ChatMessage[],
    systemPrompt: string = '',
    model?: string
  ): Promise<string> {
    const language = detectLanguage(this.topic);
    const prompt = systemPrompt || personaResponsePrompt({
      name: this.data.name,
      role: this.data.role,
      background: this.data.background,
      stance: this.data.stance,
      topic: this.topic,
      language,
      consensusMode: this.consensusMode,
    });

    const messages: ChatMessage[] = [
      { role: 'system', content: prompt },
      ...context,
    ];

    return llm.complete(messages, { model });
  }
}
