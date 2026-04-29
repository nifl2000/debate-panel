import type { Agent } from '../types';
import type { LLMClient } from '../llm';
import { panelGenerationPrompt } from '../prompts';
import { detectLanguage } from './language';

export class PanelGenerator {
  constructor(private llm: LLMClient) {}

  async generate(topic: string, consensusMode: boolean = false, model?: string): Promise<Agent[]> {
    const language = detectLanguage(topic);
    const prompt = panelGenerationPrompt(topic, language);

    try {
      const response = await this.llm.complete(
        [{ role: 'user', content: prompt }],
        { model }
      );

      const personas = this.parsePersonas(response, language);
      return personas;
    } catch (error) {
      console.error('Panel generation failed:', error);
      return this.fallbackPersonas(topic);
    }
  }

  private parsePersonas(response: string, language: string): Agent[] {
    let cleaned = response.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.split('\n').slice(1, -1).join('\n');
    }

    const match = cleaned.match(/\[[\s\S]*\]/);
    if (match) {
      const data = JSON.parse(match[0]);
      if (Array.isArray(data)) {
        return data.slice(0, 7).map((p: any, i: number) => ({
          id: `persona_${i}`,
          name: p.name || `Persona ${i + 1}`,
          role: p.role || 'Expert',
          background: p.background || 'Professional in the field',
          stance: p.stance || 'Neutral',
          type: 'PERSONA' as const,
          emoji: p.emoji || '👤',
        }));
      }
    }

    return this.fallbackPersonas('topic');
  }

  private fallbackPersonas(topic: string): Agent[] {
    return [
      { id: 'persona_0', name: 'Dr. Anna Schmidt', role: 'Expert', background: 'Subject matter expert', stance: 'Evidence-based approach', type: 'PERSONA', emoji: '👩‍🔬' },
      { id: 'persona_1', name: 'Thomas Weber', role: 'Skeptic', background: 'Questions assumptions', stance: 'Needs more proof', type: 'PERSONA', emoji: '🤔' },
      { id: 'persona_2', name: 'Lisa Müller', role: 'Pragmatist', background: 'Focuses on practical solutions', stance: 'Gradual approach', type: 'PERSONA', emoji: '🔧' },
    ];
  }
}
