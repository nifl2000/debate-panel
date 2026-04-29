export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMOptions {
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

const DEFAULT_MODEL = 'qwen3.6-plus';

export class LLMClient {
  private baseUrl = 'https://coding-intl.dashscope.aliyuncs.com/v1';

  constructor(private apiKey: string) {
    if (!apiKey) throw new Error('DASHSCOPE_API_KEY is required');
  }

  private async callAPI(messages: ChatMessage[], options: LLMOptions, streaming: boolean): Promise<Response> {
    const model = options.model || DEFAULT_MODEL;
    const url = streaming
      ? `${this.baseUrl}/chat/completions`
      : `${this.baseUrl}/chat/completions`;

    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
        'User-Agent': 'Mozilla/5.0 (compatible; DebatePanel/1.0)',
        'Accept': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages,
        max_tokens: options.maxTokens ?? 2048,
        temperature: options.temperature ?? 0.7,
        stream: streaming,
      }),
    });
  }

  async complete(
    messages: ChatMessage[],
    options: LLMOptions = {}
  ): Promise<string> {
    const response = await this.callAPI(messages, options, false);

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`LLM API error ${response.status}: ${text}`);
    }

    const data = await response.json() as { choices?: { message?: { content: string } }[] };
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error('Empty response from LLM');
    return content;
  }

  async *stream(
    messages: ChatMessage[],
    options: LLMOptions = {}
  ): AsyncIterable<string> {
    const response = await this.callAPI(messages, options, true);

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`LLM API error ${response.status}: ${text}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        const data = trimmed.slice(6);
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data) as { choices?: { delta?: { content?: string } }[] };
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) yield content;
        } catch { /* skip malformed */ }
      }
    }
  }
}
