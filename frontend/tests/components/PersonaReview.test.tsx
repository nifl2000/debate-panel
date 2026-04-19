import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PersonaReview } from '../../src/components/PersonaReview';
import { PersonaData } from '../../src/services/api';

describe('PersonaReview', () => {
  const defaultProps = {
    topic: 'Test Topic',
    personas: [
      { id: 'p1', name: 'Alice', role: 'Scientist', background: 'Researcher', stance: 'Pro science', emoji: '👩‍🔬' },
      { id: 'p2', name: 'Bob', role: 'Engineer', background: 'Developer', stance: 'Pro tech', emoji: '👨‍💻' },
    ],
    setPersonas: vi.fn(),
    maxMessages: '50',
    maxMessagesInput: '50',
    factCheckEnabled: false,
    consensusMode: false,
    showAddForm: false,
    addForm: { name: '', role: '', background: '', stance: '', emoji: '👤' } as PersonaData,
    editingPersona: null as string | null,
    editForm: { name: '', role: '', background: '', stance: '', emoji: '👤' } as PersonaData,
    onAddPersona: vi.fn(),
    onSaveEdit: vi.fn(),
    onDeletePersona: vi.fn(),
    onEditPersona: vi.fn(),
    onStartDiscussion: vi.fn(),
    onRestart: vi.fn(),
    onMaxMessagesChange: vi.fn(),
    onMaxMessagesValidate: vi.fn(),
    onFactCheckToggle: vi.fn(),
    onConsensusToggle: vi.fn(),
    onShowAddForm: vi.fn(),
    onAddFormChange: vi.fn(),
    onEditFormChange: vi.fn(),
    onEditingPersonaChange: vi.fn(),
  };

  it('renders topic and persona count', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByText('Topic: Test Topic')).toBeTruthy();
    expect(screen.getByText('Panel (2 Members)')).toBeTruthy();
  });

  it('renders personas with name, role, background and stance', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByText('Alice')).toBeTruthy();
    expect(screen.getByText('Scientist')).toBeTruthy();
    expect(screen.getByText('Researcher')).toBeTruthy();
    expect(screen.getByText('Pro science')).toBeTruthy();
    expect(screen.getByText('Bob')).toBeTruthy();
    expect(screen.getByText('Engineer')).toBeTruthy();
  });

  it('renders add persona button', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByText('+ Add Persona')).toBeTruthy();
  });

  it('calls onShowAddForm when add button clicked', () => {
    const onShowAddForm = vi.fn();
    render(<PersonaReview {...defaultProps} onShowAddForm={onShowAddForm} />);
    fireEvent.click(screen.getByText('+ Add Persona'));
    expect(onShowAddForm).toHaveBeenCalledWith(true);
  });

  it('shows add form when showAddForm is true', () => {
    render(<PersonaReview {...defaultProps} showAddForm={true} />);
    expect(screen.getByText('Add New Persona')).toBeTruthy();
  });

  it('calls onDeletePersona when delete button clicked', () => {
    const onDeletePersona = vi.fn();
    render(<PersonaReview {...defaultProps} onDeletePersona={onDeletePersona} />);
    fireEvent.click(screen.getAllByText('🗑️ Delete')[0]);
    expect(onDeletePersona).toHaveBeenCalledWith('p1');
  });

  it('calls onEditPersona when edit button clicked', () => {
    const onEditPersona = vi.fn();
    render(<PersonaReview {...defaultProps} onEditPersona={onEditPersona} />);
    fireEvent.click(screen.getAllByText('✏️ Edit')[0]);
    expect(onEditPersona).toHaveBeenCalledWith(defaultProps.personas[0]);
  });

  it('shows edit form when editingPersona is set', () => {
    render(<PersonaReview {...defaultProps} editingPersona="p1" />);
    expect(screen.getByText('Cancel')).toBeTruthy();
    expect(screen.getByText('Save')).toBeTruthy();
  });

  it('calls onSaveEdit when save button clicked in edit mode', () => {
    const onSaveEdit = vi.fn();
    render(<PersonaReview {...defaultProps} editingPersona="p1" onSaveEdit={onSaveEdit} />);
    fireEvent.click(screen.getByText('Save'));
    expect(onSaveEdit).toHaveBeenCalled();
  });

  it('calls onEditingPersonaChange when cancel button clicked in edit mode', () => {
    const onEditingPersonaChange = vi.fn();
    render(<PersonaReview {...defaultProps} editingPersona="p1" onEditingPersonaChange={onEditingPersonaChange} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onEditingPersonaChange).toHaveBeenCalledWith(null);
  });

  it('renders max messages input', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByDisplayValue('50')).toBeTruthy();
  });

  it('calls onMaxMessagesChange when max messages input changes', () => {
    const onMaxMessagesChange = vi.fn();
    render(<PersonaReview {...defaultProps} onMaxMessagesChange={onMaxMessagesChange} />);
    const input = screen.getByDisplayValue('50');
    fireEvent.change(input, { target: { value: '100' } });
    expect(onMaxMessagesChange).toHaveBeenCalledWith('100');
  });

  it('renders fact check checkbox', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByText('🔍 Fact Check')).toBeTruthy();
  });

  it('calls onFactCheckToggle when fact check checkbox changed', () => {
    const onFactCheckToggle = vi.fn();
    render(<PersonaReview {...defaultProps} onFactCheckToggle={onFactCheckToggle} />);
    const checkboxes = screen.getAllByRole('checkbox');
    const factCheckCheckbox = checkboxes[0];
    fireEvent.click(factCheckCheckbox);
    expect(onFactCheckToggle).toHaveBeenCalledWith(true);
  });

  it('renders consensus mode checkbox', () => {
    render(<PersonaReview {...defaultProps} />);
    expect(screen.getByText('🎯 Work Towards Consensus')).toBeTruthy();
  });

  it('calls onConsensusToggle when consensus checkbox changed', () => {
    const onConsensusToggle = vi.fn();
    render(<PersonaReview {...defaultProps} onConsensusToggle={onConsensusToggle} />);
    const checkboxes = screen.getAllByRole('checkbox');
    const consensusCheckbox = checkboxes[1];
    fireEvent.click(consensusCheckbox);
    expect(onConsensusToggle).toHaveBeenCalledWith(true);
  });

  it('calls onStartDiscussion when start button clicked', () => {
    const onStartDiscussion = vi.fn();
    render(<PersonaReview {...defaultProps} onStartDiscussion={onStartDiscussion} />);
    fireEvent.click(screen.getByText('💬 Start Discussion'));
    expect(onStartDiscussion).toHaveBeenCalled();
  });

  it('calls onRestart when Neues Panel button clicked', () => {
    const onRestart = vi.fn();
    render(<PersonaReview {...defaultProps} onRestart={onRestart} />);
    fireEvent.click(screen.getByText('New Panel'));
    expect(onRestart).toHaveBeenCalled();
  });

  it('hides add form when cancel button clicked in add form', () => {
    const onShowAddForm = vi.fn();
    render(<PersonaReview {...defaultProps} showAddForm={true} onShowAddForm={onShowAddForm} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onShowAddForm).toHaveBeenCalledWith(false);
  });

  it('calls onAddPersona when add button clicked in add form', () => {
    const onAddPersona = vi.fn();
    render(<PersonaReview {...defaultProps} showAddForm={true} onAddPersona={onAddPersona} />);
    fireEvent.click(screen.getByText('Add'));
    expect(onAddPersona).toHaveBeenCalled();
  });
});
