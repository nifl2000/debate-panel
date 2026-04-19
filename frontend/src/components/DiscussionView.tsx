const S = 1.25;

const COLORS = [
  '#2563eb', '#7c3aed', '#059669', '#dc2626', '#d97706',
  '#0891b2', '#4f46e5', '#be185d', '#65a30d', '#ca8a04',
];

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

export function formatMessageContent(content: string): string {
  let formatted = content || '';
  formatted = formatted.replace(/\[AGENT\]\s*/g, '');
  formatted = formatted.replace(/\[MODERATOR\]\s*/g, '');
  formatted = formatted.replace(/\[FACT_CHECK\]\s*/g, '');
  formatted = formatted.replace(/#{1,6}\s*/g, '');
  formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '$1');
  formatted = formatted.replace(/\*([^*]+)\*/g, '$1');
  formatted = formatted.replace(/__([^_]+)__/g, '$1');
  formatted = formatted.replace(/_([^_]+)_/g, '$1');
  formatted = formatted.replace(/`([^`]+)`/g, '$1');
  formatted = formatted.replace(/\r\n/g, '\n');
  formatted = formatted.trim();
  return formatted;
}

interface DiscussionViewProps {
  topic: string;
  personas: Persona[];
  messages: Message[];
  messageCount: number;
  synthesis: string | null;
  moderatorName: string;
  discussionState: 'IDLE' | 'GENERATING' | 'PANEL_READY' | 'STARTING' | 'INTRODUCTION' | 'DISCUSSION' | 'PAUSED' | 'COMPLETED' | 'SYNTHESIS';
  stateLabel: string;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRestart: () => void;
  onShowInject: (show: boolean) => void;
  showInject: boolean;
  injectText: string;
  onInjectTextChange: (text: string) => void;
  onInject: () => void;
}

export function DiscussionView({
  topic,
  personas,
  messages,
  messageCount,
  synthesis,
  moderatorName,
  discussionState,
  stateLabel,
  onPause,
  onResume,
  onStop,
  onRestart,
  onShowInject,
  showInject,
  injectText,
  onInjectTextChange,
  onInject,
}: DiscussionViewProps) {
  return (
    <div style={{ margin: `0 ${10 * S}%`, display: 'flex', height: '100vh', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <div style={{ width: `${280 * S}px`, background: '#f9fafb', borderRight: `1px solid #e5e7eb`, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: `${16 * S}px ${16 * S}px 0`, flexShrink: 0 }}>
          <div style={{ fontSize: `${14 * S}px`, color: '#374151', marginBottom: `${4 * S}px` }}>{topic}</div>
          <div style={{ fontSize: `${12 * S}px`, color: '#6b7280', marginBottom: `${16 * S}px` }}>
            {personas.length} Personas • {stateLabel} • Msg #{messageCount}
          </div>

          <div style={{ padding: `${10 * S}px`, background: '#faf5ff', borderRadius: `${8 * S}px`, border: `1px solid #e9d5ff`, marginBottom: `${12 * S}px` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: `${8 * S}px`, marginBottom: `${4 * S}px` }}>
              <span style={{ fontSize: `${18 * S}px` }}>🎙️</span>
              <div style={{ fontWeight: 700, color: '#7c3aed', fontSize: `${13 * S}px` }}>{moderatorName}</div>
            </div>
            <div style={{ fontSize: `${11 * S}px`, color: '#6b7280' }}>Moderator</div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: `0 ${16 * S}px` }}>
          {personas.filter(p => p?.id).map((p, i) => (
            <div key={p.id} style={{ padding: `${10 * S}px`, background: '#fff', borderRadius: `${8 * S}px`, border: `1px solid #e5e7eb`, marginBottom: `${8 * S}px` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: `${8 * S}px`, marginBottom: `${4 * S}px` }}>
                <span style={{ fontSize: `${18 * S}px` }}>{p.emoji || '👤'}</span>
                <div style={{ fontWeight: 600, color: COLORS[i % COLORS.length], fontSize: `${13 * S}px` }}>{p.name}</div>
              </div>
              <div style={{ fontSize: `${11 * S}px`, color: '#6b7280' }}>{p.role}</div>
            </div>
          ))}
        </div>

        <div style={{ padding: `${16 * S}px`, borderTop: `1px solid #e5e7eb`, flexShrink: 0, background: '#f9fafb' }}>
          <div style={{ fontSize: `${12 * S}px`, color: '#6b7280', marginBottom: `${8 * S}px`, textAlign: 'center' }}>Controls</div>
          <div style={{ display: 'flex', gap: `${8 * S}px`, justifyContent: 'center', flexWrap: 'wrap' }}>
            {discussionState === 'DISCUSSION' && (
              <button onClick={onPause} style={{ padding: `${8 * S}px ${16 * S}px`, background: '#f59e0b', color: '#fff', border: 'none', borderRadius: `${6 * S}px`, cursor: 'pointer', fontSize: `${16 * S}px` }}>⏸️</button>
            )}
            {discussionState === 'PAUSED' && (
              <button onClick={onResume} style={{ padding: `${8 * S}px ${16 * S}px`, background: '#22c55e', color: '#fff', border: 'none', borderRadius: `${6 * S}px`, cursor: 'pointer', fontSize: `${16 * S}px` }}>▶️</button>
            )}
            {(discussionState === 'DISCUSSION' || discussionState === 'PAUSED' || discussionState === 'INTRODUCTION') && (
              <button onClick={() => onShowInject(true)} style={{ padding: `${8 * S}px ${16 * S}px`, background: '#8b5cf6', color: '#fff', border: 'none', borderRadius: `${6 * S}px`, cursor: 'pointer', fontSize: `${16 * S}px` }}>💬</button>
            )}
            {(discussionState === 'DISCUSSION' || discussionState === 'PAUSED' || discussionState === 'INTRODUCTION') && (
              <button onClick={onStop} style={{ padding: `${8 * S}px ${16 * S}px`, background: '#ef4444', color: '#fff', border: 'none', borderRadius: `${6 * S}px`, cursor: 'pointer', fontSize: `${16 * S}px` }}>⏹️</button>
            )}
            {(discussionState === 'COMPLETED' || discussionState === 'SYNTHESIS') && (
              <button onClick={onRestart} style={{ padding: `${8 * S}px ${16 * S}px`, background: '#2563eb', color: '#fff', border: 'none', borderRadius: `${6 * S}px`, cursor: 'pointer', fontSize: `${13 * S}px` }}>New Panel</button>
            )}
          </div>

          {showInject && (
            <div style={{ marginTop: `${12 * S}px`, padding: `${12 * S}px`, background: '#faf5ff', borderRadius: `${8 * S}px`, border: `1px solid #e9d5ff` }}>
              <div style={{ fontSize: `${12 * S}px`, color: '#7c3aed', marginBottom: `${8 * S}px`, fontWeight: 600 }}>💬 Inject Instruction</div>
              <textarea
                value={injectText}
                onChange={(e) => onInjectTextChange(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onInject(); } }}
                placeholder="e.g. 'Discuss more controversially' or 'Mr. Müller changes sides'"
                rows={3}
                style={{ width: '100%', padding: `${8 * S}px`, fontSize: `${13 * S}px`, border: `1px solid #ddd`, borderRadius: `${6 * S}px`, resize: 'vertical', boxSizing: 'border-box' }}
              />
              <div style={{ display: 'flex', gap: `${8 * S}px`, marginTop: `${8 * S}px`, justifyContent: 'flex-end' }}>
                <button onClick={() => { onShowInject(false); onResume(); }} style={{ padding: `${6 * S}px ${12 * S}px`, fontSize: `${12 * S}px`, cursor: 'pointer', background: '#f3f4f6', border: `1px solid #ddd`, borderRadius: `${4 * S}px` }}>Cancel</button>
                <button onClick={onInject} disabled={!injectText.trim()} style={{ padding: `${6 * S}px ${12 * S}px`, fontSize: `${12 * S}px`, cursor: injectText.trim() ? 'pointer' : 'not-allowed', background: '#8b5cf6', color: '#fff', border: 'none', borderRadius: `${4 * S}px` }}>Inject</button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: `${20 * S}px`, minWidth: 0 }}>
          {messages.map((msg, i) => {
            const agentId = msg.agentId || 'unknown';
            const personaIndex = personas.findIndex(p => p?.id && agentId.includes(p.id.slice(-8)));
            const persona = personaIndex >= 0 ? personas[personaIndex] : null;
            const isModerator = msg.type === 'MODERATOR' || agentId.includes('moderator');
            const isFactCheck = msg.type === 'FACT_CHECK';
            const color = isModerator ? '#7c3aed' : isFactCheck ? '#0284c7' : personaIndex >= 0 ? COLORS[personaIndex % COLORS.length] : '#7c3aed';
            const emoji = isModerator ? '🎙️' : isFactCheck ? '🔍' : persona?.emoji || '👤';
            const isSystem = agentId === 'system';
            const isEndMessage = msg.content?.includes('Discussion ended');

            const content = formatMessageContent(msg.content);

            if (!content || content.length < 2) {
              return null;
            }

            return (
              <div key={msg.id || i} style={{
                marginBottom: `${12 * S}px`,
                padding: `${12 * S}px`,
                background: isEndMessage ? '#f0fdf4' : isFactCheck ? '#f0f9ff' : isSystem ? '#f0f9ff' : '#fff',
                borderRadius: `${8 * S}px`,
                border: `1px solid ${isEndMessage ? '#bbf7d0' : isFactCheck ? '#bae6fd' : isSystem ? '#bae6fd' : color + '30'}`,
                borderLeft: `3px solid ${isEndMessage ? '#22c55e' : isFactCheck ? '#0284c7' : isSystem ? '#0284c7' : color}`,
                wordBreak: 'break-word',
                overflowWrap: 'break-word',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: `${6 * S}px`, marginBottom: `${4 * S}px` }}>
                  <span style={{ fontSize: `${16 * S}px` }}>{emoji}</span>
                  <strong style={{ color, fontSize: `${13 * S}px` }}>{isModerator ? moderatorName : isFactCheck ? 'Fact Check' : persona?.name || msg.agentName || msg.agentId}</strong>
                  <span style={{ fontSize: `${10 * S}px`, color: '#9ca3af' }}>{new Date(msg.timestamp).toLocaleTimeString('de-DE')}</span>
                </div>
                <div style={{ fontSize: `${14 * S}px`, lineHeight: 1.6, color: isEndMessage ? '#166534' : '#1f2937', whiteSpace: 'pre-wrap', maxWidth: '100%', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
                  {content}
                </div>
                {isFactCheck && msg.sourceUrl && (
                  <div style={{ marginTop: `${6 * S}px`, fontSize: `${11 * S}px` }}>
                    <a href={msg.sourceUrl} target="_blank" rel="noopener noreferrer" style={{ color: '#0284c7', textDecoration: 'underline' }}>
                      🔗 Quelle
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {synthesis && (
        <div style={{ padding: `${20 * S}px`, borderTop: `2px solid #e5e7eb`, background: '#f9fafb' }}>
          <h3 style={{ fontSize: `${18 * S}px`, marginBottom: `${12 * S}px` }}>📝 Summary</h3>
          <div style={{ fontSize: `${14 * S}px`, lineHeight: 1.7, color: '#1f2937', whiteSpace: 'pre-wrap' }}>
            {synthesis}
          </div>
        </div>
      )}
    </div>
  );
}