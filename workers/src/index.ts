import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { SessionStore } from './services/session-store';
import { PanelGenerator } from './services/panel-generator';
import { ModeratorAgent } from './agents/moderator';
import { PersonaAgent } from './agents/persona';
import { FactCheckerAgent } from './agents/fact-checker';
import { LLMClient } from './llm';
import { detectLanguage } from './services/language';
import type {
  SessionData, Message, Agent, StartDiscussionRequest, PersonaUpdateRequest
} from './types';

interface Env {
  DASHSCOPE_API_KEY: string;
  DB: D1Database;
  SESSION_KV: KVNamespace;
  DEFAULT_MODEL: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const app = createApp(env, ctx);
    return app.fetch(request, env, ctx);
  },
};

function createApp(env: Env, ctx: ExecutionContext) {
  const app = new Hono<{ Bindings: Env }>();
  const store = new SessionStore(env.SESSION_KV);

  app.use('*', cors({
    origin: (origin) => {
      if (!origin) return '*';
      const allowed = ['http://localhost:5173', 'https://debate-panel.pages.dev'];
      return allowed.includes(origin) ? origin : allowed[1];
    },
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type'],
    credentials: true,
  }));

  app.get('/health', (c) => c.json({ status: 'healthy' }));

  // GET /api/diag — temporary diagnostic endpoint
  app.get('/api/diag', async (c) => {
    const env = c.env;
    const results: Record<string, unknown> = {};

    // Check bindings
    results.dashscope_key_present = !!env.DASHSCOPE_API_KEY;
    results.dashscope_key_prefix = env.DASHSCOPE_API_KEY
      ? env.DASHSCOPE_API_KEY.slice(0, 6) + '...'
      : null;
    results.kv_available = !!env.SESSION_KV;
    results.d1_available = !!env.DB;
    results.default_model = env.DEFAULT_MODEL;

    // Test LLM call
    try {
      const llm = new LLMClient(env.DASHSCOPE_API_KEY);
      const testMsg = await llm.complete(
        [{ role: 'user', content: 'Reply with "OK" only' }],
        { maxTokens: 10, temperature: 0 }
      );
      results.llm_test = 'success';
      results.llm_response = testMsg;
    } catch (err: unknown) {
      results.llm_test = 'failed';
      results.llm_error = err instanceof Error ? err.message : String(err);
    }

    // Test panel generation
    try {
      const llm = new LLMClient(env.DASHSCOPE_API_KEY);
      const generator = new PanelGenerator(llm);
      const agents = await generator.generate('Test topic', false, undefined);
      results.panel_test = 'success';
      results.panel_count = agents.length;
      results.panel_agents = agents.map(a => a.name);
    } catch (err: unknown) {
      results.panel_test = 'failed';
      results.panel_error = err instanceof Error ? err.message : String(err);
    }

    return c.json(results);
  });

  // POST /api/discussion/start
  app.post('/api/discussion/start', async (c) => {
    const body = await c.req.json<StartDiscussionRequest>();
    if (!body.topic?.trim()) {
      return c.json({ error: 'Topic required' }, 400);
    }

    const id = crypto.randomUUID();
    const config = {
      maxMessages: body.max_messages ?? 30,
      factCheckEnabled: body.fact_check_enabled ?? false,
      consensusMode: body.consensus_mode ?? false,
      model: body.model,
    };

    const session = await store.create(id, body.topic, config);

    // Run panel generation in background. Client polls /status endpoint.
    // KV fallback ensures background task can load session data.
    ctx.waitUntil(runPanelGeneration(id, body.topic, config, env, store));

    return c.json({ session_id: id, personas: [], status: 'generating' });
  });

  // GET /api/discussion/{id}/status
  app.get('/api/discussion/:id/status', async (c) => {
    const id = c.req.param('id');
    const data = store.get(id) || await store.loadFromKV(id);
    if (!data) return c.json({ error: 'Session not found' }, 404);

    return c.json({
      session_id: data.id,
      status: data.generationStatus,
      message: data.generationMessage,
      personas: data.agents,
      moderator_name: data.moderatorName,
    });
  });

  // GET /api/discussion/{id}/stream
  app.get('/api/discussion/:id/stream', async (c) => {
    const id = c.req.param('id');
    const data = store.get(id) || await store.loadFromKV(id);
    if (!data) return c.json({ error: 'Session not found' }, 404);

    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    const subId = crypto.randomUUID();
    const subscribers = getSubscribers(id);
    subscribers.set(subId, {
      enqueue: (d: string) => writer.write(encoder.encode(d)),
      close: () => writer.close(),
    });

    for (const msg of data.messages) {
      subscribers.get(subId)!.enqueue(
        `data: ${JSON.stringify(formatSSE(msg))}\n\n`
      );
    }

    (async () => {
      while (subscribers.has(subId)) {
        subscribers.get(subId)?.enqueue(
          `data: ${JSON.stringify({ type: 'heartbeat' })}\n\n`
        );
        await new Promise(r => setTimeout(r, 15000));
      }
    })();

    c.req.raw.signal.addEventListener('abort', () => {
      subscribers.delete(subId);
    });

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  });

  // PUT /api/discussion/{id}/personas/{personaId}
  app.put('/api/discussion/:id/personas/:personaId', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    const body = await c.req.json<PersonaUpdateRequest>();
    const agent = data.agents.find(a => a.id === c.req.param('personaId'));
    if (!agent) return c.json({ error: 'Persona not found' }, 404);

    Object.assign(agent, body);
    data.updatedAt = new Date().toISOString();
    await store.save(data.id);

    return c.json({ status: 'updated', persona_id: agent.id });
  });

  // DELETE /api/discussion/{id}/personas/{personaId}
  app.delete('/api/discussion/:id/personas/:personaId', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    data.agents = data.agents.filter(a => a.id !== c.req.param('personaId'));
    data.updatedAt = new Date().toISOString();
    await store.save(data.id);

    return c.json({ status: 'deleted', persona_id: c.req.param('personaId') });
  });

  // POST /api/discussion/{id}/personas
  app.post('/api/discussion/:id/personas', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    const body = await c.req.json<PersonaUpdateRequest>();
    const agent: Agent = {
      id: `persona_${data.id.slice(0, 4)}_${Date.now().toString(16)}`,
      name: body.name,
      role: body.role,
      background: body.background,
      stance: body.stance,
      type: 'PERSONA',
      emoji: body.emoji || '',
    };

    data.agents.push(agent);
    data.updatedAt = new Date().toISOString();
    await store.save(data.id);

    return c.json({ status: 'added', persona_id: agent.id });
  });

  // GET /api/discussion/{id}/debug — debug session state
  app.get('/api/discussion/:id/debug', async (c) => {
    const id = c.req.param('id');
    const data = store.get(id) || await store.loadFromKV(id);
    if (!data) return c.json({ error: 'Not found' }, 404);
    return c.json({
      id: data.id,
      state: data.state,
      phase: data.phase,
      agents_count: data.agents.length,
      agents: data.agents.map(a => ({ id: a.id, name: a.name, type: a.type })),
      messages_count: data.messages.length,
      moderator_name: data.moderatorName,
      generation_status: data.generationStatus,
      generation_message: data.generationMessage,
      config: data.config,
      has_dashscope: !!c.env.DASHSCOPE_API_KEY,
    });
  });

  // POST /api/discussion/{id}/start-discussion
  app.post('/api/discussion/:id/start-discussion', async (c) => {
    const id = c.req.param('id');
    const data = store.get(id) || await store.loadFromKV(id);
    if (!data) return c.json({ error: 'Not found' }, 404);
    if (data.agents.length === 0) return c.json({ error: 'Panel not ready' }, 400);

    data.state = 'DISCUSSION';
    data.phase = 'INTRODUCTION';
    data.moderatorName = generateModeratorName();
    data.updatedAt = new Date().toISOString();

    store.startAutoSync(id);

    ctx.waitUntil(runDiscussionLoop(id, data, env, store));

    return c.json({
      status: 'discussion_started',
      moderator_name: data.moderatorName,
    });
  });

  // POST /api/discussion/{id}/pause
  app.post('/api/discussion/:id/pause', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);
    if (data.state === 'COMPLETED') return c.json({ error: 'Already completed' }, 400);

    data.state = 'PAUSED';
    data.updatedAt = new Date().toISOString();
    await store.save(data.id);

    return c.json({ session_id: data.id, state: 'PAUSED', message: 'Paused' });
  });

  // POST /api/discussion/{id}/resume
  app.post('/api/discussion/:id/resume', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    data.state = 'DISCUSSION';
    data.updatedAt = new Date().toISOString();
    store.startAutoSync(data.id);

    return c.json({ session_id: data.id, state: 'ACTIVE', message: 'Resumed' });
  });

  // POST /api/discussion/{id}/stop
  app.post('/api/discussion/:id/stop', async (c) => {
    const id = c.req.param('id');
    const data = store.get(id);
    if (!data) return c.json({ error: 'Not found' }, 404);

    data.state = 'COMPLETED';
    data.phase = 'COMPLETED';
    store.stopAutoSync(id);

    if (!data.synthesis) {
      const llm = new LLMClient(env.DASHSCOPE_API_KEY);
      const moderator = new ModeratorAgent('mod', data.moderatorName, llm, new FactCheckerAgent(llm));
      data.synthesis = await moderator.generateSynthesis(data.topic, data.messages, data.config.model);
    }

    await store.save(id);
    await store.persistToD1(id, env);

    notifySubscribers(id, { type: 'SYSTEM', content: 'Discussion ended' });

    return c.json({ session_id: id, state: 'COMPLETED', synthesis: data.synthesis });
  });

  // POST /api/discussion/{id}/inject
  app.post('/api/discussion/:id/inject', async (c) => {
    const data = store.get(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    const body = await c.req.json<{ instruction: string }>();
    const msg: Message = {
      id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      agentId: 'moderator',
      agentName: data.moderatorName || 'Moderator',
      content: body.instruction,
      timestamp: new Date().toISOString(),
      type: 'MODERATOR',
    };
    data.messages.push(msg);
    data.updatedAt = new Date().toISOString();
    await store.save(data.id);

    notifySubscribers(data.id, formatSSE(msg));

    return c.json({ status: 'injected', message: `Injiziert: ${body.instruction.slice(0, 50)}...` });
  });

  // GET /api/discussion/{id}
  app.get('/api/discussion/:id', async (c) => {
    const data = store.get(c.req.param('id')) || await store.loadFromKV(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    return c.json({
      topic: data.topic,
      state: data.state,
      messages: data.messages,
      agents: data.agents,
    });
  });

  // GET /api/discussion/{id}/export
  app.get('/api/discussion/:id/export', async (c) => {
    const format = c.req.query('format') || 'TEXT';
    const data = store.get(c.req.param('id')) || await store.loadFromKV(c.req.param('id'));
    if (!data) return c.json({ error: 'Not found' }, 404);

    let content = `# DebatePanel: ${data.topic}\n\n`;
    content += `Date: ${data.createdAt}\nParticipants: ${data.agents.map(a => a.name).join(', ')}\n\n---\n\n`;

    for (const msg of data.messages) {
      content += `### ${msg.agentName}\n\n${msg.content}\n\n`;
    }

    if (data.synthesis) {
      content += `---\n\n## Summary\n\n${data.synthesis}\n`;
    }

    const contentType = format === 'MARKDOWN' ? 'text/markdown' : 'text/plain';
    const body = format === 'MARKDOWN' ? content : content.replace(/[#*_]/g, '');

    return c.text(body, 200, { 'Content-Type': contentType });
  });

  return app;
}

// --- Discussion Loop ---

async function runPanelGeneration(
  id: string,
  topic: string,
  config: { maxMessages: number; factCheckEnabled: boolean; consensusMode: boolean; model?: string },
  env: Env,
  store: SessionStore
): Promise<void> {
  const data = store.get(id) || await store.loadFromKV(id);
  if (!data) {
    console.error(`[panel] No session data for ${id}`);
    return;
  }

  const llm = new LLMClient(env.DASHSCOPE_API_KEY);
  const generator = new PanelGenerator(llm);

  data.generationStatus = 'detecting_language';
  data.generationMessage = 'Detecting language...';

  try {
    const agents = await generator.generate(topic, config.consensusMode, config.model);
    data.agents = agents;
    data.state = 'PANEL_READY';
    data.generationStatus = 'ready';
    data.generationMessage = `${agents.length} personas ready!`;
    data.updatedAt = new Date().toISOString();
    await store.save(id);
  } catch (error) {
    data.generationStatus = 'error';
    data.generationMessage = `Error: ${error}`;
    data.state = 'ERROR';
    await store.save(id);
  }
}

async function runDiscussionLoop(
  id: string,
  data: SessionData,
  env: Env,
  store: SessionStore
): Promise<void> {
  try {
    console.log(`[loop] Starting for session ${id}, agents: ${data.agents.length}, model: ${data.config.model}`);
    const llm = new LLMClient(env.DASHSCOPE_API_KEY);
    const factChecker = new FactCheckerAgent(llm);
    const moderator = new ModeratorAgent('moderator', data.moderatorName, llm, factChecker);

  const personas = data.agents
    .filter(a => a.type === 'PERSONA')
    .map(a => new PersonaAgent(a, data.topic, data.config.consensusMode));

  // Phase 1: Introductions
  data.phase = 'INTRODUCTION';
  for (const persona of personas) {
    if (data.state !== 'DISCUSSION') break;

    const content = await persona.generateIntroduction(llm, data.config.model);
    const msg = persona.createMessage(content, 'AGENT', persona.name);
    data.messages.push(msg);
    data.updatedAt = new Date().toISOString();
    await store.save(id);
    notifySubscribers(id, formatSSE(msg));

    data.generationStatus = 'introducing';
    data.generationMessage = `${persona.name} introduces...`;
  }

  // Phase 2: Discussion
  data.phase = 'DISCUSSION';
  const statusMsg: Message = {
    id: `msg_${crypto.randomUUID().slice(0, 8)}`,
    agentId: 'system',
    agentName: 'System',
    content: 'Open discussion begins...',
    timestamp: new Date().toISOString(),
    type: 'SYSTEM',
  };
  data.messages.push(statusMsg);
  notifySubscribers(id, formatSSE(statusMsg));

  let iteration = 0;
  let moderatorInterval = 0;

  while (data.state === 'DISCUSSION') {
    iteration++;
    moderatorInterval++;

    const agentMsgCount = data.messages.filter(m => m.type === 'AGENT' || m.type === 'MODERATOR').length;
    if (agentMsgCount >= data.config.maxMessages) break;

    const current = store.get(id);
    if (current?.state === 'PAUSED') {
      await new Promise(r => setTimeout(r, 2000));
      continue;
    }

    const nextSpeaker = moderator.selectNextSpeaker(personas, data.messages);
    if (!nextSpeaker) break;

    const speakerStatus: Message = {
      id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      agentId: 'system',
      agentName: 'System',
      content: `${nextSpeaker.name} spricht...`,
      timestamp: new Date().toISOString(),
      type: 'SYSTEM',
    };
    data.messages.push(speakerStatus);
    notifySubscribers(id, formatSSE(speakerStatus));

    const context = nextSpeaker.getContext(data.messages, nextSpeaker.id);
    const content = await nextSpeaker.generateResponse(llm, context, undefined, data.config.model);

    const msg = nextSpeaker.createMessage(content, 'AGENT', nextSpeaker.name);
    data.messages.push(msg);
    data.updatedAt = new Date().toISOString();
    await store.save(id);
    notifySubscribers(id, formatSSE(msg));

    if (data.config.factCheckEnabled) {
      await moderator.runFactCheck(content, data.messages, data.config.model);
    }

    if (moderatorInterval >= 3) {
      moderatorInterval = 0;
      const intervention = await moderator.generateIntervention(
        'CLARIFYING',
        data.topic,
        data.messages.slice(-3).map(m => m.content).join('\n'),
        data.config.model
      );
      const modMsg: Message = {
        id: `msg_${crypto.randomUUID().slice(0, 8)}`,
        agentId: 'moderator',
        agentName: data.moderatorName,
        content: intervention,
        timestamp: new Date().toISOString(),
        type: 'MODERATOR',
      };
      data.messages.push(modMsg);
      await store.save(id);
      notifySubscribers(id, formatSSE(modMsg));
    }

    const totalAgentMsgs = data.messages.filter(m => m.type === 'AGENT').length;
    if (totalAgentMsgs >= data.config.maxMessages - 2) {
      const converged = await moderator.checkConvergence(data.topic, data.messages, data.config.model);
      if (converged) break;
    }

    await new Promise(r => setTimeout(r, 500));
  }

  // Phase 3: Reflection + Synthesis
  data.phase = 'COMPLETED';
  data.state = 'COMPLETED';

  const reflections = await moderator.generateReflection(
    personas, data.topic, data.messages, data.config.model
  );
  for (const ref of reflections) {
    data.messages.push(ref);
    notifySubscribers(id, formatSSE(ref));
  }

  const synthesis = await moderator.generateSynthesis(
    data.topic, data.messages, data.config.model
  );
  data.synthesis = synthesis;

  const synthMsg: Message = {
    id: `msg_${crypto.randomUUID().slice(0, 8)}`,
    agentId: 'moderator',
    agentName: data.moderatorName,
    content: synthesis,
    timestamp: new Date().toISOString(),
    type: 'MODERATOR',
  };
  data.messages.push(synthMsg);
  data.updatedAt = new Date().toISOString();

  store.stopAutoSync(id);
  await store.save(id);
  await store.persistToD1(id, env);

  notifySubscribers(id, formatSSE(synthMsg));
  notifySubscribers(id, { type: 'SYSTEM', content: 'Discussion ended' });
  } catch (error: unknown) {
    console.error(`[loop] ERROR: ${error}`);
    data.state = 'ERROR';
    data.generationStatus = 'error';
    data.generationMessage = `Loop failed: ${error}`;
    data.updatedAt = new Date().toISOString();
    await store.save(id);
    notifySubscribers(id, { type: 'SYSTEM', content: `Error: ${error}` });
  }
}

// --- SSE Subscriber Management ---

const subscribersMap: Map<string, Map<string, { enqueue: (d: string) => void; close: () => void }>> = new Map();

function getSubscribers(id: string) {
  if (!subscribersMap.has(id)) {
    subscribersMap.set(id, new Map());
  }
  return subscribersMap.get(id)!;
}

function notifySubscribers(id: string, data: string | object) {
  const subs = subscribersMap.get(id);
  if (!subs) return;

  const text = typeof data === 'string' ? data : `data: ${JSON.stringify(data)}\n\n`;
  for (const sub of subs.values()) {
    try {
      sub.enqueue(text);
    } catch {
      // Disconnected
    }
  }
}

function formatSSE(msg: Message): object {
  return {
    type: msg.type,
    agent_id: msg.agentId,
    agent_type: msg.type,
    content: msg.content,
    metadata: {
      message_id: msg.id,
      timestamp: msg.timestamp,
      persona_name: msg.agentName,
      ...(msg.sourceUrl ? { source_url: msg.sourceUrl } : {}),
    },
  };
}

function generateModeratorName(): string {
  const names = ['Clara Vogel', 'Anna Bergmann', 'Sophie Richter', 'Lena Hartmann', 'Marie Schneider', 'Julia Weber', 'Sarah Fischer', 'Laura Müller'];
  return names[Math.floor(Math.random() * names.length)];
}
