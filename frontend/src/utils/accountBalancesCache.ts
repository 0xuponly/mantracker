import type { BalanceItem } from '../api'

const CACHE_PREFIX = 'mantracker_balances_'

export interface CachedAccountBalances {
  balances: BalanceItem[]
  fetchedAt: number
}

export interface CachedBalancesBlob {
  byId: Record<string, CachedAccountBalances>
}

function key(profileId: string): string {
  return `${CACHE_PREFIX}${profileId}`
}

export function readBalancesCache(profileId: string | null): CachedBalancesBlob | null {
  if (!profileId) return null
  try {
    const raw = localStorage.getItem(key(profileId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedBalancesBlob
    if (!parsed || typeof parsed !== 'object' || !parsed.byId || typeof parsed.byId !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

export function writeBalancesCache(profileId: string | null, accountId: number, balances: BalanceItem[]): void {
  if (!profileId) return
  try {
    const existing = readBalancesCache(profileId) ?? { byId: {} }
    existing.byId[String(accountId)] = { balances, fetchedAt: Date.now() }
    localStorage.setItem(key(profileId), JSON.stringify(existing))
  } catch {
    // ignore quota / serialization errors
  }
}

