import { describe, expect, it } from 'vitest';
import { resolveRequestErrorMessage } from './request';

describe('request error messages', () => {
  it('keeps invalid login credentials actionable instead of saying the session expired', () => {
    expect(resolveRequestErrorMessage(401, '邮箱或密码错误', { detail: '邮箱或密码错误' }, { isLoginRequest: true }))
      .toBe('邮箱或密码错误');
  });
});
