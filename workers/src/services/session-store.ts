import type { SessionData, DiscussionConfig } from '../types';

const KV_TTL = 3600;
const SYNC_INTERVAL = 5000;

interface ActiveSession {
  data: SessionData;
  interval: ReturnType<typeof setInterval> | null;
}

export class SessionStore {
  private activeSessions: Map<string, ActiveSession> = new Map();

  constructor(private kv: KVNamespace) {}

  async create(
    id: string,
    topic: string,
    config: DiscussionConfig
  ): Promise<SessionData> {
    const data: SessionData = {
      id,
      topic,
      state: 'GENERATING',
      phase: 'INTRODUCTION',
      config,
      agents: [],
      messages: [],
      synthesis: '',
      moderatorName: '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      generationStatus: 'starting',
      generationMessage: 'Starting discussion...',
    };

    this.activeSessions.set(id, { data, interval: null });
    await this.saveToKV(id, data);

    return data;
  }

  get(id: string): SessionData | undefined {
    return this.activeSessions.get(id)?.data;
  }

  async loadFromKV(id: string): Promise<SessionData | null> {
    const cached = this.activeSessions.get(id);
    if (cached) return cached.data;

    const raw = await this.kv.get(id);
    if (!raw) return null;

    const data = JSON.parse(raw) as SessionData;
    this.activeSessions.set(id, { data, interval: null });
    return data;
  }

  async save(id: string): Promise<void> {
    const session = this.activeSessions.get(id);
    if (session) {
      await this.saveToKV(id, session.data);
    }
  }

  async saveToKV(id: string, data: SessionData): Promise<void> {
    await this.kv.put(id, JSON.stringify(data), { expirationTtl: KV_TTL });
  }

  startAutoSync(id: string): void {
    const session = this.activeSessions.get(id);
    if (!session || session.interval) return;

    session.interval = setInterval(async () => {
      await this.saveToKV(id, session.data);
    }, SYNC_INTERVAL);
  }

  stopAutoSync(id: string): void {
    const session = this.activeSessions.get(id);
    if (session?.interval) {
      clearInterval(session.interval);
      session.interval = null;
    }
  }

  async delete(id: string): Promise<void> {
    this.stopAutoSync(id);
    this.activeSessions.delete(id);
    await this.kv.delete(id);
  }

  async persistToD1(id: string, env: { DB: D1Database }): Promise<void> {
    const session = this.activeSessions.get(id);
    if (!session) return;

    const { data } = session;
    const { getDb, sessions } = await import('../db');
    const db = getDb(env);

    await db.insert(sessions).values({
      id: data.id,
      topic: data.topic,
      state: data.state,
      config: JSON.stringify(data.config),
      agents: JSON.stringify(data.agents),
      messages: JSON.stringify(data.messages),
      synthesis: data.synthesis || null,
      moderatorName: data.moderatorName || null,
      createdAt: new Date(data.createdAt),
      updatedAt: new Date(data.updatedAt),
      expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
    });
  }

  async cleanup(): Promise<void> {
    for (const [id, session] of this.activeSessions) {
      if (session.data.state === 'COMPLETED' || session.data.state === 'ERROR') {
        this.stopAutoSync(id);
        this.activeSessions.delete(id);
      }
    }
  }
}
