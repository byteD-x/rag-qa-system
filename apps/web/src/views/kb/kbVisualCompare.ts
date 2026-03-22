export interface KBVisualCompareMatch {
  asset: any | null;
  region: any | null;
  score: number;
  strategy: 'region' | 'asset' | 'none';
}

export interface KBPixelDiffBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface KBPixelDiffResult {
  mask: Uint8ClampedArray;
  changed_pixels: number;
  total_pixels: number;
  changed_ratio: number;
  bounds: KBPixelDiffBounds | null;
}

function normalizeText(value: unknown): string {
  return String(value || '')
    .toLowerCase()
    .replace(/[\s\-_.,/\\()[\]{}:;'"`~!?@#$%^&*+=<>|]+/g, '')
    .trim();
}

function overlapCount(left: string[], right: string[]): number {
  const rightSet = new Set(right);
  return left.filter((item) => rightSet.has(item)).length;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function normalizedBbox(bbox: unknown): number[] {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return [];
  }
  const left = clamp01(Number(bbox[0]));
  const top = clamp01(Number(bbox[1]));
  const right = clamp01(Number(bbox[2]));
  const bottom = clamp01(Number(bbox[3]));
  if (right <= left || bottom <= top) {
    return [];
  }
  return [left, top, right, bottom];
}

function bboxIou(left: unknown, right: unknown): number {
  const a = normalizedBbox(left);
  const b = normalizedBbox(right);
  if (a.length !== 4 || b.length !== 4) {
    return 0;
  }
  const [aLeft, aTop, aRight, aBottom] = a as [number, number, number, number];
  const [bLeft, bTop, bRight, bBottom] = b as [number, number, number, number];
  const intersectLeft = Math.max(aLeft, bLeft);
  const intersectTop = Math.max(aTop, bTop);
  const intersectRight = Math.min(aRight, bRight);
  const intersectBottom = Math.min(aBottom, bBottom);
  if (intersectRight <= intersectLeft || intersectBottom <= intersectTop) {
    return 0;
  }
  const intersectArea = (intersectRight - intersectLeft) * (intersectBottom - intersectTop);
  const leftArea = (aRight - aLeft) * (aBottom - aTop);
  const rightArea = (bRight - bLeft) * (bBottom - bTop);
  const union = leftArea + rightArea - intersectArea;
  return union > 0 ? intersectArea / union : 0;
}

export function resolveVisualRegionBox(region: any | null | undefined): number[] {
  return normalizedBbox(region?.bbox);
}

export function findBestMatchingCompareVisual(options: {
  sourceAsset: any | null | undefined;
  sourceRegion: any | null | undefined;
  compareAssets: any[];
  compareRegionsByAsset: Record<string, any[]>;
}): KBVisualCompareMatch {
  const sourceAsset = options.sourceAsset || null;
  if (!sourceAsset) {
    return { asset: null, region: null, score: 0, strategy: 'none' };
  }
  const sourceRegion = options.sourceRegion || null;
  const sourcePage = Number(sourceRegion?.page_number || sourceAsset?.page_number || 0);
  const sourceLabel = normalizeText(sourceRegion?.region_label);
  const sourceHints = (Array.isArray(sourceRegion?.layout_hints) ? sourceRegion.layout_hints : []).map((item: unknown) => normalizeText(item)).filter(Boolean);
  const sourceText = normalizeText(sourceRegion?.ocr_text || sourceRegion?.summary);
  let best: KBVisualCompareMatch = { asset: null, region: null, score: -1, strategy: 'none' };

  for (const asset of options.compareAssets || []) {
    const assetId = String(asset?.asset_id || '');
    const assetPage = Number(asset?.page_number || 0);
    const assetRegions = options.compareRegionsByAsset[assetId] || [];
    if (!assetRegions.length) {
      let assetScore = 0;
      if (sourcePage && assetPage === sourcePage) {
        assetScore += 3;
      }
      if (assetScore > best.score) {
        best = { asset, region: null, score: assetScore, strategy: 'asset' };
      }
      continue;
    }

    for (const region of assetRegions) {
      let score = 0;
      const regionPage = Number(region?.page_number || assetPage || 0);
      const regionLabel = normalizeText(region?.region_label);
      const regionHints = (Array.isArray(region?.layout_hints) ? region.layout_hints : []).map((item: unknown) => normalizeText(item)).filter(Boolean);
      const regionText = normalizeText(region?.ocr_text || region?.summary);

      if (sourcePage && regionPage === sourcePage) {
        score += 4;
      } else if (sourcePage && regionPage && Math.abs(regionPage - sourcePage) === 1) {
        score += 1.5;
      }
      if (sourceLabel && regionLabel) {
        if (sourceLabel === regionLabel) {
          score += 6;
        } else if (sourceLabel.includes(regionLabel) || regionLabel.includes(sourceLabel)) {
          score += 3;
        }
      }
      score += overlapCount(sourceHints, regionHints) * 1.2;
      if (sourceText && regionText && (sourceText.includes(regionText) || regionText.includes(sourceText))) {
        score += 2;
      }
      score += bboxIou(sourceRegion?.bbox, region?.bbox) * 2;

      if (score > best.score) {
        best = { asset, region, score, strategy: 'region' };
      }
    }
  }

  if (best.score <= 0) {
    return { asset: null, region: null, score: 0, strategy: 'none' };
  }
  return best;
}

export function computePixelDiffMask(
  leftPixels: Uint8ClampedArray,
  rightPixels: Uint8ClampedArray,
  width: number,
  height: number,
  threshold = 28
): KBPixelDiffResult {
  const safeWidth = Math.max(1, Math.floor(width));
  const safeHeight = Math.max(1, Math.floor(height));
  const totalPixels = safeWidth * safeHeight;
  const mask = new Uint8ClampedArray(totalPixels * 4);
  let changedPixels = 0;
  let minX = safeWidth;
  let minY = safeHeight;
  let maxX = -1;
  let maxY = -1;

  for (let index = 0; index < totalPixels; index += 1) {
    const offset = index * 4;
    const redDelta = Math.abs((leftPixels[offset] || 0) - (rightPixels[offset] || 0));
    const greenDelta = Math.abs((leftPixels[offset + 1] || 0) - (rightPixels[offset + 1] || 0));
    const blueDelta = Math.abs((leftPixels[offset + 2] || 0) - (rightPixels[offset + 2] || 0));
    const alphaDelta = Math.abs((leftPixels[offset + 3] || 0) - (rightPixels[offset + 3] || 0));
    const averageDelta = (redDelta + greenDelta + blueDelta) / 3;
    const changed = averageDelta > threshold || alphaDelta > threshold;

    if (changed) {
      const x = index % safeWidth;
      const y = Math.floor(index / safeWidth);
      changedPixels += 1;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      mask[offset] = 217;
      mask[offset + 1] = 45;
      mask[offset + 2] = 32;
      mask[offset + 3] = Math.max(96, Math.min(220, Math.round(averageDelta * 3 + alphaDelta)));
    } else {
      const grayscale = Math.round(((leftPixels[offset] || 0) * 0.299 + (leftPixels[offset + 1] || 0) * 0.587 + (leftPixels[offset + 2] || 0) * 0.114) * 0.18);
      mask[offset] = grayscale;
      mask[offset + 1] = grayscale;
      mask[offset + 2] = grayscale;
      mask[offset + 3] = 90;
    }
  }

  return {
    mask,
    changed_pixels: changedPixels,
    total_pixels: totalPixels,
    changed_ratio: totalPixels ? changedPixels / totalPixels : 0,
    bounds: maxX >= 0 && maxY >= 0
      ? { left: minX, top: minY, right: maxX + 1, bottom: maxY + 1 }
      : null
  };
}
