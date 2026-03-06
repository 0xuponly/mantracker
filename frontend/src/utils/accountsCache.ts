import type { AccountSummary } from '../api'

const CACHE_PREFIX = 'mantracker_accounts_'

export interface CachedAccountsBlob {
  accounts: AccountSummary[]
  fetchedAt: number
}

function key(profileId: string): string {
  return `${CACHE_PREFIX}${profileId}`
}

export function readAccountsCache(profileId: string | null): CachedAccountsBlob | null {
  if (!profileId) return null
  try {
    const raw = localStorage.getItem(key(profileId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedAccountsBlob
    if (!Array.isArray(parsed?.accounts)) return null
    return {
      accounts: parsed.accounts,
      fetchedAt: parsed.fetchedAt ?? 0,
    }
  } catch {
    return null
  }
}

export function writeAccountsCache(profileId: string | null, accounts: AccountSummary[]): void {
  if (!profileId) return
  try {
    const blob: CachedAccountsBlob = {
      accounts,
      fetchedAt: Date.now(),
    }
    localStorage.setItem(key(profileId), JSON.stringify(blob))
  } catch {
    // ignore quota / serialization errors
  }
}

