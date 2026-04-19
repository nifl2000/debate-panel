import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DiscussionView, formatMessageContent } from '../../src/components/DiscussionView';

describe('formatMessageContent', () => {
  it('removes markdown formatting', () => {
    expect(formatMessageContent('**bold** text')).toBe('bold text');
    expect(formatMessageContent('*italic* text')).toBe('italic text');
    expect(formatMessageContent('`code` text')).toBe('code text');
  });

  it('removes agent type prefixes', () => {
    expect(formatMessageContent('[AGENT] Hello')).toBe('Hello');
    expect(formatMessageContent('[MODERATOR] Hello')).toBe('Hello');
    expect(formatMessageContent('[FACT_CHECK] Hello')).toBe('Hello');
  });

  it('removes headers', () => {
    expect(formatMessageContent('# Header text')).toBe('Header text');
    expect(formatMessageContent('## Header text')).toBe('Header text');
  });

  it('trims whitespace', () => {
    expect(formatMessageContent('  hello  ')).toBe('hello');
  });

  it('handles empty input', () => {
    expect(formatMessageContent('')).toBe('');
    expect(formatMessageContent('   ')).toBe('');
  });
});

describe('DiscussionView', () => {
  const defaultProps = {
    topic: 'Test topic',
    personas: [
      { id: 'p1', name: 'Alice', role: 'Scientist', background: 'bg', stance: 'pro', emoji: '👩‍🔬' },
    ],
    messages: [],
    synthesis: null,
    moderatorName: 'Clara',
    discussionState: 'DISCUSSION' as const,
    stateLabel: '💬 Discussion',
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    onRestart: vi.fn(),
    onShowInject: vi.fn(),
    showInject: false,
    injectText: '',
    onInjectTextChange: vi.fn(),
    onInject: vi.fn(),
  };

  it('renders topic and persona count', () => {
    render(<DiscussionView {...defaultProps} />);
    expect(screen.getByText('Test topic')).toBeTruthy();
    expect(screen.getByText('1 Personas • 💬 Discussion')).toBeTruthy();
  });

  it('renders moderator in sidebar', () => {
    render(<DiscussionView {...defaultProps} />);
    expect(screen.getByText('Clara')).toBeTruthy();
    expect(screen.getByText('Moderator')).toBeTruthy();
  });

  it('renders personas in sidebar', () => {
    render(<DiscussionView {...defaultProps} />);
    expect(screen.getByText('Alice')).toBeTruthy();
    expect(screen.getByText('Scientist')).toBeTruthy();
  });

  it('shows pause button in DISCUSSION state', () => {
    render(<DiscussionView {...defaultProps} discussionState="DISCUSSION" />);
    expect(screen.getByText('⏸️')).toBeTruthy();
    expect(screen.getByText('⏹️')).toBeTruthy();
  });

  it('shows resume button in PAUSED state', () => {
    render(<DiscussionView {...defaultProps} discussionState="PAUSED" />);
    expect(screen.getByText('▶️')).toBeTruthy();
  });

  it('shows Neues Panel button in COMPLETED state', () => {
    render(<DiscussionView {...defaultProps} discussionState="COMPLETED" />);
    expect(screen.getByText('Neues Panel')).toBeTruthy();
  });

  it('renders messages', () => {
    const messages = [{
      id: 'm1',
      agentId: 'p1',
      agentName: 'Alice',
      content: 'Hello world',
      timestamp: '2024-01-01T00:00:00',
      type: 'AGENT',
    }];
    render(<DiscussionView {...defaultProps} messages={messages} />);
    expect(screen.getAllByText('Alice').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Hello world')).toBeTruthy();
  });

  it('renders synthesis when provided', () => {
    render(<DiscussionView {...defaultProps} synthesis="Test synthesis" />);
    expect(screen.getByText('📝 Summary')).toBeTruthy();
    expect(screen.getByText('Test synthesis')).toBeTruthy();
  });

  it('shows inject button in DISCUSSION state', () => {
    render(<DiscussionView {...defaultProps} discussionState="DISCUSSION" />);
    expect(screen.getByText('💬')).toBeTruthy();
  });

  it('calls onPause when pause button clicked', () => {
    const onPause = vi.fn();
    render(<DiscussionView {...defaultProps} onPause={onPause} />);
    fireEvent.click(screen.getByText('⏸️'));
    expect(onPause).toHaveBeenCalled();
  });
});
