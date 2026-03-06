import { useEffect, useState } from 'react'
import { settingsApi } from '../api'
import './Settings.css'

export default function Settings() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatus] = useState<{ alchemy_api_key: boolean } | null>(null)
  const [alchemyValue, setAlchemyValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')

  useEffect(() => {
    settingsApi
      .apiKeysStatus()
      .then((s) => {
        setStatus(s)
        setLoading(false)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load settings')
        setLoading(false)
      })
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setSaveMessage('')
    if (!alchemyValue.trim()) {
      setError('Enter an Alchemy API key to save.')
      return
    }
    setSaving(true)
    try {
      const updated = await settingsApi.updateApiKeys({ alchemy_api_key: alchemyValue.trim() })
      setStatus(updated)
      setAlchemyValue('')
      setSaveMessage('Saved. Restart app for changes to fully apply.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="page-loading">Loading settings…</div>
  if (error) return <div className="page-error">{error}</div>

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>API keys</h1>
      </div>
      <p className="muted">
        Manage API keys that extend mantracker’s coverage. Keys are stored encrypted on disk and never sent to any server.
      </p>

      <form className="settings-form" onSubmit={handleSave}>
        <label>
          <span>Alchemy API key</span>
          <input
            type="password"
            value={alchemyValue}
            onChange={(e) => setAlchemyValue(e.target.value)}
            placeholder={status?.alchemy_api_key ? 'Key is set – enter a new one to replace' : 'Enter Alchemy API key'}
            disabled={saving}
          />
          <span className="hint">
            Used for EVM token balances. Existing key is not shown; entering a new one replaces it. Get a key at{' '}
            <a href="https://www.alchemy.com/" target="_blank" rel="noreferrer">
              alchemy.com
            </a>
            .
          </span>
        </label>
        {saveMessage && <p className="settings-success">{saveMessage}</p>}
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}

