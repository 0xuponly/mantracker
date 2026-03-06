import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { accounts } from '../api'
import type { AccountSummary, BalanceItem, AccountBalancesResponse } from '../api'
import { useProfile } from '../ProfileContext'
import { readBalancesCache, writeBalancesCache } from '../utils/accountBalancesCache'
import { readPortfolioCache } from '../utils/portfolioCache'
import { readAccountsCache, writeAccountsCache } from '../utils/accountsCache'
import './Dashboard.css'

const LOW_BALANCE_THRESHOLD = 1
const RETRY_INITIAL_MS = 3000
const RETRY_MAX_MS = 30_000
const BALANCE_FETCH_CONCURRENCY = 6
const AUTO_REFRESH_COOLDOWN_MS = 15 * 60 * 1000

type BalanceState = {
  balances: BalanceItem[]
  status: 'idle' | 'loading' | 'ok' | 'error'
  error: string | null
  fetchedAt: number | null
}

function balanceKey(b: BalanceItem): string {
  // Key should be stable across refreshes.
  // Asset symbol + optional chain is enough for our adapters today; include currency for safety.
  return `${b.asset}::${b.chain ?? ''}::${b.currency ?? ''}`
}

function mergeBalances(prev: BalanceItem[], next: BalanceItem[]): BalanceItem[] {
  const prevByKey = new Map<string, BalanceItem>()
  for (const b of prev) prevByKey.set(balanceKey(b), b)

  const used = new Set<string>()
  const out: BalanceItem[] = []

  for (const b of next) {
    const k = balanceKey(b)
    used.add(k)
    const p = prevByKey.get(k)
    out.push({
      ...p,
      ...b,
      // Preserve last known USD value/name if the refresh couldn't compute them.
      usd_value: b.usd_value ?? p?.usd_value ?? null,
      name: b.name ?? p?.name ?? null,
    })
  }

  // Append anything that was present previously but missing from the refresh result.
  // This is critical for partial Solana refreshes where SPL tokens may be unavailable.
  for (const b of prev) {
    const k = balanceKey(b)
    if (!used.has(k)) out.push(b)
  }
  return out
}

function shouldRetryError(message: string | null): boolean {
  if (!message) return false
  // Don't retry permanent/validation failures
  if (/invalid credentials|missing wallet address|no credentials stored|account not found/i.test(message)) return false
  // Retry timeouts, 429s, network-ish failures, 5xx, and generic failures
  return true
}

export default function Dashboard() {
  const [accountList, setAccountList] = useState<AccountSummary[] | null>(null)
  const [byAccountId, setByAccountId] = useState<Record<number, BalanceState>>({})
  const [accountsError, setAccountsError] = useState('')
  const [hideLowBalance, setHideLowBalance] = useState(true)
  const byAccountRef = useRef<Record<number, BalanceState>>({})
  const retryCountRef = useRef<Map<number, number>>(new Map())
  const retryTimersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const pendingRef = useRef<number[]>([])
  const pendingSetRef = useRef<Set<number>>(new Set())
  const inFlightRef = useRef<Set<number>>(new Set())
  const activeRef = useRef(0)
  const fetchProfileIdRef = useRef<number | string | null>(null)
  const { currentProfile } = useProfile()
  const profileId = currentProfile?.id ?? null

  // Load account list when profile is set; refetch when profile changes.
  // When list arrives, seed byAccountId from cache in the same callback so cached balances show on first paint.
  useEffect(() => {
    if (profileId == null) {
      setAccountList([])
      setAccountsError('')
      fetchProfileIdRef.current = null
      return
    }
    // Try to show cached accounts immediately for this profile before hitting the network.
    const cachedAccounts = readAccountsCache(String(profileId))
    if (cachedAccounts && cachedAccounts.accounts.length > 0) {
      setAccountList(cachedAccounts.accounts)
    } else {
      setAccountList(null)
    }
    setAccountsError('')
    fetchProfileIdRef.current = profileId
    accounts
      .list()
      .then((list) => {
        if (fetchProfileIdRef.current !== profileId) return
        let cached = readBalancesCache(String(profileId))
        // Back-compat: older builds cached full portfolio responses (mantracker_portfolio_*).
        // If we don't have per-account cache yet, seed from portfolio cache and migrate it.
        const portfolioCached = !cached ? readPortfolioCache(String(profileId)) : null
        const seeded: Record<number, BalanceState> = {}
        for (const acc of list) {
          const cachedItem = cached?.byId?.[String(acc.id)]
          const fallbackBalances = portfolioCached?.accounts?.find((a) => a.id === acc.id)?.balances
          if (cachedItem?.balances) {
            seeded[acc.id] = { balances: cachedItem.balances, status: 'ok', error: null, fetchedAt: cachedItem.fetchedAt ?? null }
          } else if (fallbackBalances && fallbackBalances.length > 0) {
            seeded[acc.id] = { balances: fallbackBalances, status: 'ok', error: null, fetchedAt: portfolioCached?.fetchedAt ?? null }
            // Write into the current per-account cache so subsequent loads are instant.
            writeBalancesCache(String(profileId), acc.id, fallbackBalances)
          } else {
            seeded[acc.id] = { balances: [], status: 'idle', error: null, fetchedAt: null }
          }
        }
        setAccountList(list)
        setByAccountId(seeded)
        byAccountRef.current = seeded
        writeAccountsCache(String(profileId), list)
      })
      .catch((e) => {
        if (fetchProfileIdRef.current !== profileId) return
        setAccountsError(e.message)
      })
  }, [profileId])

  function clearRetries() {
    for (const t of retryTimersRef.current.values()) clearTimeout(t)
    retryTimersRef.current.clear()
    retryCountRef.current.clear()
  }

  function scheduleRetry(accountId: number, message: string | null) {
    if (!shouldRetryError(message)) return
    const n = retryCountRef.current.get(accountId) ?? 0
    const delay = Math.min(RETRY_INITIAL_MS * Math.pow(2, n), RETRY_MAX_MS)
    retryCountRef.current.set(accountId, n + 1)
    if (retryTimersRef.current.has(accountId)) return
    const t = setTimeout(() => {
      retryTimersRef.current.delete(accountId)
      enqueueFetch(accountId, false, false)
    }, delay)
    retryTimersRef.current.set(accountId, t)
  }

  function mergeState(accountId: number, next: Partial<BalanceState>) {
    setByAccountId((prev) => {
      // Important: on startup we seed `byAccountRef.current` from cache and then immediately
      // start fetches. React state may not have applied yet, so prefer the ref as a fallback
      // to avoid clobbering cached balances with an early "loading + empty balances" update.
      const cur =
        prev[accountId] ??
        byAccountRef.current[accountId] ??
        { balances: [], status: 'idle', error: null, fetchedAt: null }
      const merged = { ...cur, ...next }
      const out = { ...prev, [accountId]: merged }
      byAccountRef.current = out
      return out
    })
  }

  async function fetchOne(accountId: number) {
    activeRef.current += 1
    inFlightRef.current.add(accountId)
    const prev = byAccountRef.current[accountId]
    const hadBalances = (prev?.balances?.length ?? 0) > 0
    mergeState(accountId, { status: 'loading', error: null })
    try {
      const res: AccountBalancesResponse = await accounts.balancesWithTimeout(accountId)
      const nextBalances = res.balances ?? []
      const hasAnyBalances = nextBalances.length > 0
      // If backend returns partial balances with an error (e.g. SOL returned but SPL token fetch rate-limited),
      // treat it as success and show what we have.
      if (res.error && !hasAnyBalances) {
        if (hadBalances) {
          // Keep last known balances; don't get stuck retrying this one account.
          mergeState(accountId, { status: 'ok', error: res.error })
        } else {
          mergeState(accountId, { status: 'error', error: res.error })
          scheduleRetry(accountId, res.error)
        }
        return
      }

      const now = Date.now()
      // When we had previous balances, always merge the new snapshot into them so that
      // cached SPL tokens / values are preserved even if a refresh only returns SOL or
      // misses some tokens due to transient failures.
      const merged =
        hadBalances
          ? mergeBalances(prev?.balances ?? [], nextBalances)
          : nextBalances
      mergeState(accountId, { status: 'ok', error: res.error ?? null, balances: merged, fetchedAt: now })
      if (profileId != null) writeBalancesCache(String(profileId), accountId, merged)
      retryCountRef.current.delete(accountId)
      const t = retryTimersRef.current.get(accountId)
      if (t) {
        clearTimeout(t)
        retryTimersRef.current.delete(accountId)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (hadBalances) {
        mergeState(accountId, { status: 'ok', error: msg })
      } else {
        mergeState(accountId, { status: 'error', error: msg })
        scheduleRetry(accountId, msg)
      }
    } finally {
      inFlightRef.current.delete(accountId)
      activeRef.current -= 1
      drainQueue()
    }
  }

  function drainQueue() {
    while (activeRef.current < BALANCE_FETCH_CONCURRENCY && pendingRef.current.length > 0) {
      const id = pendingRef.current.shift()!
      pendingSetRef.current.delete(id)
      if (inFlightRef.current.has(id)) continue
      fetchOne(id)
    }
  }

  /** Add to front of queue so never-fetched accounts get tried before retries. */
  function enqueueFetch(accountId: number, force = false, front = false) {
    if (pendingSetRef.current.has(accountId) || inFlightRef.current.has(accountId)) return
    if (!force) {
      const st = byAccountRef.current[accountId]
      if (st?.status === 'ok' && st.fetchedAt != null) {
        const age = Date.now() - st.fetchedAt
        if (age >= 0 && age < AUTO_REFRESH_COOLDOWN_MS) return
      }
    }
    pendingSetRef.current.add(accountId)
    if (front) pendingRef.current.unshift(accountId)
    else pendingRef.current.push(accountId)
    drainQueue()
  }

  function refreshAllBalances() {
    if (!accountList || accountList.length === 0) return
    // Cancel any scheduled retries so manual refresh runs immediately.
    for (const t of retryTimersRef.current.values()) clearTimeout(t)
    retryTimersRef.current.clear()
    retryCountRef.current.clear()
    for (const acc of accountList) enqueueFetch(acc.id, true)
  }

  function refreshOneBalance(accountId: number) {
    const t = retryTimersRef.current.get(accountId)
    if (t) {
      clearTimeout(t)
      retryTimersRef.current.delete(accountId)
    }
    retryCountRef.current.delete(accountId)
    enqueueFetch(accountId, true, true)
  }

  // Load cache and start per-account balance fetches when we have accounts for this profile
  useEffect(() => {
    if (profileId == null || !accountList || accountList.length === 0) {
      if (profileId == null) {
        clearRetries()
        setByAccountId({})
        byAccountRef.current = {}
      }
      return
    }

    // If we already seeded state for this account list (from the accounts.list() callback),
    // don't clobber it again here.
    const alreadySeeded = accountList.every((acc) => byAccountRef.current[acc.id] != null)
    if (!alreadySeeded) {
      // Seed from cache (last known good balances)
      const cached = readBalancesCache(String(profileId))
      const seeded: Record<number, BalanceState> = {}
      for (const acc of accountList) {
        const cachedItem = cached?.byId?.[String(acc.id)]
        if (cachedItem?.balances) {
          seeded[acc.id] = { balances: cachedItem.balances, status: 'ok', error: null, fetchedAt: cachedItem.fetchedAt ?? null }
        } else {
          seeded[acc.id] = { balances: [], status: 'idle', error: null, fetchedAt: null }
        }
      }
      setByAccountId(seeded)
      byAccountRef.current = seeded
    }

    // Start fetches on the next tick so cached balances render first.
    const startTimer = setTimeout(() => {
      for (const acc of accountList) enqueueFetch(acc.id, false, true)
    }, 0)

    return () => {
      clearTimeout(startTimer)
      clearRetries()
      pendingRef.current = []
      pendingSetRef.current.clear()
      inFlightRef.current.clear()
      activeRef.current = 0
    }
  }, [profileId, accountList])

  if (profileId == null) {
    return (
      <div className="dashboard">
        <div className="page-header"><h1>Portfolio</h1></div>
        <div className="page-error">No profile selected. Choose or create a profile from the header to view balances.</div>
      </div>
    )
  }
  if (accountsError) return <div className="page-error">{accountsError}</div>
  if (accountList === null) return <div className="page-loading">Loading accounts…</div>

  const hasAccounts = accountList.length > 0
  let totalUsd = 0

  function accountTotalUsd(id: number): number {
    const st = byAccountId[id]
    if (!st || !st.balances) return 0
    return st.balances.reduce((s, b) => s + (b.usd_value ?? 0), 0)
  }

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1>Portfolio</h1>
        <div className="page-header-actions">
          <label className="toggle-low-balance">
            <input
              type="checkbox"
              checked={hideLowBalance}
              onChange={(e) => setHideLowBalance(e.target.checked)}
            />
            <span>Hide &lt;$1</span>
          </label>
          <button type="button" className="btn-secondary" onClick={refreshAllBalances}>
            Refresh balances
          </button>
          <Link to="/accounts/add" className="btn-primary">Add account</Link>
        </div>
      </div>

      {!hasAccounts ? (
        <div className="empty-state">
          <p>No accounts yet. Add bank, brokerage, exchange, or wallet to see balances.</p>
          <Link to="/accounts/add" className="btn-primary">Add your first account</Link>
        </div>
      ) : (
        <div className="portfolio-grid">
          {[...accountList]
            .sort((a, b) => {
              const diff = accountTotalUsd(b.id) - accountTotalUsd(a.id)
              if (diff !== 0) return diff
              return a.name.localeCompare(b.name)
            })
            .map((acc) => {
            const state = byAccountId[acc.id] ?? { balances: [], status: 'idle', error: null, fetchedAt: null }
            const hasCachedBalances = state.balances.length > 0
            const isLoading = state.status === 'loading' || state.status === 'idle'
            const isError = state.status === 'error'
            const isRetrying = isError && retryTimersRef.current.has(acc.id)
            const showStaleLabel = hasCachedBalances && (isLoading || isRetrying)

            const visibleBalances =
              hideLowBalance
                ? state.balances.filter((b) => b.usd_value != null && b.usd_value >= LOW_BALANCE_THRESHOLD)
                : state.balances
            const accountUsd = visibleBalances.reduce((s, b) => s + (b.usd_value ?? 0), 0)
            totalUsd += accountUsd
            return (
              <div key={acc.id} className="account-card">
                <div className="account-card-header">
                  <span className="account-type">{acc.type}</span>
                  {acc.provider && <span className="account-provider">{acc.provider}</span>}
                  <span className="account-card-header-spacer" />
                  {showStaleLabel && (
                    <span className="account-updating">{isRetrying ? 'Retrying…' : 'Updating…'}</span>
                  )}
                  <button
                    type="button"
                    className="account-refresh-btn"
                    onClick={() => refreshOneBalance(acc.id)}
                    disabled={state.status === 'loading'}
                    aria-label="Refresh this account"
                    title="Refresh this account"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                      <path
                        d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.75 6h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L14 10h7V3l-3.35 3.35z"
                        fill="currentColor"
                      />
                    </svg>
                  </button>
                </div>
                <h3>{acc.name}</h3>

                {state.balances.length === 0 && isLoading ? (
                  <p className="account-loading">Loading balances…</p>
                ) : state.balances.length === 0 && isError ? (
                  <p className="account-error">{state.error}</p>
                ) : (
                  visibleBalances.length === 0 && hideLowBalance ? (
                    <p className="account-loading">
                      {state.balances.every((b) => b.usd_value == null)
                        ? 'Balances loaded, but USD values are unavailable. Turn off Hide <$1 to view amounts.'
                        : 'All balances are <$1 (hidden). Turn off Hide <$1 to show.'}
                    </p>
                  ) : (
                    <ul className="balance-list">
                      {visibleBalances.map((b, i) => {
                        const unitPrice = b.amount > 0 && b.usd_value != null ? b.usd_value / b.amount : null
                        return (
                          <li key={i}>
                            <span className="asset">
                              {b.name || b.asset}
                              {b.chain ? ` (${b.chain})` : ''}
                            </span>
                            <span className="ticker">{b.currency || b.asset}</span>
                            <span className="amount">
                              {b.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                            </span>
                            <span className="unit-price">
                              {unitPrice != null ? `$${unitPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}` : '—'}
                            </span>
                            {b.usd_value != null ? (
                              <span className="usd">≈ ${b.usd_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                            ) : (
                              <span className="usd muted">—</span>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )
                )}
                {visibleBalances.length > 0 && (
                  <p className="card-usd-total">
                    ≈ ${accountUsd.toLocaleString(undefined, { maximumFractionDigits: 2 })} USD
                  </p>
                )}
                {state.balances.length > 0 && state.error && (
                  <p className="account-loading" style={{ marginTop: '0.5rem' }}>
                    Update failed: {state.error}{isRetrying ? ' (retrying automatically)' : ''}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {hasAccounts && totalUsd > 0 && (
        <div className="total-bar">
          <span>Total (USD equivalent)</span>
          <strong>${totalUsd.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
        </div>
      )}
    </div>
  )
}
