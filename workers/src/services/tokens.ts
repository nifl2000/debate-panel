export function estimateTokens(text: string): number {
  const cjkChars = (text.match(/[一-鿿぀-ゟ゠-ヿ]/g) || []).length;
  const nonCjkChars = text.length - cjkChars;
  return Math.ceil(cjkChars / 2 + nonCjkChars / 4);
}

export function getWindowedMessages(
  messages: Array<{ role: string; content: string }>,
  maxTokens: number = 8000
): Array<{ role: string; content: string }> {
  const total = messages.reduce((s, m) => s + estimateTokens(m.content), 0);
  if (total <= maxTokens) return messages;

  const result: Array<{ role: string; content: string }> = [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    const testTokens = estimateTokens(msg.content) +
      result.reduce((s, m) => s + estimateTokens(m.content), 0);
    if (testTokens <= maxTokens) {
      result.unshift(msg);
    } else {
      break;
    }
  }
  return result;
}
