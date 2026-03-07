/** Persisted in localStorage (survives tab navigation and app restart). Key: mantracker_dashboard_prefs_<profileId> */
const KEY_PREFIX = 'mantracker_dashboard_prefs_'

export type DashboardPrefs = {
  hideLowBalance: boolean
  balancesVisible: boolean
  hiddenAccountIds: number[]
}

const DEFAULTS: DashboardPrefs = {
  hideLowBalance: true,
  balancesVisible: true,
  hiddenAccountIds: [],
}

export function getDashboardPrefs(profileId: number | string): DashboardPrefs {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + String(profileId))
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw) as Partial<DashboardPrefs>
    return {
      hideLowBalance: typeof parsed.hideLowBalance === 'boolean' ? parsed.hideLowBalance : DEFAULTS.hideLowBalance,
      balancesVisible: typeof parsed.balancesVisible === 'boolean' ? parsed.balancesVisible : DEFAULTS.balancesVisible,
      hiddenAccountIds: Array.isArray(parsed.hiddenAccountIds)
        ? parsed.hiddenAccountIds.filter((id): id is number => typeof id === 'number')
        : DEFAULTS.hiddenAccountIds,
    }
  } catch {
    return DEFAULTS
  }
}

export function setDashboardPrefs(profileId: number | string, prefs: DashboardPrefs): void {
  try {
    localStorage.setItem(KEY_PREFIX + String(profileId), JSON.stringify(prefs))
  } catch {
    // ignore quota / private mode
  }
}
