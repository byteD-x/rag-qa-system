/**
 * 文本高亮工具
 * 用于搜索结果、关键词匹配等场景
 */

export interface HighlightOptions {
  className?: string;
  caseSensitive?: boolean;
  highlightAll?: boolean;
}

/**
 * 高亮文本中的关键词
 * @param text 原始文本
 * @param keyword 要高亮的关键词
 * @param options 配置选项
 * @returns 包含高亮标记的 HTML 字符串
 */
export function highlightText(
  text: string,
  keyword: string,
  options: HighlightOptions = {}
): string {
  if (!keyword || !text) return text;

  const {
    className = 'highlight',
    caseSensitive = false
  } = options;

  // 转义特殊字符
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  
  // 构建正则表达式
  const flags = caseSensitive ? 'g' : 'gi';
  const regex = new RegExp(`(${escapedKeyword})`, flags);
  
  const highlighted = text.replace(
    regex,
    `<mark class="${className}">$1</mark>`
  );

  return highlighted;
}

/**
 * 高亮多个关键词
 * @param text 原始文本
 * @param keywords 关键词数组
 * @param options 配置选项
 * @returns 包含高亮标记的 HTML 字符串
 */
export function highlightMultiple(
  text: string,
  keywords: string[],
  options: HighlightOptions = {}
): string {
  if (!keywords.length || !text) return text;

  let result = text;
  
  // 按长度降序排序，避免短词匹配长词中的内容
  const sortedKeywords = [...keywords].sort((a, b) => b.length - a.length);
  
  for (const keyword of sortedKeywords) {
    result = highlightText(result, keyword, options);
  }

  return result;
}

/**
 * 移除高亮标记
 * @param html 包含高亮标记的 HTML
 * @returns 纯文本
 */
export function removeHighlight(html: string): string {
  const temp = document.createElement('div');
  temp.innerHTML = html;
  return temp.textContent || temp.innerText || '';
}

/**
 * 获取高亮文本的纯文本版本（用于安全渲染）
 * @param text 原始文本
 * @param keyword 关键词
 * @param options 配置选项
 * @returns 安全的文本对象
 */
export function createHighlightSafe(
  text: string,
  keyword: string,
  options: HighlightOptions = {}
): { __html: string } {
  return {
    __html: highlightText(text, keyword, options)
  };
}

/**
 * 计算关键词在文本中的位置
 * @param text 原始文本
 * @param keyword 关键词
 * @returns 匹配位置数组
 */
export function findKeywordPositions(
  text: string,
  keyword: string,
  caseSensitive = false
): Array<{ start: number; end: number }> {
  if (!keyword || !text) return [];

  const positions: Array<{ start: number; end: number }> = [];
  const searchText = caseSensitive ? text : text.toLowerCase();
  const searchKeyword = caseSensitive ? keyword : keyword.toLowerCase();
  
  let index = searchText.indexOf(searchKeyword);
  
  while (index !== -1) {
    positions.push({
      start: index,
      end: index + searchKeyword.length
    });
    index = searchText.indexOf(searchKeyword, index + 1);
  }

  return positions;
}

/**
 * 截取并高亮文本（用于搜索结果摘要）
 * @param text 完整文本
 * @param keyword 关键词
 * @param maxLength 最大长度
 * @param options 配置选项
 * @returns 截取后的高亮文本
 */
export function truncateAndHighlight(
  text: string,
  keyword: string,
  maxLength = 200,
  options: HighlightOptions = {}
): string {
  if (!text || text.length <= maxLength) {
    return highlightText(text, keyword, options);
  }

  const positions = findKeywordPositions(text, keyword, options.caseSensitive);
  
  if (positions.length === 0) {
    return highlightText(text.substring(0, maxLength) + '...', keyword, options);
  }

  // 找到第一个匹配位置
  const firstMatch = positions[0];
  if (!firstMatch) {
    return highlightText(text.substring(0, maxLength) + '...', keyword, options);
  }
  
  const contextLength = Math.floor(maxLength / 2);
  
  let start = Math.max(0, firstMatch.start - contextLength);
  let end = Math.min(text.length, firstMatch.end + contextLength);
  
  // 调整以确保包含关键词
  if (end - start < maxLength) {
    const remaining = maxLength - (end - start);
    if (start === 0) {
      end = Math.min(text.length, end + remaining);
    } else if (end === text.length) {
      start = Math.max(0, start - remaining);
    }
  }
  
  const prefix = start > 0 ? '...' : '';
  const suffix = end < text.length ? '...' : '';
  
  const truncated = text.substring(start, end);
  
  return prefix + highlightText(truncated, keyword, options) + suffix;
}
