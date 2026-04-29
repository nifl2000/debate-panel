export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMOptions {
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

export class LLMClient {
  constructor(private ai: Ai) {}

  async complete(
    messages: ChatMessage[],
    options: LLMOptions = {}
  ): Promise<string> {
    const response = await this.ai.run(
      options.model || '@cf/qwen/qwen2.5-72b-instruct',
      {
        messages,
        max_tokens: options.maxTokens ?? 2048,
        temperature: options.temperature ?? 0.7,
      }
    ) as { response?: string };

    if (!response?.response) {
      throw new Error('Empty response from LLM');
    }

    return response.response;
  }

  async *stream(
    messages: ChatMessage[],
    options: LLMOptions = {}
  ): AsyncIterable<string> {
    const stream = await this.ai.run(
      options.model || '@cf/qwen/qwen2.5-72b-instruct',
      {
        messages,
        max_tokens: options.maxTokens ?? 2048,
        temperature: options.temperature ?? 0.7,
        stream: true,
      }
    ) as unknown as ReadableStream;

    const reader = stream.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value);
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6));
            if (parsed.response) {
              yield parsed.response;
            }
          } catch { /* skip */ }
        }
      }
    }
  }
}
