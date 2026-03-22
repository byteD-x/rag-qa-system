export interface KBVersionSummaryItem {
  key: string;
  title: string;
  excerpt: string;
  char_count: number;
}

export interface KBVersionSummaryResult {
  items: KBVersionSummaryItem[];
  hidden_section_count: number;
  total_section_count: number;
  fallback_excerpt: string;
}

function normalizeText(value: unknown): string {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim();
}

function truncateText(value: string, maxChars: number): string {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`;
}

export function buildVersionSummary(
  document: any,
  options: {
    maxItems?: number;
    maxChars?: number;
  } = {}
): KBVersionSummaryResult {
  const maxItems = Math.max(1, Number(options.maxItems || 5));
  const maxChars = Math.max(40, Number(options.maxChars || 160));
  const sections = Array.isArray(document?.sections) ? document.sections : [];
  const normalizedSections = sections
    .map((section: any, index: number) => {
      const title = normalizeText(section?.section_title) || `Section ${Number(section?.section_index ?? index) + 1}`;
      const text = normalizeText(section?.text_content);
      if (!text) {
        return null;
      }
      return {
        key: `${Number(section?.section_index ?? index)}:${title}`,
        title,
        excerpt: truncateText(text, maxChars),
        char_count: text.length
      };
    })
    .filter(Boolean) as KBVersionSummaryItem[];
  const totalSectionCount = Math.max(normalizedSections.length, Number(document?.section_count || 0));
  const items = normalizedSections.slice(0, maxItems);
  const fallbackText = normalizeText(document?.full_text);
  return {
    items,
    hidden_section_count: Math.max(0, totalSectionCount - items.length),
    total_section_count: totalSectionCount,
    fallback_excerpt: items.length ? '' : truncateText(fallbackText, maxChars * 2)
  };
}
