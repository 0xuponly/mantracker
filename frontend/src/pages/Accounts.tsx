import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { accounts } from '../api'
import type { AccountSummary } from '../api'
import './Accounts.css'

export default function Accounts() {
  const [list, setList] = useState<AccountSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [savingId, setSavingId] = useState<number | null>(null)
  const [editError, setEditError] = useState('')

  function load() {
    setError('')
    accounts
      .listWithTimeout()
      .then(setList)
      .catch((e) => setError(e?.message ?? 'Failed to load accounts'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  async function handleDelete(id: number) {
    if (!confirm('Remove this account? Stored credentials will be deleted.')) return
    setDeleting(id)
    try {
      await accounts.delete(id)
      setList((prev) => prev.filter((a) => a.id !== id))
    } finally {
      setDeleting(null)
    }
  }

  function startEdit(a: AccountSummary) {
    setEditingId(a.id)
    setEditName(a.name)
    setEditError('')
  }

  function cancelEdit() {
    setEditingId(null)
    setEditName('')
    setEditError('')
  }

  async function saveEdit(id: number) {
    const name = editName.trim()
    if (!name) {
      setEditError('Name cannot be empty.')
      return
    }
    setSavingId(id)
    setEditError('')
    try {
      const updated = await accounts.update(id, { name })
      setList((prev) => prev.map((a) => (a.id === id ? updated : a)))
      setEditingId(null)
      setEditName('')
    } catch (e) {
      setEditError(e instanceof Error ? e.message : 'Failed to save changes.')
    } finally {
      setSavingId(null)
    }
  }

  if (loading) return <div className="page-loading">Loading accounts…</div>
  if (error) return <div className="page-error">{error}</div>

  return (
    <div className="accounts-page">
      <div className="page-header">
        <h1>Accounts</h1>
        <Link to="/accounts/add" className="btn-primary">Add account</Link>
      </div>
      <p className="muted">Bank and brokerage accounts are added via Plaid. Exchanges and wallets use API keys or addresses (stored encrypted).</p>
      {list.length === 0 ? (
        <div className="empty-state">
          <p>No accounts yet.</p>
          <Link to="/accounts/add" className="btn-primary">Add account</Link>
        </div>
      ) : (
        <ul className="accounts-list">
          {list.map((a) => (
            <li key={a.id} className="account-row">
              {editingId === a.id ? (
                <>
                  <div>
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      disabled={savingId === a.id}
                    />
                    <span className="meta">{a.type}{a.provider ? ` · ${a.provider}` : ''}</span>
                    {editError && <p className="page-error" style={{ marginTop: '0.25rem' }}>{editError}</p>}
                  </div>
                  <div className="account-row-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => saveEdit(a.id)}
                      disabled={savingId === a.id}
                    >
                      {savingId === a.id ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={cancelEdit}
                      disabled={savingId === a.id}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <strong>{a.name}</strong>
                    <span className="meta">{a.type}{a.provider ? ` · ${a.provider}` : ''}</span>
                  </div>
                  <div className="account-row-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => startEdit(a)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn-danger"
                      onClick={() => handleDelete(a.id)}
                      disabled={deleting === a.id}
                    >
                      {deleting === a.id ? 'Removing…' : 'Remove'}
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
