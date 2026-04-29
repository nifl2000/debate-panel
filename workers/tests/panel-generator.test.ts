import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PanelGenerator } from '../src/services/panel-generator';

describe('PanelGenerator', () => {
  let mockLLM: any;

  beforeEach(() => {
    mockLLM = {
      complete: vi.fn(),
    };
  });

  it('returns fallback personas on LLM error', async () => {
    mockLLM.complete.mockRejectedValue(new Error('LLM failed'));
    const gen = new PanelGenerator(mockLLM);
    const agents = await gen.generate('Test topic');
    expect(agents.length).toBeGreaterThanOrEqual(3);
    expect(agents[0].name).toBeTruthy();
    expect(agents[0].role).toBeTruthy();
  });

  it('parses valid JSON array response', async () => {
    mockLLM.complete.mockResolvedValue(
      JSON.stringify([
        { name: 'Test Person', role: 'Expert', background: 'Expert in field', stance: 'Pro', emoji: '👨‍🔬' },
        { name: 'Test Two', role: 'Skeptic', background: 'Skeptical', stance: 'Con', emoji: '🤔' },
        { name: 'Test Three', role: 'Pragmatist', background: 'Practical', stance: 'Neutral', emoji: '🔧' },
      ])
    );
    const gen = new PanelGenerator(mockLLM);
    const agents = await gen.generate('Test topic');
    expect(agents.length).toBe(3);
    expect(agents[0].name).toBe('Test Person');
  });

  it('parses JSON in markdown code blocks', async () => {
    mockLLM.complete.mockResolvedValue(
      '```json\n[{"name": "A", "role": "R", "background": "B", "stance": "S", "emoji": "👤"}]\n```'
    );
    const gen = new PanelGenerator(mockLLM);
    const agents = await gen.generate('Test');
    expect(agents.length).toBe(1);
    expect(agents[0].name).toBe('A');
  });
});
