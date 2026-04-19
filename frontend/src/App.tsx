import { useCallback, Component, type ReactNode } from 'react';
import { startDiscussion, pollGenerationStatus, stopDiscussion, injectInstruction, updatePersona, deletePersona, addPersona } from './services/api';
import { useDiscussionState } from './hooks/useDiscussionState';
import { TopicInput } from './components/TopicInput';
import { PersonaReview } from './components/PersonaReview';
import { DiscussionView } from './components/DiscussionView';

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: string }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: '' };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center', fontFamily: 'system-ui' }}>
          <h2>An error occurred</h2>
          <p style={{ color: '#666' }}>{this.state.error}</p>
          <button onClick={() => window.location.reload()} style={{ marginTop: 16, padding: '8px 16px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
            Seite neu laden
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const log = (component: string, event: string, details?: Record<string, unknown>) => {
  console.log(`%c[DebatePanel] %c[${component}] %c${event}`, 'color: #2563eb; font-weight: bold', 'color: #7c3aed', 'color: #059669', details || '');
};

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

function App() {
  const state = useDiscussionState();
  const {
    config, session, ui,
    eventSourceRef, setMessageIds, reconnectAttempts, reconnectTimer, MAX_RECONNECT_ATTEMPTS,
    setTopic, setModel, setMaxMessages, setMaxMessagesInput, setFactCheckEnabled, setConsensusMode,
    setSessionId, setPersonas, setMessages, setSynthesis, setModeratorName, setDiscussionState,
    setLoading, setError, setStatusMessage, setEditingPersona, setEditForm, setShowAddForm, setAddForm,
    setShowInject, setInjectText,
  } = state;

  const topic = config.topic;
  const model = config.model;
  const maxMessages = config.maxMessages;
  const maxMessagesInput = config.maxMessagesInput;
  const factCheckEnabled = config.factCheckEnabled;
  const consensusMode = config.consensusMode;

  const sessionId = session.sessionId;
  const personas = session.personas;
  const messages = session.messages;
  const synthesis = session.synthesis;
  const moderatorName = session.moderatorName;
  const discussionState = session.discussionState;

  const loading = ui.loading;
  const error = ui.error;
  const statusMessage = ui.statusMessage;
  const editingPersona = ui.editingPersona;
  const editForm = ui.editForm;
  const showAddForm = ui.showAddForm;
  const addForm = ui.addForm;
  const showInject = ui.showInject;
  const injectText = ui.injectText;

  const connectSSE = useCallback((sid: string) => {
    log('frontend', 'sse_connect', { sessionId: sid, attempt: reconnectAttempts.current + 1 });
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    const es = new EventSource(`${API_BASE_URL}/api/discussion/${sid}/stream`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'heartbeat') return;

        reconnectAttempts.current = 0;

        const msgId = data.metadata?.message_id || crypto.randomUUID();

        if (data.agent_id === 'system') {
          setStatusMessage(data.content);
          if (data.content.includes('Vorstellung') || data.content.includes('startet')) {
            setDiscussionState('INTRODUCTION');
            log('frontend', 'state_change', { from: discussionState, to: 'INTRODUCTION', event: data.content });
          }
          else if (data.content.includes('Open discussion')) {
            setDiscussionState('DISCUSSION');
            log('frontend', 'state_change', { from: discussionState, to: 'DISCUSSION' });
          }
          else if (data.content.includes('completed') || data.content.includes('Discussion completed')) {
            setDiscussionState('COMPLETED');
            log('frontend', 'state_change', { from: discussionState, to: 'COMPLETED' });
            setMessages(prev => [...prev, {
              id: crypto.randomUUID(),
              agentId: 'system',
              agentName: 'System',
              content: '🏁 Discussion ended',
              timestamp: new Date().toISOString(),
              type: 'SYSTEM',
            }]);
          }
          log('frontend', 'sse_system_message', { content: data.content });
        } else {
          setMessageIds(prev => {
            if (prev.has(msgId)) return prev;
            const next = new Set(prev);
            next.add(msgId);

            const rawType = data.agent_type || data.type || 'AGENT';
            const msgType = typeof rawType === 'string' ? rawType : String(rawType);

            const msg: Message = {
              id: msgId,
              agentId: data.agent_id || 'system',
              agentName: data.metadata?.persona_name,
              content: data.content || '',
              timestamp: data.metadata?.timestamp || new Date().toISOString(),
              type: msgType,
              sourceUrl: data.metadata?.source_url,
            };
            setMessages(prevMsgs => [...prevMsgs, msg]);
            log('frontend', 'sse_message_received', { agent: msg.agentName, type: msg.type, length: msg.content.length });
            return next;
          });
        }
      } catch (e) {
        console.error('SSE parse error:', e);
        log('frontend', 'sse_parse_error', { error: e });
      }
    };

    es.onerror = () => {
      if (discussionState === 'COMPLETED' || discussionState === 'SYNTHESIS') {
        es.close();
        return;
      }
      log('frontend', 'sse_connection_error', { attempts: reconnectAttempts.current });
      if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        setError('Connection lost. Please refresh the page.');
        es.close();
        return;
      }
      es.close();
      reconnectAttempts.current += 1;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000);
      reconnectTimer.current = setTimeout(() => connectSSE(sid), delay);
    };
  }, [discussionState]);

  const handleStart = async () => {
    if (!topic.trim()) return;
    log('frontend', 'start_discussion', { topic, model, maxMessages, factCheckEnabled, consensusMode });
    setLoading(true);
    setError(null);
    setPersonas([]);
    setMessages([]);
    setSynthesis(null);
    setMessageIds(new Set());
    setStatusMessage('Starte...');
    setDiscussionState('GENERATING');
    try {
      const { sessionId: sid } = await startDiscussion(topic, parseInt(maxMessages) || 50, model, factCheckEnabled, consensusMode);
      setSessionId(sid);
      log('frontend', 'session_created', { sessionId: sid });

      await pollGenerationStatus(sid, (status, message, currentPersonas, modName) => {
        setStatusMessage(message);
        if (currentPersonas.length > 0) {
          setPersonas(currentPersonas);
        }
        if (modName) {
          setModeratorName(modName);
        }
        if (status === 'ready') {
          setDiscussionState('PANEL_READY');
          log('frontend', 'panel_ready', { personaCount: currentPersonas.length });
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setDiscussionState('IDLE');
      log('frontend', 'start_error', { error: e });
    } finally {
      setLoading(false);
    }
  };

  const handleStartDiscussion = async () => {
    if (!sessionId) return;
    log('frontend', 'discussion_starting', { sessionId });
    setDiscussionState('STARTING');
    connectSSE(sessionId);

    const res = await fetch(`${API_BASE_URL}/api/discussion/${sessionId}/start-discussion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_messages: parseInt(maxMessages) || 30 }),
    });
    const data = await res.json();
    if (data.moderator_name) {
      setModeratorName(data.moderator_name);
      log('frontend', 'moderator_assigned', { name: data.moderator_name });
    }
  };

  const handlePause = async () => {
    if (!sessionId) return;
    log('frontend', 'discussion_paused');
    await fetch(`${API_BASE_URL}/api/discussion/${sessionId}/pause`, { method: 'POST' });
    setDiscussionState('PAUSED');
  };

  const handleResume = async () => {
    if (!sessionId) return;
    log('frontend', 'discussion_resumed');
    await fetch(`${API_BASE_URL}/api/discussion/${sessionId}/resume`, { method: 'POST' });
    setDiscussionState('DISCUSSION');
  };

  const handleStop = async () => {
    if (!sessionId) return;
    log('frontend', 'discussion_stopping');
    try {
      const result = await stopDiscussion(sessionId);
      if (result.synthesis) {
        setSynthesis(result.synthesis);
        setDiscussionState('SYNTHESIS');
        log('frontend', 'synthesis_received', { length: result.synthesis.length });
      } else {
        setDiscussionState('COMPLETED');
        log('frontend', 'discussion_completed');
      }
    } catch (e) {
      setDiscussionState('COMPLETED');
      log('frontend', 'stop_error', { error: e });
    }
    eventSourceRef.current?.close();
  };

  const handleInject = async () => {
    if (!sessionId || !injectText.trim()) return;
    log('frontend', 'injecting_instruction', { instruction: injectText });
    try {
      await injectInstruction(sessionId, injectText);
      setInjectText('');
      setShowInject(false);
      if (discussionState === 'PAUSED') {
        await fetch(`${API_BASE_URL}/api/discussion/${sessionId}/resume`, { method: 'POST' });
        setDiscussionState('DISCUSSION');
      }
    } catch (e) {
      log('frontend', 'inject_error', { error: e });
    }
  };

  const handleRestart = () => {
    eventSourceRef.current?.close();
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectAttempts.current = 0;
    setSessionId(null);
    setPersonas([]);
    setMessages([]);
    setSynthesis(null);
    setTopic('');
    setError(null);
    setStatusMessage('');
    setDiscussionState('IDLE');
    setMaxMessages('50');
    setMaxMessagesInput('50');
    setEditingPersona(null);
    setShowAddForm(false);
  };

  const validateMaxMessages = () => {
    const num = parseInt(maxMessagesInput);
    if (isNaN(num) || num < 10 || num > 999) {
      setMaxMessagesInput('50');
      setMaxMessages('50');
    } else {
      setMaxMessagesInput(String(num));
      setMaxMessages(String(num));
    }
  };

  const handleEditPersona = (p: Persona) => {
    setEditingPersona(p.id);
    setEditForm({ name: p.name, role: p.role, background: p.background, stance: p.stance, emoji: p.emoji || '' });
  };

  const handleSaveEdit = async () => {
    if (!sessionId || !editingPersona) return;
    try {
      await updatePersona(sessionId, editingPersona, editForm);
      setPersonas(prev => prev.map(p => p.id === editingPersona ? { ...p, ...editForm } : p));
      setEditingPersona(null);
      log('frontend', 'persona_updated', { personaId: editingPersona });
    } catch (e) {
      log('frontend', 'persona_update_error', { error: e });
    }
  };

  const handleDeletePersona = async (personaId: string) => {
    if (!sessionId) return;
    try {
      await deletePersona(sessionId, personaId);
      setPersonas(prev => prev.filter(p => p.id !== personaId));
      log('frontend', 'persona_deleted', { personaId });
    } catch (e) {
      log('frontend', 'persona_delete_error', { error: e });
    }
  };

  const handleAddPersona = async () => {
    if (!sessionId || !addForm.name) return;
    try {
      const result = await addPersona(sessionId, addForm);
      setPersonas(prev => [...prev, { id: result.personaId, ...addForm }]);
      setAddForm({ name: '', role: '', background: '', stance: '', emoji: '' });
      setShowAddForm(false);
      log('frontend', 'persona_added', { personaId: result.personaId });
    } catch (e) {
      log('frontend', 'persona_add_error', { error: e });
    }
  };

  const stateLabel = discussionState === 'STARTING' || discussionState === 'INTRODUCTION' ? '👋 Introduction'
    : discussionState === 'DISCUSSION' ? '💬 Discussion'
    : discussionState === 'PAUSED' ? '⏸️ Paused'
    : discussionState === 'COMPLETED' || discussionState === 'SYNTHESIS' ? '✅ Completed'
    : '';

  if (discussionState === 'PANEL_READY') {
    return (
      <PersonaReview
        topic={topic}
        personas={personas}
        setPersonas={setPersonas}
        maxMessages={maxMessages}
        maxMessagesInput={maxMessagesInput}
        factCheckEnabled={factCheckEnabled}
        consensusMode={consensusMode}
        showAddForm={showAddForm}
        addForm={addForm}
        editingPersona={editingPersona}
        editForm={editForm}
        onAddPersona={handleAddPersona}
        onSaveEdit={handleSaveEdit}
        onDeletePersona={handleDeletePersona}
        onEditPersona={handleEditPersona}
        onStartDiscussion={handleStartDiscussion}
        onRestart={handleRestart}
        onMaxMessagesChange={setMaxMessagesInput}
        onMaxMessagesValidate={validateMaxMessages}
        onFactCheckToggle={setFactCheckEnabled}
        onConsensusToggle={setConsensusMode}
        onShowAddForm={setShowAddForm}
        onAddFormChange={setAddForm}
        onEditFormChange={setEditForm}
        onEditingPersonaChange={setEditingPersona}
      />
    );
  }

  if (discussionState === 'IDLE' || discussionState === 'GENERATING') {
    return (
      <TopicInput
        topic={topic}
        setTopic={setTopic}
        model={model}
        setModel={setModel}
        loading={loading}
        statusMessage={statusMessage}
        error={error}
        onStart={handleStart}
      />
    );
  }

  return (
    <DiscussionView
      topic={topic}
      personas={personas}
      messages={messages}
      messageCount={messages.filter(m => m.type === 'AGENT' || m.type === 'MODERATOR').length}
      synthesis={synthesis}
      moderatorName={moderatorName}
      discussionState={discussionState}
      stateLabel={stateLabel}
      onPause={handlePause}
      onResume={handleResume}
      onStop={handleStop}
      onRestart={handleRestart}
      onShowInject={setShowInject}
      showInject={showInject}
      injectText={injectText}
      onInjectTextChange={setInjectText}
      onInject={handleInject}
    />
  );
}

export default function AppWithBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}