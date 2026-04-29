import { describe, it, expect } from 'vitest';
import { personaIntroductionPrompt, personaResponsePrompt, synthesisPrompt, panelGenerationPrompt } from '../src/prompts';

describe('prompts', () => {
  it('persona intro includes all fields', () => {
    const p = personaIntroductionPrompt({ name: 'Dr. Test', role: 'Scientist', background: '10 years', stance: 'Pro', topic: 'AI Ethics', language: 'German' });
    expect(p).toContain('Dr. Test');
    expect(p).toContain('Scientist');
    expect(p).toContain('AI Ethics');
  });

  it('consensus mode adds goal instruction', () => {
    const p = personaResponsePrompt({ name: 'T', role: 'E', background: 'B', stance: 'S', topic: 'T', language: 'E', consensusMode: true });
    expect(p).toContain('CONSENSUS GOAL');
  });

  it('synthesis includes topic and conversation', () => {
    const p = synthesisPrompt('Topic', 'log', 'English');
    expect(p).toContain('Topic');
    expect(p).toContain('log');
  });

  it('panel generation includes topic and language', () => {
    const p = panelGenerationPrompt('Topic', 'German');
    expect(p).toContain('Topic');
    expect(p).toContain('German');
  });
});
