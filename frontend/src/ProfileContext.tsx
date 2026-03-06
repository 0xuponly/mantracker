import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { profiles as profilesApi, setProfileId, getProfileId, type ProfileSummary } from './api'

const ProfileContext = createContext<{
  profiles: ProfileSummary[];
  currentProfile: ProfileSummary | null;
  loading: boolean;
  setCurrentProfileById: (id: number | null, profile?: ProfileSummary) => void;
  createProfile: (name: string) => Promise<ProfileSummary>;
  deleteProfile: (id: number) => Promise<void>;
  refreshProfiles: () => Promise<void>;
}>({
  profiles: [],
  currentProfile: null,
  loading: true,
  setCurrentProfileById: () => {},
  createProfile: async () => ({ id: 0, name: '' }),
  deleteProfile: async () => {},
  refreshProfiles: async () => {},
})

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([])
  const [currentProfile, setCurrentProfile] = useState<ProfileSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshProfiles = useCallback(async () => {
    try {
      const list = await profilesApi.list()
      setProfiles(list)
      const id = getProfileId()
      if (id) {
        const num = parseInt(id, 10)
        const p = list.find((x) => x.id === num)
        setCurrentProfile(p || null)
        if (!p) setProfileId(null)
      } else {
        setCurrentProfile(null)
      }
    } catch {
      setProfiles([])
      setCurrentProfile(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshProfiles()
  }, [refreshProfiles])

  const setCurrentProfileById = useCallback((id: number | null, profile?: ProfileSummary) => {
    setProfileId(id)
    if (id == null) {
      setCurrentProfile(null)
      return
    }
    setCurrentProfile(profile ?? profiles.find((x) => x.id === id) ?? null)
  }, [profiles])

  const createProfile = useCallback(async (name: string) => {
    const created = await profilesApi.create(name)
    await refreshProfiles()
    return created
  }, [refreshProfiles])

  const deleteProfile = useCallback(async (id: number) => {
    await profilesApi.delete(id)
    if (getProfileId() === String(id)) {
      setProfileId(null)
      setCurrentProfile(null)
    }
    await refreshProfiles()
  }, [refreshProfiles])

  return (
    <ProfileContext.Provider
      value={{
        profiles,
        currentProfile,
        loading,
        setCurrentProfileById,
        createProfile,
        deleteProfile,
        refreshProfiles,
      }}
    >
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfile() {
  return useContext(ProfileContext)
}
