import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TopicInput } from '../../src/components/TopicInput';

describe('TopicInput', () => {
  const defaultProps = {
    topic: '',
    setTopic: vi.fn(),
    model: 'qwen3-coder-next',
    setModel: vi.fn(),
    loading: false,
    statusMessage: '',
    error: null as string | null,
    onStart: vi.fn(),
  };

  it('renders title and input field', () => {
    render(<TopicInput {...defaultProps} />);
    expect(screen.getByText('DebatePanel')).toBeTruthy();
    expect(screen.getByPlaceholderText('Enter a topic...')).toBeTruthy();
  });

  it('calls onStart when button clicked with topic', () => {
    const onStart = vi.fn();
    render(<TopicInput {...defaultProps} topic="Test topic" onStart={onStart} />);
    fireEvent.click(screen.getByText('Generate Panel'));
    expect(onStart).toHaveBeenCalled();
  });

  it('does not call onStart when topic is empty', () => {
    const onStart = vi.fn();
    render(<TopicInput {...defaultProps} topic="" onStart={onStart} />);
    fireEvent.click(screen.getByText('Generate Panel'));
    expect(onStart).not.toHaveBeenCalled();
  });

  it('shows loading state', () => {
    render(<TopicInput {...defaultProps} loading={true} statusMessage="Generating..." />);
    expect(screen.getByText('Generating Panel...')).toBeTruthy();
    expect(screen.getByText('Generating...')).toBeTruthy();
  });

  it('shows error message', () => {
    render(<TopicInput {...defaultProps} error="Test error" />);
    expect(screen.getByText('Test error')).toBeTruthy();
  });

  it('renders model selector with options', () => {
    render(<TopicInput {...defaultProps} />);
    const select = screen.getByRole('combobox');
    expect(select).toBeTruthy();
    expect(screen.getByText('Qwen 3 Coder Next (fast)')).toBeTruthy();
  });
});
