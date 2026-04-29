import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  startDiscussion,
  getDiscussion,
  pauseDiscussion,
  stopDiscussion,
  exportDiscussion,
} from '../src/services/api';
import { ExportFormat, DiscussionState, AgentType } from '../src/types';

describe('API Client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('startDiscussion', () => {
    it('should start a discussion and return sessionId and personas', async () => {
      const mockResponse = {
        session_id: 'session-123',
        personas: [
          {
            id: 'agent-1',
            name: 'Alice',
            role: 'Proponent',
            background: 'Expert in economics',
            stance: 'Pro',
            type: AgentType.PERSONA,
          },
        ],
      };

      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await startDiscussion('Climate Change');

      expect(result).toEqual({ sessionId: 'session-123' });
    });

    it('should throw error when response is not ok', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error'),
      });

      await expect(startDiscussion('Test')).rejects.toThrow(
        'Failed to start discussion: 500 Internal Server Error'
      );
    });
  });

  describe('getDiscussion', () => {
    it('should get discussion by sessionId', async () => {
      const mockSession = {
        id: 'session-123',
        topic: 'Climate Change',
        state: DiscussionState.ACTIVE,
        conversationLog: [],
        agents: [],
        config: { maxMessages: 50, language: 'en', model: 'gpt-4' },
      };

      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockSession),
      });

      const result = await getDiscussion('session-123');

      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/discussion/session-123'
      );
      expect(result).toEqual(mockSession);
    });

    it('should throw error when response is not ok', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 404,
        text: () => Promise.resolve('Not Found'),
      });

      await expect(getDiscussion('invalid-id')).rejects.toThrow(
        'Failed to get discussion: 404 Not Found'
      );
    });
  });

  describe('pauseDiscussion', () => {
    it('should pause a discussion', async () => {
      const mockResponse = { state: 'PAUSED' };

      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await pauseDiscussion('session-123');

      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/discussion/session-123/pause',
        { method: 'POST' }
      );
      expect(result).toEqual(mockResponse);
    });

    it('should throw error when response is not ok', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 400,
        text: () => Promise.resolve('Bad Request'),
      });

      await expect(pauseDiscussion('session-123')).rejects.toThrow(
        'Failed to pause discussion: 400 Bad Request'
      );
    });
  });

  describe('stopDiscussion', () => {
    it('should stop a discussion', async () => {
      const mockResponse = { state: 'COMPLETED' };

      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await stopDiscussion('session-123');

      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/discussion/session-123/stop',
        { method: 'POST' }
      );
      expect(result).toEqual(mockResponse);
    });

    it('should throw error when response is not ok', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 400,
        text: () => Promise.resolve('Bad Request'),
      });

      await expect(stopDiscussion('session-123')).rejects.toThrow(
        'Failed to stop discussion: 400 Bad Request'
      );
    });
  });

  describe('exportDiscussion', () => {
    it('should export a discussion as blob', async () => {
      const mockBlob = new Blob(['exported content'], { type: 'text/plain' });

      fetchMock.mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(mockBlob),
      });

      const result = await exportDiscussion('session-123', ExportFormat.TEXT);

      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/discussion/session-123/export?format=TEXT'
      );
      expect(result).toEqual(mockBlob);
    });

    it('should throw error when response is not ok', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error'),
      });

      await expect(
        exportDiscussion('session-123', ExportFormat.MARKDOWN)
      ).rejects.toThrow('Failed to export discussion: 500 Internal Server Error');
    });
  });
});