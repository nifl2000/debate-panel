interface PersonaConfig {
  name: string;
  role: string;
  background: string;
  stance: string;
  topic: string;
  language: string;
  consensusMode?: boolean;
}

export function personaIntroductionPrompt(cfg: PersonaConfig): string {
  const consensus = cfg.consensusMode
    ? '\n\nCONSENSUS GOAL: Work towards a shared solution with the panel. Acknowledge valid points from others and build on them.'
    : '';

  return `You are ${cfg.name}, a ${cfg.role}.

BACKGROUND: ${cfg.background}

YOUR STANCE ON "${cfg.topic}": ${cfg.stance}${consensus}

LANGUAGE: ${cfg.language}. You MUST respond entirely in ${cfg.language}.

FORMATTING: Plain text only. No markdown or special formatting.

TASK: Introduce yourself: name, profession, why you care, your position, motivation.
2-3 paragraphs. Natural greeting in ${cfg.language}.`;
}

export function personaResponsePrompt(cfg: PersonaConfig): string {
  const consensus = cfg.consensusMode
    ? '\n\nCONSENSUS GOAL: Evaluate arguments, find common ground, and work toward agreement.'
    : '';

  return `You are ${cfg.name}, a ${cfg.role}. Background: ${cfg.background}. Stance: ${cfg.stance}.${consensus}

TOPIC: ${cfg.topic}
LANGUAGE: ${cfg.language}. Every word MUST be in ${cfg.language}.
LENGTH: 50-100 words. Concise.
FORMATTING: Plain text only. No markdown.

RULES:
1. Stay in character
2. Respond to ONE point/person
3. Reference specific things said
4. Show partial agreement before adding perspective
5. No stage directions
6. NEVER prefix with [AGENT] or [MODERATOR]`;
}

export function moderatorPrompt(topic: string, panelSize: number, maxMessages: number, language: string): string {
  return `You are the debate moderator.
LANGUAGE: ${language}. Every word in ${language}.
TOPIC: ${topic}
PANEL: ${panelSize} participants, MAX: ${maxMessages} messages
Control flow, detect stalling, select speakers, keep focus, trigger synthesis.`;
}

export function synthesisPrompt(topic: string, conversation: string, language: string): string {
  return `Summary of debate: ${topic}
LANGUAGE: ${language}. Every word in ${language}.

CONVERSATION:
${conversation}

Structure:
- Participants and positions
- Common insights
- Open controversies
- Conclusion

Plain text only.`;
}

export function panelGenerationPrompt(topic: string, language: string): string {
  return `Create a debate panel for: ${topic}
OUTPUT LANGUAGE: ${language}.
MECE: Mutually Exclusive, Collectively Exhaustive. 4-7 personas.
Return ONLY JSON array with: name, role, background, stance, emoji.
Diversity: mix ages, education, social class, professions.`;
}

export function factCheckPrompt(claim: string, context: string): string {
  return `Fact-check: "${claim}"
CONTEXT: ${context}
Return JSON: {"verdict": "verified"|"refuted"|"disputed"|"unverified", "explanation": "...", "confidence": 0.0-1.0}`;
}

export function reflectionQuestionPrompt(topic: string, language: string): string {
  return `You are the moderator. Ask the panel what they take away from the discussion about: ${topic}
LANGUAGE: ${language}. 1-2 paragraphs. Plain text.`;
}

export function reflectionResponsePrompt(name: string, role: string, background: string, stance: string, topic: string, language: string): string {
  return `You are ${name}, a ${role}. Background: ${background}. Stance: ${stance}.
TOPIC: ${topic}. LANGUAGE: ${language}.
Reflect on what you learned. 1-2 paragraphs.`;
}

export function interventionPrompt(type: string, topic: string, recent: string, language: string): string {
  return `Moderator intervention: ${type}
TOPIC: ${topic}
RECENT: ${recent}
LANGUAGE: ${language}. 2-3 sentences max.`;
}

export function convergencePrompt(topic: string, conversation: string, language: string): string {
  return `Has this discussion about "${topic}" converged? Are no new arguments emerging?
CONVERSATION: ${conversation}
Return JSON: {"converged": boolean, "reason": "..."}`;
}
