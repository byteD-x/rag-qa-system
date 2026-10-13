import { describe, expect, it } from 'vitest';
import { elementComponents } from './element-plus-components';

describe('Element Plus global registration', () => {
  it('registers every Element Plus component used by application templates', () => {
    const names = new Set(elementComponents.map((component) => component.name));

    expect(names).toEqual(expect.any(Set));
    for (const name of [
      'ElCheckboxGroup',
      'ElDatePicker',
      'ElDivider',
      'ElInputNumber',
      'ElPagination',
      'ElRadio',
      'ElSkeleton',
      'ElSlider',
      'ElTabPane',
      'ElTabs',
      'ElTooltip'
    ]) {
      expect(names.has(name)).toBe(true);
    }
  });
});
