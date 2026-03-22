import { describe, expect, it } from 'vitest';

import { computePixelDiffMask, findBestMatchingCompareVisual, resolveVisualRegionBox } from './kbVisualCompare';

describe('kbVisualCompare', () => {
  it('prefers exact page and region label match across versions', () => {
    const match = findBestMatchingCompareVisual({
      sourceAsset: { asset_id: 'asset-current', page_number: 3 },
      sourceRegion: {
        region_id: 'region-current',
        page_number: 3,
        region_label: 'red box config',
        layout_hints: ['terminal', 'annotation'],
        bbox: [0.1, 0.2, 0.8, 0.6]
      },
      compareAssets: [
        { asset_id: 'asset-old-1', page_number: 2 },
        { asset_id: 'asset-old-2', page_number: 3 }
      ],
      compareRegionsByAsset: {
        'asset-old-1': [
          { region_id: 'region-a', page_number: 2, region_label: 'footer note', layout_hints: ['table'], bbox: [0.1, 0.2, 0.8, 0.6] }
        ],
        'asset-old-2': [
          { region_id: 'region-b', page_number: 3, region_label: 'red box config', layout_hints: ['terminal', 'annotation'], bbox: [0.1, 0.2, 0.8, 0.6] }
        ]
      }
    });

    expect(match.strategy).toBe('region');
    expect(match.asset?.asset_id).toBe('asset-old-2');
    expect(match.region?.region_id).toBe('region-b');
    expect(match.score).toBeGreaterThan(10);
  });

  it('falls back to page-level asset match when compare version has no structured region', () => {
    const match = findBestMatchingCompareVisual({
      sourceAsset: { asset_id: 'asset-current', page_number: 4 },
      sourceRegion: null,
      compareAssets: [
        { asset_id: 'asset-old-1', page_number: 2 },
        { asset_id: 'asset-old-2', page_number: 4 }
      ],
      compareRegionsByAsset: {}
    });

    expect(match.strategy).toBe('asset');
    expect(match.asset?.asset_id).toBe('asset-old-2');
    expect(match.region).toBeNull();
  });

  it('computes changed bounds for pixel differences', () => {
    const leftPixels = new Uint8ClampedArray(4 * 4 * 4);
    const rightPixels = new Uint8ClampedArray(4 * 4 * 4);
    for (let index = 0; index < leftPixels.length; index += 4) {
      leftPixels[index] = 20;
      leftPixels[index + 1] = 20;
      leftPixels[index + 2] = 20;
      leftPixels[index + 3] = 255;
      rightPixels[index] = 20;
      rightPixels[index + 1] = 20;
      rightPixels[index + 2] = 20;
      rightPixels[index + 3] = 255;
    }

    const changedOffsets = [5, 6, 9, 10];
    for (const pixelIndex of changedOffsets) {
      const offset = pixelIndex * 4;
      rightPixels[offset] = 240;
      rightPixels[offset + 1] = 20;
      rightPixels[offset + 2] = 20;
    }

    const result = computePixelDiffMask(leftPixels, rightPixels, 4, 4, 20);
    expect(result.changed_pixels).toBe(4);
    expect(result.changed_ratio).toBe(0.25);
    expect(result.bounds).toEqual({ left: 1, top: 1, right: 3, bottom: 3 });
    expect(result.mask[5 * 4]).toBe(217);
  });

  it('normalizes region box to safe coordinates', () => {
    expect(resolveVisualRegionBox({ bbox: [-1, 0.1, 1.4, 0.8] })).toEqual([0, 0.1, 1, 0.8]);
    expect(resolveVisualRegionBox({ bbox: [0.5, 0.2, 0.3, 0.7] })).toEqual([]);
  });
});
