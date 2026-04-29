import { describe, it, expect } from 'vitest';
import { estimateTokens, getWindowedMessages } from '../src/services/tokens';

describe('token counter', () => {
  it('estimates tokens for English text', () => {
    const tokens = estimateTokens('Hello world, this is a test message for token counting');
    expect(tokens).toBeGreaterThan(0);
    expect(tokens).toBeLessThan(30);
  });

  it('windows messages to fit limit', () => {
    const messages = Array.from({ length: 20 }, (_, i) => ({
      role: 'user',
      content: `Message ${i}: ${'x'.repeat(100)}`,
    }));
    const windowed = getWindowedMessages(messages, 500);
    expect(windowed.length).toBeLessThan(20);
  });
});
