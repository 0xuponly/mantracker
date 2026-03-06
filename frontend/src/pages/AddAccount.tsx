import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { accounts, plaid } from '../api'
import { detectAddressType, splitList } from '../utils/addressDetection'
import './AddAccount.css'

type Flow = 'choose' | 'plaid' | 'exchange' | 'wallet'

const EXCHANGE_PROVIDERS = [
  'binance', 'coinbase', 'kraken', 'kucoin', 'bybit', 'okx', 'gateio', 'bitfinex', 'gemini', 'bitstamp',
]

declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        onSuccess: (public_token: string) => void;
        onExit: (err: unknown) => void;
        onEvent?: (name: string, meta: unknown) => void;
      }) => { open: () => void };
    };
  }
}

export default function AddAccount() {
  const [flow, setFlow] = useState<Flow>('choose')
  const [plaidReady, setPlaidReady] = useState(false)
  const [exchangeName, setExchangeName] = useState('')
  const [exchangeApiKey, setExchangeApiKey] = useState('')
  const [exchangeSecret, setExchangeSecret] = useState('')
  const [exchangePassphrase, setExchangePassphrase] = useState('')
  const [walletAddress, setWalletAddress] = useState('')
  const [accountName, setAccountName] = useState('')
  const [plaidAccountName, setPlaidAccountName] = useState('')
  const [plaidAccountType, setPlaidAccountType] = useState<'bank' | 'brokerage'>('bank')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const navigate = useNavigate()

  // Load Plaid script
  useEffect(() => {
    if (flow !== 'plaid') return
    if (document.getElementById('plaid-script')) {
      setPlaidReady(!!window.Plaid)
      return
    }
    const script = document.createElement('script')
    script.id = 'plaid-script'
    script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js'
    script.onload = () => setPlaidReady(true)
    document.head.appendChild(script)
  }, [flow])

  const openPlaid = useCallback(async () => {
    setError('')
    try {
      const { link_token } = await plaid.linkToken()
      if (!window.Plaid) {
        setError('Plaid not loaded. Refresh and try again.')
        return
      }
      window.Plaid.create({
        token: link_token,
        onSuccess: async (public_token) => {
          setLoading(true)
          setError('')
          try {
            await plaid.exchange(
              public_token,
              plaidAccountName || 'Plaid account',
              plaidAccountType
            )
            navigate('/accounts')
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Exchange failed')
          } finally {
            setLoading(false)
          }
        },
        onExit: () => {},
      }).open()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start Plaid')
    }
  }, [plaidAccountName, plaidAccountType, navigate])

  async function handleAddExchange(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const cred: Record<string, string> = {
        api_key: exchangeApiKey,
        secret: exchangeSecret,
      }
      if (exchangePassphrase) cred.password = exchangePassphrase
      await accounts.create({
        name: accountName || `${exchangeName} exchange`,
        type: 'exchange',
        provider: exchangeName,
        credentials: cred,
      })
      navigate('/accounts')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add account')
    } finally {
      setLoading(false)
    }
  }

  /** Parse addresses and names; detect type per address; create one account per address. */
  async function handleAddWallet(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    const addressList = splitList(walletAddress)
    if (addressList.length === 0) {
      setError('Enter at least one wallet address.')
      return
    }
    const nameList = splitList(accountName)
    const results: { index: number; address: string; error?: string }[] = []
    setLoading(true)
    try {
      for (let i = 0; i < addressList.length; i++) {
        const address = addressList[i]
        const detected = detectAddressType(address)
        if (!detected) {
          results.push({ index: i + 1, address: address.slice(0, 20) + '…', error: 'Unknown address type' })
          continue
        }
        const provider = detected === 'ethereum' ? 'evm' : detected
        const name = nameList[i] || `${provider} wallet ${i + 1}`
        try {
          await accounts.create({
            name,
            type: 'wallet',
            provider,
            credentials: { address },
          })
        } catch (err) {
          results.push({
            index: i + 1,
            address: address.slice(0, 20) + '…',
            error: err instanceof Error ? err.message : 'Failed',
          })
        }
      }
      const failed = results.filter((r) => r.error)
      if (failed.length > 0) {
        setError(
          failed.length === addressList.length
            ? failed[0]?.error ?? 'Failed to add wallets'
            : `Added ${addressList.length - failed.length}; failed: ${failed.map((f) => `#${f.index} ${f.error}`).join('; ')}`
        )
      }
      if (failed.length < addressList.length) {
        navigate('/accounts')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="add-account">
      <div className="page-header">
        <h1>Add account</h1>
        <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>
          Back
        </button>
      </div>

      {flow === 'choose' && (
        <div className="flow-cards">
          <button type="button" className="flow-card" onClick={() => setFlow('plaid')}>
            <span className="flow-icon">🏦</span>
            <strong>Bank or brokerage</strong>
            <span className="flow-desc">Link via Plaid (US)</span>
          </button>
          <button type="button" className="flow-card" onClick={() => setFlow('exchange')}>
            <span className="flow-icon">📊</span>
            <strong>Centralized exchange</strong>
            <span className="flow-desc">API key (Binance, Coinbase, etc.)</span>
          </button>
          <button type="button" className="flow-card" onClick={() => setFlow('wallet')}>
            <span className="flow-icon">🔗</span>
            <strong>Blockchain wallet</strong>
            <span className="flow-desc">Read-only address (BTC, ETH, SOL, …)</span>
          </button>
        </div>
      )}

      {flow === 'plaid' && (
        <div className="flow-form">
          <label>
            Account name
            <input
              type="text"
              placeholder="e.g. Chase Checking"
              value={plaidAccountName}
              onChange={(e) => setPlaidAccountName(e.target.value)}
            />
          </label>
          <label>
            Type
            <select
              value={plaidAccountType}
              onChange={(e) => setPlaidAccountType(e.target.value as 'bank' | 'brokerage')}
            >
              <option value="bank">Bank</option>
              <option value="brokerage">Brokerage</option>
            </select>
          </label>
          {error && <div className="error">{error}</div>}
          <button
            type="button"
            className="btn-primary"
            onClick={openPlaid}
            disabled={loading || !plaidReady}
          >
            {!plaidReady ? 'Loading Plaid…' : loading ? 'Linking…' : 'Open Plaid Link'}
          </button>
          <button type="button" className="btn-link" onClick={() => setFlow('choose')}>
            Cancel
          </button>
        </div>
      )}

      {flow === 'exchange' && (
        <form className="flow-form" onSubmit={handleAddExchange}>
          <label>
            Exchange
            <select
              value={exchangeName}
              onChange={(e) => setExchangeName(e.target.value)}
              required
            >
              <option value="">Select…</option>
              {EXCHANGE_PROVIDERS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            Account name
            <input
              type="text"
              placeholder="e.g. Binance main"
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
            />
          </label>
          <label>
            API key
            <input
              type="password"
              value={exchangeApiKey}
              onChange={(e) => setExchangeApiKey(e.target.value)}
              required
              placeholder="Stored encrypted"
              autoComplete="off"
            />
          </label>
          <label>
            API secret
            <input
              type="password"
              value={exchangeSecret}
              onChange={(e) => setExchangeSecret(e.target.value)}
              required
              placeholder="Stored encrypted"
              autoComplete="off"
            />
          </label>
          <label>
            Passphrase (optional, for exchanges that use it)
            <input
              type="password"
              value={exchangePassphrase}
              onChange={(e) => setExchangePassphrase(e.target.value)}
              placeholder="e.g. Coinbase"
              autoComplete="off"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Adding…' : 'Add exchange'}
          </button>
          <button type="button" className="btn-link" onClick={() => setFlow('choose')}>
            Cancel
          </button>
        </form>
      )}

      {flow === 'wallet' && (
        <form className="flow-form" onSubmit={handleAddWallet}>
          <label>
            Addresses (one or more — comma-, space-, or newline-separated; type auto-detected per address)
            <textarea
              value={walletAddress}
              onChange={(e) => setWalletAddress(e.target.value)}
              required
              placeholder={'0x…  bc1…  Solana…\nor: addr1, addr2, addr3'}
              spellCheck={false}
              rows={4}
            />
          </label>
          {splitList(walletAddress).length > 0 && (
            <p className="muted" style={{ marginTop: '-0.5rem', marginBottom: 0 }}>
              {splitList(walletAddress).length} address(es) — types detected per address (EVM, Bitcoin, Solana)
            </p>
          )}
          <label>
            Names (optional; same order — comma-, space-, or newline-separated)
            <textarea
              placeholder="Main wallet  Cold storage  Exchange"
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
              rows={2}
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Adding…' : splitList(walletAddress).length > 1 ? `Add ${splitList(walletAddress).length} wallets` : 'Add wallet'}
          </button>
          <button type="button" className="btn-link" onClick={() => setFlow('choose')}>
            Cancel
          </button>
        </form>
      )}
    </div>
  )
}
