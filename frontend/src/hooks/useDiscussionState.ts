import { useState, useRef, useCallback } from 'react';
import { PersonaData } from '../services/api';

type DiscussionPhase = 'IDLE' | 'GENERATING' | 'PANEL_READY' | 'STARTING' | 'INTRODUCTION' | 'DISCUSSION' | 'PAUSED' | 'COMPLETED' | 'SYNTHESIS';

interface Persona {
  id: string;
  name: string;
  role: string;
  background: string;
  stance: string;
  emoji?: string;
}

interface Message {
  id: string;
  agentId: string;
  agentName?: string;
  content: string;
  timestamp: string;
  type: string;
  sourceUrl?: string;
}

interface ConfigState {
  topic: string;
  model: string;
  maxMessages: string;
  maxMessagesInput: string;
  factCheckEnabled: boolean;
  consensusMode: boolean;
}

interface SessionState {
  sessionId: string | null;
  personas: Persona[];
  messages: Message[];
  synthesis: string | null;
  moderatorName: string;
  discussionState: DiscussionPhase;
}

interface UIState {
  loading: boolean;
  error: string | null;
  statusMessage: string;
  editingPersona: string | null;
  editForm: PersonaData;
  showAddForm: boolean;
  addForm: PersonaData;
  showInject: boolean;
  injectText: string;
}

export function useDiscussionState() {
  const [config, setConfig] = useState<ConfigState>({
    topic: '', model: 'qwen3-coder-next', maxMessages: '50',
    maxMessagesInput: '50', factCheckEnabled: false, consensusMode: false,
  });
  const [session, setSession] = useState<SessionState>({
    sessionId: null, personas: [], messages: [], synthesis: null,
    moderatorName: 'Moderator', discussionState: 'IDLE',
  });
  const [ui, setUI] = useState<UIState>({
    loading: false, error: null, statusMessage: '',
    editingPersona: null, editForm: { name: '', role: '', background: '', stance: '', emoji: '' },
    showAddForm: false, addForm: { name: '', role: '', background: '', stance: '', emoji: '' },
    showInject: false, injectText: '',
  });
  const eventSourceRef = useRef<EventSource | null>(null);
  const [, setMessageIds] = useState<Set<string>>(new Set());
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const MAX_RECONNECT_ATTEMPTS = 5;

  const setTopic = useCallback((v: string) => setConfig(p => ({ ...p, topic: v })), []);
  const setModel = useCallback((v: string) => setConfig(p => ({ ...p, model: v })), []);
  const setMaxMessages = useCallback((v: string) => setConfig(p => ({ ...p, maxMessages: v })), []);
  const setMaxMessagesInput = useCallback((v: string) => setConfig(p => ({ ...p, maxMessagesInput: v })), []);
  const setFactCheckEnabled = useCallback((v: boolean) => setConfig(p => ({ ...p, factCheckEnabled: v })), []);
  const setConsensusMode = useCallback((v: boolean) => setConfig(p => ({ ...p, consensusMode: v })), []);

  const setSessionId = useCallback((v: string | null) => setSession(p => ({ ...p, sessionId: v })), []);
  const setPersonas = useCallback((v: Persona[] | ((prev: Persona[]) => Persona[])) =>
    setSession(p => ({ ...p, personas: typeof v === 'function' ? v(p.personas) : v })), []);
  const setMessages = useCallback((v: Message[] | ((prev: Message[]) => Message[])) =>
    setSession(p => ({ ...p, messages: typeof v === 'function' ? v(p.messages) : v })), []);
  const setSynthesis = useCallback((v: string | null) => setSession(p => ({ ...p, synthesis: v })), []);
  const setModeratorName = useCallback((v: string) => setSession(p => ({ ...p, moderatorName: v })), []);
  const setDiscussionState = useCallback((v: DiscussionPhase) => setSession(p => ({ ...p, discussionState: v })), []);

  const setLoading = useCallback((v: boolean) => setUI(p => ({ ...p, loading: v })), []);
  const setError = useCallback((v: string | null) => setUI(p => ({ ...p, error: v })), []);
  const setStatusMessage = useCallback((v: string) => setUI(p => ({ ...p, statusMessage: v })), []);
  const setEditingPersona = useCallback((v: string | null) => setUI(p => ({ ...p, editingPersona: v })), []);
  const setEditForm = useCallback((v: PersonaData | ((prev: PersonaData) => PersonaData)) =>
    setUI(p => ({ ...p, editForm: typeof v === 'function' ? v(p.editForm) : v })), []);
  const setShowAddForm = useCallback((v: boolean) => setUI(p => ({ ...p, showAddForm: v })), []);
  const setAddForm = useCallback((v: PersonaData | ((prev: PersonaData) => PersonaData)) =>
    setUI(p => ({ ...p, addForm: typeof v === 'function' ? v(p.addForm) : v })), []);
  const setShowInject = useCallback((v: boolean) => setUI(p => ({ ...p, showInject: v })), []);
  const setInjectText = useCallback((v: string) => setUI(p => ({ ...p, injectText: v })), []);

  return {
    config, session, ui,
    eventSourceRef, setMessageIds, reconnectAttempts, reconnectTimer, MAX_RECONNECT_ATTEMPTS,
    setTopic, setModel, setMaxMessages, setMaxMessagesInput, setFactCheckEnabled, setConsensusMode,
    setSessionId, setPersonas, setMessages, setSynthesis, setModeratorName, setDiscussionState,
    setLoading, setError, setStatusMessage, setEditingPersona, setEditForm, setShowAddForm, setAddForm,
    setShowInject, setInjectText,
  };
}
