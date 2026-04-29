import { describe, it, expect } from 'vitest';
import { detectLanguage } from '../src/services/language';

describe('detectLanguage', () => {
  it('detects German', () => {
    expect(detectLanguage('Dies ist ein deutscher Text über die politische Diskussion')).toBe('German');
  });

  it('detects English', () => {
    expect(detectLanguage('This is an English text about the political discussion')).toBe('English');
  });

  it('defaults to English for short text', () => {
    expect(detectLanguage('hi')).toBe('English');
  });
});
