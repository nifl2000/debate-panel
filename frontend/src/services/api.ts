import { Agent, DiscussionSession, ExportFormat } from '../types';

// Base URL from environment variable, default to localhost
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Start a new discussion session
 */
export async function startDiscussion(topic: string, maxMessages: number = 30, model: string = 'qwen3-coder-next', factCheckEnabled: boolean = false, consensusMode: boolean = false): Promise<{ sessionId: string }> {
  const response = await fetch(`${BASE_URL}/api/discussion/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, max_messages: maxMessages, model, fact_check_enabled: factCheckEnabled, consensus_mode: consensusMode }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to start discussion: ${response.status} ${error}`);
  }

  const data = await response.json();
  return { sessionId: data.session_id };
}

export async function pollGenerationStatus(
  sessionId: string,
  onProgress: (status: string, message: string, personas: Agent[], moderatorName?: string) => void
): Promise<Agent[]> {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/status`);
        if (!response.ok) {
          reject(new Error('Status check failed'));
          return;
        }

        const data = await response.json();
        onProgress(data.status, data.message, data.personas || [], data.moderator_name);

        if (data.status === 'ready') {
          resolve(data.personas);
        } else if (data.status === 'error') {
          reject(new Error(data.message));
        } else {
          setTimeout(poll, 500);
        }
      } catch (e) {
        reject(e);
      }
    };
    poll();
  });
}

/**
 * Get discussion session by ID
 */
export async function getDiscussion(sessionId: string): Promise<DiscussionSession> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}`);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to get discussion: ${response.status} ${error}`);
  }

  return response.json();
}

/**
 * Pause a discussion session
 */
export async function pauseDiscussion(sessionId: string): Promise<{ state: string }> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/pause`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to pause discussion: ${response.status} ${error}`);
  }

  return response.json();
}

/**
 * Stop a discussion session
 */
export async function stopDiscussion(sessionId: string): Promise<{ state: string; synthesis?: string }> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/stop`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to stop discussion: ${response.status} ${error}`);
  }

  return response.json();
}

export async function injectInstruction(sessionId: string, instruction: string): Promise<{ status: string; message: string }> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/inject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to inject instruction: ${response.status} ${error}`);
  }

  return response.json();
}

/**
 * Export a discussion session
 */
export async function exportDiscussion(
  sessionId: string,
  format: ExportFormat
): Promise<Blob> {
  const response = await fetch(
    `${BASE_URL}/api/discussion/${sessionId}/export?format=${format}`
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to export discussion: ${response.status} ${error}`);
  }

  return response.blob();
}

export interface PersonaData {
  name: string;
  role: string;
  background: string;
  stance: string;
  emoji?: string;
}

export async function updatePersona(
  sessionId: string,
  personaId: string,
  data: PersonaData
): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/personas/${personaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update persona');
}

export async function deletePersona(
  sessionId: string,
  personaId: string
): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/personas/${personaId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete persona');
}

export async function addPersona(
  sessionId: string,
  data: PersonaData
): Promise<{ personaId: string }> {
  const response = await fetch(`${BASE_URL}/api/discussion/${sessionId}/personas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to add persona');
  return response.json();
}