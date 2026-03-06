import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useProfile } from './ProfileContext'
import Layout from './Layout'
import ProfilePicker from './pages/ProfilePicker'
import Dashboard from './pages/Dashboard'
import Accounts from './pages/Accounts'
import AddAccount from './pages/AddAccount'
import Profiles from './pages/Profiles'
import UnlockScreen from './pages/UnlockScreen'
import { unlockApi } from './api'
import Settings from './pages/Settings'

export default function App() {
  const [unlockChecked, setUnlockChecked] = useState(false)
  const [unlocked, setUnlocked] = useState(false)
  const { currentProfile, loading } = useProfile()

  useEffect(() => {
    unlockApi
      .status()
      .then((r) => {
        setUnlocked(r.unlocked)
        setUnlockChecked(true)
      })
      .catch(() => setUnlockChecked(true))
  }, [])

  if (!unlockChecked) return <div className="loading">Loading…</div>
  if (!unlocked) return <UnlockScreen onUnlocked={() => setUnlocked(true)} />

  if (loading) return <div className="loading">Loading…</div>

  if (!currentProfile) {
    return (
      <Routes>
        <Route path="/" element={<ProfilePicker />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="accounts" element={<Accounts />} />
        <Route path="accounts/add" element={<AddAccount />} />
        <Route path="profiles" element={<Profiles />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
