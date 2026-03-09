export function formatBytes(value: number | undefined | null): string {
  if (!value || value <= 0) {
    return '0 B';
  }

  if (value < 1024) {
    return `${value} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function readableText(value: unknown, fallback: string): string {
  const text = String(value ?? '').trim();
  if (!text) {
    return fallback;
  }

  const questionMarks = (text.match(/\?/g) || []).length;
  const looksCorrupted = text.includes('�') || questionMarks >= Math.max(3, Math.floor(text.length / 3));
  return looksCorrupted ? fallback : text;
}
