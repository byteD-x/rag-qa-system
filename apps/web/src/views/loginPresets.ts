export type DemoAccount = {
  email: string;
  password: string;
};

export type DemoAccountEnv = {
  VITE_DEMO_ADMIN_EMAIL?: string;
  VITE_DEMO_ADMIN_PASSWORD?: string;
  VITE_DEMO_MEMBER_EMAIL?: string;
  VITE_DEMO_MEMBER_PASSWORD?: string;
};

const DEFAULT_DEMO_ACCOUNTS = {
  admin: { email: 'admin@local', password: 'ChangeMe123!' },
  member: { email: 'member@local', password: 'ChangeMe123!' }
} satisfies Record<'admin' | 'member', DemoAccount>;

function valueOrDefault(value: string | undefined, fallback: string): string {
  return value?.trim() || fallback;
}

export function resolveDemoAccounts(env: DemoAccountEnv): Record<'admin' | 'member', DemoAccount> {
  return {
    admin: {
      email: valueOrDefault(env.VITE_DEMO_ADMIN_EMAIL, DEFAULT_DEMO_ACCOUNTS.admin.email),
      password: valueOrDefault(env.VITE_DEMO_ADMIN_PASSWORD, DEFAULT_DEMO_ACCOUNTS.admin.password)
    },
    member: {
      email: valueOrDefault(env.VITE_DEMO_MEMBER_EMAIL, DEFAULT_DEMO_ACCOUNTS.member.email),
      password: valueOrDefault(env.VITE_DEMO_MEMBER_PASSWORD, DEFAULT_DEMO_ACCOUNTS.member.password)
    }
  };
}

export const demoAccounts = resolveDemoAccounts(import.meta.env);
