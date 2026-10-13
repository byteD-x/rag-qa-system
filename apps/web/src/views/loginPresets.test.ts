import { describe, expect, it } from 'vitest';

import { resolveDemoAccounts } from './loginPresets';

describe('login demo account presets', () => {
  it('uses deployment-injected credentials for the quick-fill accounts', () => {
    const accounts = resolveDemoAccounts({
      VITE_DEMO_ADMIN_EMAIL: 'admin@company.test',
      VITE_DEMO_ADMIN_PASSWORD: 'admin-secret',
      VITE_DEMO_MEMBER_EMAIL: 'member@company.test',
      VITE_DEMO_MEMBER_PASSWORD: 'member-secret'
    });

    expect(accounts.admin).toEqual({ email: 'admin@company.test', password: 'admin-secret' });
    expect(accounts.member).toEqual({ email: 'member@company.test', password: 'member-secret' });
  });
});
