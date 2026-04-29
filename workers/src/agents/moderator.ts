import type { Message, Agent } from '../types';
import type { LLMClient, ChatMessage } from '../llm';
import type { SessionStore } from '../services/session-store';
import {
  moderatorPrompt,
  synthesisPrompt,
  reflectionQuestionPrompt,
  reflectionResponsePrompt,
  interventionPrompt,
  convergencePrompt,
} from '../prompts';
import { detectLanguage } from '../services/language';
import { FactCheckerAgent } from './fact-checker';
import { PersonaAgent } from './persona';

export class ModeratorAgent {
  id: string;
  name: string;
  emoji = '🎙️';

  constructor(
    id: string,
    name: string,
    private llm: LLMClient,
    private factChecker: FactCheckerAgent
  ) {
    this.id = id;
    this.name = name;
  }

  selectNextSpeaker(personas: PersonaAgent[], messages: Message[]): PersonaAgent | null {
    if (personas.length === 0) return null;
    if (personas.length === 1) return personas[0];

    const agentMsgCount = new Map<string, number>();
    for (const m of messages) {
      if (m.type === 'AGENT') {
        agentMsgCount.set(m.agentId, (agentMsgCount.get(m.agentId) || 0) + 1);
      }
    }

    let minCount = Infinity;
    for (const p of personas) {
      const count = agentMsgCount.get(p.id) || 0;
      if (count < minCount) minCount = count;
    }

    const candidates = personas.filter(
      p => (agentMsgCount.get(p.id) || 0) === minCount
    );
    return candidates[Math.floor(Math.random() * candidates.length)];
  }

  async generateSynthesis(
    topic: string,
    messages: Message[],
    model?: string
  ): Promise<string> {
    const conversationText = messages
      .filter(m => m.type === 'AGENT' || m.type === 'MODERATOR')
      .map(m => `[${m.type}] ${m.content}`)
      .join('\n');

    const language = detectLanguage(topic);
    const prompt = synthesisPrompt(topic, conversationText, language);

    return this.llm.complete(
      [{ role: 'system', content: prompt }],
      { model }
    );
  }

  async generateReflection(
    personas: PersonaAgent[],
    topic: string,
    messages: Message[],
    model?: string
  ): Promise<Message[]> {
    const language = detectLanguage(topic);
    const question = await this.llm.complete(
      [{ role: 'system', content: reflectionQuestionPrompt(topic, language) }],
      { model }
    );

    const results: Message[] = [];

    results.push({
      id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      agentId: this.id,
      agentName: this.name,
      content: question,
      timestamp: new Date().toISOString(),
      type: 'MODERATOR',
    });

    for (const persona of personas) {
      const response = await persona.generateResponse(
        this.llm,
        [],
        reflectionResponsePrompt(
          persona.toAgentModel().name,
          persona.toAgentModel().role,
          persona.toAgentModel().background,
          persona.toAgentModel().stance,
          topic,
          language
        ),
        model
      );

      results.push({
        id: `msg_${crypto.randomUUID().slice(0, 8)}`,
        agentId: persona.id,
        agentName: persona.toAgentModel().name,
        content: response,
        timestamp: new Date().toISOString(),
        type: 'AGENT',
      });
    }

    return results;
  }

  async generateIntervention(
    type: string,
    topic: string,
    recentMessages: string,
    model?: string
  ): Promise<string> {
    const language = detectLanguage(topic);
    const prompt = interventionPrompt(type, topic, recentMessages, language);

    return this.llm.complete(
      [{ role: 'system', content: prompt }],
      { model }
    );
  }

  async checkConvergence(
    topic: string,
    messages: Message[],
    model?: string
  ): Promise<boolean> {
    const recent = messages
      .slice(-5)
      .map(m => `[${m.type}] ${m.content}`)
      .join('\n');

    const language = detectLanguage(topic);
    const prompt = convergencePrompt(topic, recent, language);

    try {
      const response = await this.llm.complete(
        [{ role: 'system', content: prompt }],
        { model }
      );
      const result = JSON.parse(response);
      return result.converged === true;
    } catch {
      return false;
    }
  }

  async runFactCheck(
    message: string,
    messages: Message[],
    model?: string
  ): Promise<void> {
    const claims = await this.factChecker.detectClaims(this.llm, message);
    if (claims.length === 0) return;

    const context = messages
      .slice(-10)
      .map(m => m.content)
      .join('\n');

    for (const claim of claims) {
      await this.factChecker.checkClaim(claim, context);
    }
  }
}
