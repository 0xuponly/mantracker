import { useState } from 'react'
import { useProfile } from '../ProfileContext'
import './ProfilePicker.css'

export default function ProfilePicker() {
  const { profiles, setCurrentProfileById, createProfile } = useProfile()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setError('')
    setCreating(true)
    try {
      const p = await createProfile(name)
      setCurrentProfileById(p.id, p)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create profile')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="profile-picker">
      <div className="profile-picker-card">
        <h1>Portfolio Tracker</h1>
        <p className="subtitle">All data stays on your device. No sign-in, no cloud.</p>

        {profiles.length > 0 ? (
          <>
            <p className="label">Choose a profile</p>
            <ul className="profile-list">
              {profiles.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className="profile-btn"
                    onClick={() => setCurrentProfileById(p.id)}
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
            <p className="label">Or create a new profile</p>
          </>
        ) : (
          <p className="label">Create your first profile to get started</p>
        )}

        <form onSubmit={handleCreate} className="create-form">
          {error && <div className="error">{error}</div>}
          <input
            type="text"
            placeholder="Profile name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={creating}
          />
          <button type="submit" disabled={creating || !newName.trim()}>
            {creating ? 'Creating…' : 'Create profile'}
          </button>
        </form>
      </div>
    </div>
  )
}
