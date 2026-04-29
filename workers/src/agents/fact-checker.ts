import type { LLMClient } from '../llm';
import { factCheckPrompt } from '../prompts';

export interface FactCheckResult {
  claim: string;
  verdict: 'verified' | 'refuted' | 'disputed' | 'unverified';
  explanation: string;
  confidence: number;
}

export class FactCheckerAgent {
  constructor(private llm: LLMClient) {}

  async detectClaims(llm: LLMClient, message: string): Promise<string[]> {
    const prompt = `Identify the SINGLE most important factual claim in this message.
Return ONLY a JSON array with at most ONE claim string. Return [] if no factual claim.

Message: ${message}`;

    const response = await llm.complete([
      { role: 'user', content: prompt },
    ]);

    try {
      let cleaned = response.trim();
      if (cleaned.includes('```')) {
        cleaned = cleaned.split('```')[1]?.split('```')[0] || cleaned;
      }
      const claims = JSON.parse(cleaned);
      if (Array.isArray(claims) && claims.length > 0) {
        return [String(claims[0])];
      }
    } catch { /* ignore */ }

    return [];
  }

  async checkClaim(
    claim: string,
    context: string = ''
  ): Promise<FactCheckResult> {
    const prompt = factCheckPrompt(claim, context);

    try {
      const response = await this.llm.complete([
        { role: 'user', content: prompt },
      ]);

      let cleaned = response.trim();
      if (cleaned.includes('```')) {
        cleaned = cleaned.split('```')[1]?.split('```')[0] || cleaned;
      }

      const result = JSON.parse(cleaned);
      return {
        claim,
        verdict: result.verdict || 'unverified',
        explanation: result.explanation || 'Could not verify.',
        confidence: result.confidence || 0.0,
      };
    } catch {
      return {
        claim,
        verdict: 'unverified',
        explanation: 'Error during fact-check.',
        confidence: 0.0,
      };
    }
  }
}
