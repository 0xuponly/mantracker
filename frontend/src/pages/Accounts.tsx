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
              <div>
                <strong>{a.name}</strong>
                <span className="meta">{a.type}{a.provider ? ` · ${a.provider}` : ''}</span>
              </div>
              <button
                type="button"
                className="btn-danger"
                onClick={() => handleDelete(a.id)}
                disabled={deleting === a.id}
              >
                {deleting === a.id ? 'Removing…' : 'Remove'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
