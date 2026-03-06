import { useState } from 'react'
import { unlockApi } from '../api'
import './UnlockScreen.css'

type Props = {
  onUnlocked: () => void
}

export default function UnlockScreen({ onUnlocked }: Props) {
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!passphrase.trim()) {
      setError('Enter your passphrase.')
      return
    }
    setSubmitting(true)
    try {
      await unlockApi.unlock(passphrase)
      setPassphrase('')
      onUnlocked()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unlock failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="unlock-screen">
      <div className="unlock-card">
        <h1>Unlock mantracker</h1>
        <p className="unlock-description">
          Enter your app passphrase to unlock. If this is your first time, choose a passphrase—you’ll need it each time you start the app.
        </p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="unlock-passphrase">Passphrase</label>
          <input
            id="unlock-passphrase"
            type="password"
            autoComplete="current-password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="App passphrase"
            disabled={submitting}
            autoFocus
          />
          {error && <p className="unlock-error">{error}</p>}
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Unlocking…' : 'Unlock'}
          </button>
        </form>
      </div>
    </div>
  )
}
