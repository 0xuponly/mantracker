const API = '/api';

const PROFILE_ID_KEY = 'profileId';

export function getProfileId(): string | null {
  return localStorage.getItem(PROFILE_ID_KEY);
}

export function setProfileId(id: number | null): void {
  if (id == null) localStorage.removeItem(PROFILE_ID_KEY);
  else localStorage.setItem(PROFILE_ID_KEY, String(id));
}

/** Calls that require a profile (accounts, plaid, portfolio) send X-Profile-Id. */
export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const profileId = getProfileId();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (profileId) headers['X-Profile-Id'] = profileId;
  let res: Response
  try {
    res = await fetch(API + path, { ...options, headers })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
      throw new Error('Cannot reach backend. Is the server running? (npm start or backend on port 8000)')
    }
    throw e
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const msg = err.detail || String(err)
    throw new Error(res.status === 400 && msg.includes('X-Profile-Id') ? 'No profile selected. Choose or create a profile first.' : msg)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

/** For routes that don't need a profile (list profiles, create profile, import, unlock). */
export async function apiNoProfile<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  const res = await fetch(API + path, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || String(err));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const unlockApi = {
  status: () => apiNoProfile<{ unlocked: boolean }>('/unlock/status'),
  unlock: (passphrase: string) =>
    apiNoProfile<{ ok: boolean }>('/unlock', {
      method: 'POST',
      body: JSON.stringify({ passphrase }),
    }),
};

export const profiles = {
  list: () => apiNoProfile<ProfileSummary[]>('/profiles'),
  create: (name: string) =>
    apiNoProfile<ProfileSummary>('/profiles', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  update: (id: number, name: string) =>
    apiNoProfile<ProfileSummary>(`/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  delete: (id: number) =>
    apiNoProfile<void>(`/profiles/${id}`, { method: 'DELETE' }),
  exportProfile: async (id: number, suggestedName: string) => {
    const res = await fetch(`${API}/profiles/${id}/export`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || String(err))
    }
    const blob = await res.blob()
    const disp = res.headers.get('Content-Disposition')
    const match = disp?.match(/filename="?([^";]+)"?/)
    const filename = match ? match[1].trim() : `profile-${suggestedName.replace(/\s+/g, '-')}.json`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
  importFile: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const profileId = getProfileId();
    const headers: HeadersInit = {};
    if (profileId) headers['X-Profile-Id'] = profileId;
    const res = await fetch(API + '/profiles/import', {
      method: 'POST',
      body: form,
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || String(err));
    }
    return res.json() as Promise<ProfileSummary>;
  },
};

const ACCOUNTS_LIST_TIMEOUT_MS = 15_000;
const ACCOUNT_BALANCES_TIMEOUT_MS = 60_000;

export const accounts = {
  list: (options?: RequestInit) => api<AccountSummary[]>('/accounts', options),
  listWithTimeout: () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ACCOUNTS_LIST_TIMEOUT_MS);
    return accounts
      .list({ signal: controller.signal })
      .finally(() => clearTimeout(timeoutId))
      .catch((e) => {
        if (e?.name === 'AbortError') throw new Error('Request timed out. Try again.');
        throw e;
      });
  },
  balances: (id: number, options?: RequestInit) => api<AccountBalancesResponse>(`/accounts/${id}/balances`, options),
  balancesWithTimeout: (id: number) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ACCOUNT_BALANCES_TIMEOUT_MS);
    return accounts
      .balances(id, { signal: controller.signal })
      .finally(() => clearTimeout(timeoutId))
      .catch((e) => {
        if (e?.name === 'AbortError') throw new Error('Request timed out. Try again.');
        throw e;
      });
  },
  create: (body: AccountCreate) =>
    api<AccountSummary>('/accounts', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  update: (id: number, body: { name?: string }) =>
    api<AccountSummary>(`/accounts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  delete: (id: number) =>
    api<{ ok: boolean }>(`/accounts/${id}`, { method: 'DELETE' }),
};

export const plaid = {
  linkToken: () => api<{ link_token: string }>('/plaid/link_token'),
  exchange: (public_token: string, account_name: string, account_type: string) =>
    api<{ id: number; name: string; type: string }>('/plaid/exchange', {
      method: 'POST',
      body: JSON.stringify({
        public_token,
        account_name,
        account_type,
      }),
    }),
};

const PORTFOLIO_TIMEOUT_MS = 90_000; // 90s so backend can finish under rate limits

export const portfolio = {
  get: () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), PORTFOLIO_TIMEOUT_MS);
    return api<PortfolioAccount[]>('/portfolio', { signal: controller.signal })
      .finally(() => clearTimeout(timeoutId))
      .catch((e) => {
        if (e?.name === 'AbortError') throw new Error('Portfolio request timed out. Try again.');
        throw e;
      });
  },
};

export interface ProfileSummary {
  id: number;
  name: string;
}

export interface AccountSummary {
  id: number;
  name: string;
  type: string;
  provider: string | null;
  is_active: boolean;
}

export interface AccountCreate {
  name: string;
  type: string;
  provider?: string | null;
  credentials: Record<string, string>;
}

export interface BalanceItem {
  asset: string;
  amount: number;
  currency: string | null;
  usd_value: number | null;
  /** Chain name when balance is from multi-chain EVM (e.g. "Ethereum", "Arbitrum") */
  chain?: string | null;
  /** Token name for display (e.g. "USD Coin" for USDC) */
  name?: string | null;
}

export interface PortfolioAccount {
  id: number;
  name: string;
  type: string;
  provider: string | null;
  balances: BalanceItem[];
  error: string | null;
}

export interface AccountBalancesResponse {
  id: number;
  balances: BalanceItem[];
  error: string | null;
}
