import type { PortfolioAccount } from '../api'

const CACHE_PREFIX = 'mantracker_portfolio_'

export function getPortfolioCacheKey(profileId: string): string {
  return `${CACHE_PREFIX}${profileId}`
}

export interface CachedPortfolio {
  accounts: PortfolioAccount[]
  fetchedAt: number
}

export function readPortfolioCache(profileId: string | null): CachedPortfolio | null {
  if (!profileId) return null
  try {
    const raw = localStorage.getItem(getPortfolioCacheKey(profileId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedPortfolio
    if (!Array.isArray(parsed?.accounts)) return null
    return { accounts: parsed.accounts, fetchedAt: parsed.fetchedAt ?? 0 }
  } catch {
    return null
  }
}

export function writePortfolioCache(profileId: string | null, accounts: PortfolioAccount[]): void {
  if (!profileId) return
  try {
    const data: CachedPortfolio = { accounts, fetchedAt: Date.now() }
    localStorage.setItem(getPortfolioCacheKey(profileId), JSON.stringify(data))
  } catch {
    // ignore quota or parse errors
  }
}
