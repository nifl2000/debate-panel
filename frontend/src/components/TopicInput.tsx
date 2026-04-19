const S = 1.25;

export const MODELS = [
  { value: 'qwen3-coder-next', label: 'Qwen 3 Coder Next (fast)' },
  { value: 'qwen3.6-plus', label: 'Qwen 3.6 Plus' },
  { value: 'kimi-k2.5', label: 'Kimi K2.5' },
  { value: 'glm-5', label: 'GLM 5' },
  { value: 'MiniMax-M2.5', label: 'MiniMax M2.5' },
];

interface TopicInputProps {
  topic: string;
  setTopic: (topic: string) => void;
  model: string;
  setModel: (model: string) => void;
  loading: boolean;
  statusMessage: string;
  error: string | null;
  onStart: () => void;
}

export function TopicInput({
  topic,
  setTopic,
  model,
  setModel,
  loading,
  statusMessage,
  error,
  onStart,
}: TopicInputProps) {
  return (
    <div style={{ margin: `0 ${10 * S}%`, fontFamily: 'system-ui, -apple-system, sans-serif', padding: `${20 * S}px 0`, textAlign: 'center' }}>
      <h1 style={{ fontSize: `${32 * S}px`, marginBottom: `${8 * S}px` }}>DebatePanel</h1>
        <p style={{ color: '#6b7280', marginBottom: `${32 * S}px` }}>Generate a diverse AI discussion panel</p>

      <div style={{ display: 'flex', gap: `${12 * S}px`, marginBottom: `${16 * S}px` }}>
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onStart()}
          placeholder="Enter a topic..."
          style={{ flex: 1, padding: `${14 * S}px ${18 * S}px`, fontSize: `${18 * S}px`, boxSizing: 'border-box', border: `2px solid #e5e7eb`, borderRadius: `${10 * S}px`, outline: 'none' }}
        />
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          style={{ padding: `${14 * S}px ${12 * S}px`, fontSize: `${14 * S}px`, border: `2px solid #e5e7eb`, borderRadius: `${10 * S}px`, background: '#fff', cursor: 'pointer', minWidth: `${180 * S}px` }}
        >
          {MODELS.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>
      <button
        onClick={onStart}
        disabled={loading || !topic.trim()}
        style={{ padding: `${14 * S}px ${32 * S}px`, fontSize: `${18 * S}px`, cursor: loading ? 'wait' : 'pointer', background: '#2563eb', color: '#fff', border: 'none', borderRadius: `${10 * S}px`, fontWeight: 600 }}
      >
        {loading ? 'Generating Panel...' : 'Generate Panel'}
      </button>

      {loading && (
        <div style={{ marginTop: `${32 * S}px`, padding: `${24 * S}px`, background: '#f0f9ff', borderRadius: `${12 * S}px`, border: `1px solid #bae6fd` }}>
          <div style={{ fontSize: `${24 * S}px`, marginBottom: `${12 * S}px` }}>
            {statusMessage.includes('Detecting') || statusMessage.includes('Sprache') ? '🌍' :
             statusMessage.includes('Panel') || statusMessage.includes('Generating') ? '🎯' :
             statusMessage.includes('Persona') || statusMessage.includes('Creating') ? '👤' :
             statusMessage.includes('discussion') || statusMessage.includes('Diskussion') ? '🎬' :
             statusMessage.includes('ready') || statusMessage.includes('bereit') ? '✅' : '⏳'}
          </div>
          <div style={{ fontSize: `${16 * S}px`, color: '#0369a1', fontWeight: 500 }}>{statusMessage}</div>
          <div style={{ marginTop: `${16 * S}px`, height: `${4 * S}px`, background: '#e0f2fe', borderRadius: `${2 * S}px`, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              background: '#0284c7',
              borderRadius: `${2 * S}px`,
              width: statusMessage.includes('Detecting') || statusMessage.includes('Sprache') ? '15%' :
                     statusMessage.includes('Panel') || statusMessage.includes('Generating') ? '35%' :
                     statusMessage.includes('Persona') || statusMessage.includes('Creating') ? '60%' :
                     statusMessage.includes('discussion') || statusMessage.includes('Diskussion') ? '85%' :
                     statusMessage.includes('ready') || statusMessage.includes('bereit') ? '100%' : '5%',
              transition: 'width 0.5s ease'
            }} />
          </div>
        </div>
      )}

      {error && <p style={{ color: '#dc2626', marginTop: `${16 * S}px` }}>{error}</p>}
    </div>
  );
}