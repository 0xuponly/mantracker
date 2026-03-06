import { useState, useRef } from 'react'
import { useProfile } from '../ProfileContext'
import { profiles as profilesApi } from '../api'
import './Profiles.css'

export default function Profiles() {
  const { profiles, currentProfile, setCurrentProfileById, createProfile, deleteProfile, refreshProfiles } = useProfile()

  function switchToPicker() {
    setCurrentProfileById(null)
  }
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setError('')
    setCreating(true)
    try {
      const p = await createProfile(name)
      setCurrentProfileById(p.id, p)
      setNewName('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create profile')
    } finally {
      setCreating(false)
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setImporting(true)
    try {
      const p = await profilesApi.importFile(file)
      await refreshProfiles()
      setCurrentProfileById(p.id, p)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  function handleExport(id: number, name: string) {
    profilesApi.exportProfile(id, name).catch((err) => setError(err instanceof Error ? err.message : 'Export failed'))
  }

  async function handleDelete(id: number) {
    if (!confirm('Delete this profile and all its accounts? This cannot be undone.')) return
    try {
      await deleteProfile(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  return (
    <div className="profiles-page">
      <div className="page-header">
        <h1>Manage profiles</h1>
        <button type="button" className="btn-link" onClick={switchToPicker}>
          Use another profile
        </button>
      </div>
      <p className="muted">Profiles are stored only on this device. Export a profile to back it up or move it to another machine.</p>

      {error && <div className="error-banner">{error}</div>}

      <section className="section">
        <h2>Create profile</h2>
        <form onSubmit={handleCreate} className="inline-form">
          <input
            type="text"
            placeholder="Profile name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={creating}
          />
          <button type="submit" disabled={creating || !newName.trim()} className="btn-primary">
            {creating ? 'Creating…' : 'Create'}
          </button>
        </form>
      </section>

      <section className="section">
        <h2>Import profile</h2>
        <p className="muted small">Upload a previously exported .json file. Use the same app setup (ENCRYPTION_KEY) for credentials to work.</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleImport}
          style={{ display: 'none' }}
        />
        <button
          type="button"
          className="btn-secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
        >
          {importing ? 'Importing…' : 'Choose file'}
        </button>
      </section>

      <section className="section">
        <h2>Profiles</h2>
        {profiles.length === 0 ? (
          <p className="muted">No profiles yet. Create one above.</p>
        ) : (
          <ul className="profiles-list">
            {profiles.map((p) => (
              <li key={p.id} className="profile-row">
                <div>
                  <strong>{p.name}</strong>
                  {currentProfile?.id === p.id && <span className="badge">Current</span>}
                </div>
                <div className="actions">
                  {currentProfile?.id !== p.id && (
                    <button type="button" className="btn-link" onClick={() => setCurrentProfileById(p.id)}>
                      Switch to
                    </button>
                  )}
                  <button type="button" className="btn-link" onClick={() => handleExport(p.id, p.name)}>
                    Export
                  </button>
                  <button type="button" className="btn-danger" onClick={() => handleDelete(p.id)}>
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
