import { PersonaData } from '../services/api';

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

interface PersonaReviewProps {
  topic: string;
  personas: Persona[];
  setPersonas: (personas: Persona[]) => void;
  maxMessages: string;
  maxMessagesInput: string;
  factCheckEnabled: boolean;
  consensusMode: boolean;
  showAddForm: boolean;
  addForm: PersonaData;
  editingPersona: string | null;
  editForm: PersonaData;
  onAddPersona: () => void;
  onSaveEdit: () => void;
  onDeletePersona: (personaId: string) => void;
  onEditPersona: (persona: Persona) => void;
  onStartDiscussion: () => void;
  onRestart: () => void;
  onMaxMessagesChange: (value: string) => void;
  onMaxMessagesValidate: () => void;
  onFactCheckToggle: (enabled: boolean) => void;
  onConsensusToggle: (enabled: boolean) => void;
  onShowAddForm: (show: boolean) => void;
  onAddFormChange: (form: PersonaData) => void;
  onEditFormChange: (form: PersonaData) => void;
  onEditingPersonaChange: (id: string | null) => void;
}

export function PersonaReview({
  topic,
  personas,
  maxMessagesInput,
  factCheckEnabled,
  consensusMode,
  showAddForm,
  addForm,
  editingPersona,
  editForm,
  onAddPersona,
  onSaveEdit,
  onDeletePersona,
  onEditPersona,
  onStartDiscussion,
  onRestart,
  onMaxMessagesChange,
  onMaxMessagesValidate,
  onFactCheckToggle,
  onConsensusToggle,
  onShowAddForm,
  onAddFormChange,
  onEditFormChange,
  onEditingPersonaChange,
}: PersonaReviewProps) {
  return (
    <div style={{ margin: `0 ${10 * S}%`, fontFamily: 'system-ui, -apple-system, sans-serif', padding: `${20 * S}px 0` }}>
      <div style={{ textAlign: 'center', marginBottom: `${32 * S}px` }}>
        <h1 style={{ fontSize: `${28 * S}px`, marginBottom: `${8 * S}px` }}>DebatePanel</h1>
        <p style={{ color: '#6b7280' }}>Topic: {topic}</p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: `${16 * S}px` }}>
        <h2 style={{ fontSize: `${18 * S}px`, margin: 0 }}>Panel ({personas.length} Members)</h2>
        <button
          onClick={() => { onShowAddForm(true); onAddFormChange({ name: '', role: '', background: '', stance: '', emoji: '👤' }); }}
          style={{ padding: `${8 * S}px ${16 * S}px`, fontSize: `${14 * S}px`, cursor: 'pointer', background: '#2563eb', color: '#fff', border: 'none', borderRadius: `${6 * S}px` }}
        >
          + Add Persona
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: `${12 * S}px`, marginBottom: `${24 * S}px` }}>
        {personas.filter(p => p?.id).map((p, i) => {
          const color = COLORS[i % COLORS.length];
          const isEditing = editingPersona === p.id;

          if (isEditing) {
            return (
              <div key={p.id} style={{ padding: `${16 * S}px`, background: '#fff', borderRadius: `${10 * S}px`, border: `2px solid ${color}`, borderLeft: `4px solid ${color}` }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: `${8 * S}px` }}>
                  <div style={{ display: 'flex', gap: `${8 * S}px` }}>
                    <input value={editForm.emoji} onChange={e => onEditFormChange({ ...editForm, emoji: e.target.value })} style={{ width: `${40 * S}px`, fontSize: `${20 * S}px`, textAlign: 'center', border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
                    <input value={editForm.name} onChange={e => onEditFormChange({ ...editForm, name: e.target.value })} placeholder="Name" style={{ flex: 1, padding: `${6 * S}px ${10 * S}px`, fontSize: `${14 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
                    <input value={editForm.role} onChange={e => onEditFormChange({ ...editForm, role: e.target.value })} placeholder="Rolle" style={{ flex: 1, padding: `${6 * S}px ${10 * S}px`, fontSize: `${14 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
                  </div>
                  <textarea value={editForm.background} onChange={e => onEditFormChange({ ...editForm, background: e.target.value })} placeholder="Hintergrund" rows={2} style={{ padding: `${6 * S}px ${10 * S}px`, fontSize: `${13 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px`, resize: 'vertical' }} />
                  <textarea value={editForm.stance} onChange={e => onEditFormChange({ ...editForm, stance: e.target.value })} placeholder="Haltung" rows={2} style={{ padding: `${6 * S}px ${10 * S}px`, fontSize: `${13 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px`, resize: 'vertical' }} />
                  <div style={{ display: 'flex', gap: `${8 * S}px`, justifyContent: 'flex-end' }}>
                    <button onClick={() => onEditingPersonaChange(null)} style={{ padding: `${6 * S}px ${16 * S}px`, fontSize: `${13 * S}px`, cursor: 'pointer', background: '#f3f4f6', border: `1px solid #ddd`, borderRadius: `${4 * S}px` }}>Cancel</button>
                    <button onClick={onSaveEdit} style={{ padding: `${6 * S}px ${16 * S}px`, fontSize: `${13 * S}px`, cursor: 'pointer', background: '#22c55e', color: '#fff', border: 'none', borderRadius: `${4 * S}px` }}>Save</button>
                  </div>
                </div>
              </div>
            );
          }

          return (
            <div key={p.id} style={{ padding: `${16 * S}px`, background: '#fff', borderRadius: `${10 * S}px`, border: `2px solid ${color}20`, borderLeft: `4px solid ${color}` }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: `${12 * S}px`, marginBottom: `${8 * S}px` }}>
                <span style={{ fontSize: `${24 * S}px` }}>{p.emoji || '👤'}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, color, fontSize: `${16 * S}px` }}>{p.name}</div>
                  <div style={{ fontSize: `${13 * S}px`, color: '#6b7280' }}>{p.role}</div>
                </div>
                <div style={{ display: 'flex', gap: `${6 * S}px` }}>
                  <button onClick={() => onEditPersona(p)} style={{ padding: `${4 * S}px ${10 * S}px`, fontSize: `${12 * S}px`, cursor: 'pointer', background: '#f0f9ff', color: '#0284c7', border: `1px solid #bae6fd`, borderRadius: `${4 * S}px` }}>✏️ Edit</button>
                  <button onClick={() => onDeletePersona(p.id)} style={{ padding: `${4 * S}px ${10 * S}px`, fontSize: `${12 * S}px`, cursor: 'pointer', background: '#fef2f2', color: '#dc2626', border: `1px solid #fecaca`, borderRadius: `${4 * S}px` }}>🗑️ Delete</button>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: `${12 * S}px` }}>
                <div>
                  <div style={{ fontSize: `${10 * S}px`, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', marginBottom: `${2 * S}px` }}>Hintergrund</div>
                  <div style={{ fontSize: `${13 * S}px`, lineHeight: 1.5, color: '#374151' }}>{p.background}</div>
                </div>
                <div>
                  <div style={{ fontSize: `${10 * S}px`, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', marginBottom: `${2 * S}px` }}>Haltung</div>
                  <div style={{ fontSize: `${13 * S}px`, lineHeight: 1.5, color: '#374151' }}>{p.stance}</div>
                </div>
              </div>
            </div>
          );
        })}

        {showAddForm && (
          <div style={{ padding: `${16 * S}px`, background: '#f0fdf4', borderRadius: `${10 * S}px`, border: `2px solid #22c55e`, borderLeft: `4px solid #22c55e` }}>
            <div style={{ fontWeight: 600, marginBottom: `${8 * S}px`, color: '#166534' }}>Add New Persona</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: `${8 * S}px` }}>
              <div style={{ display: 'flex', gap: `${8 * S}px` }}>
                <input value={addForm.emoji} onChange={e => onAddFormChange({ ...addForm, emoji: e.target.value })} style={{ width: `${40 * S}px`, fontSize: `${20 * S}px`, textAlign: 'center', border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
                <input value={addForm.name} onChange={e => onAddFormChange({ ...addForm, name: e.target.value })} placeholder="Name" style={{ flex: 1, padding: `${6 * S}px ${10 * S}px`, fontSize: `${14 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
                <input value={addForm.role} onChange={e => onAddFormChange({ ...addForm, role: e.target.value })} placeholder="Rolle" style={{ flex: 1, padding: `${6 * S}px ${10 * S}px`, fontSize: `${14 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px` }} />
              </div>
              <textarea value={addForm.background} onChange={e => onAddFormChange({ ...addForm, background: e.target.value })} placeholder="Hintergrund" rows={2} style={{ padding: `${6 * S}px ${10 * S}px`, fontSize: `${13 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px`, resize: 'vertical' }} />
              <textarea value={addForm.stance} onChange={e => onAddFormChange({ ...addForm, stance: e.target.value })} placeholder="Haltung" rows={2} style={{ padding: `${6 * S}px ${10 * S}px`, fontSize: `${13 * S}px`, border: `1px solid #ddd`, borderRadius: `${4 * S}px`, resize: 'vertical' }} />
              <div style={{ display: 'flex', gap: `${8 * S}px`, justifyContent: 'flex-end' }}>
                <button onClick={() => onShowAddForm(false)} style={{ padding: `${6 * S}px ${16 * S}px`, fontSize: `${13 * S}px`, cursor: 'pointer', background: '#f3f4f6', border: `1px solid #ddd`, borderRadius: `${4 * S}px` }}>Cancel</button>
                <button onClick={onAddPersona} style={{ padding: `${6 * S}px ${16 * S}px`, fontSize: `${13 * S}px`, cursor: 'pointer', background: '#22c55e', color: '#fff', border: 'none', borderRadius: `${4 * S}px` }}>Add</button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: `${24 * S}px`, marginBottom: `${24 * S}px`, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: `${8 * S}px` }}>
          <label style={{ fontSize: `${14 * S}px`, color: '#6b7280' }}>Max Messages:</label>
          <input
            type="text"
            inputMode="numeric"
            value={maxMessagesInput}
            onChange={(e) => onMaxMessagesChange(e.target.value.replace(/[^0-9]/g, ''))}
            onBlur={onMaxMessagesValidate}
            onKeyDown={(e) => e.key === 'Enter' && onMaxMessagesValidate()}
            style={{ width: `${80 * S}px`, padding: `${8 * S}px ${12 * S}px`, fontSize: `${16 * S}px`, border: `2px solid #e5e7eb`, borderRadius: `${8 * S}px`, textAlign: 'center' }}
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: `${8 * S}px`, fontSize: `${14 * S}px`, color: '#6b7280', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={factCheckEnabled}
            onChange={(e) => onFactCheckToggle(e.target.checked)}
            style={{ width: `${18 * S}px`, height: `${18 * S}px`, cursor: 'pointer' }}
          />
          🔍 Fact Check
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: `${8 * S}px`, fontSize: `${14 * S}px`, color: '#6b7280', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={consensusMode}
            onChange={(e) => onConsensusToggle(e.target.checked)}
            style={{ width: `${18 * S}px`, height: `${18 * S}px`, cursor: 'pointer' }}
          />
          🎯 Work Towards Consensus
        </label>
      </div>

      <div style={{ textAlign: 'center' }}>
        <button
          onClick={onStartDiscussion}
          style={{ padding: `${14 * S}px ${40 * S}px`, fontSize: `${18 * S}px`, cursor: 'pointer', background: '#22c55e', color: '#fff', border: 'none', borderRadius: `${10 * S}px`, fontWeight: 600 }}
        >
          💬 Start Discussion
        </button>
        <button
          onClick={onRestart}
          style={{ padding: `${14 * S}px ${24 * S}px`, fontSize: `${16 * S}px`, cursor: 'pointer', background: '#f3f4f6', color: '#374151', border: `1px solid #ddd`, borderRadius: `${10 * S}px`, marginLeft: `${12 * S}px` }}
        >
          New Panel
        </button>
      </div>
    </div>
  );
}