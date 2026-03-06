# Portfolio Tracker

A comprehensive portfolio tracker that aggregates balances from **bank accounts** (via Plaid), **brokerage accounts**, **centralized crypto exchanges** (e.g. Bybit, Coinbase, Kraken), and **blockchain wallets** (Bitcoin, EVM chains, Solana). All API keys and wallet addresses are stored **encrypted at rest** and never exposed in API responses or logs.

## Features

- **Banks & brokerage** – Link US accounts via [Plaid](https://plaid.com) (API required).
- **Centralized exchanges** – Add any [CCXT](https://github.com/ccxt/ccxt)-supported exchange with API key + secret (stored encrypted).
- **Blockchain wallets** – Read-only by address (no private keys): Bitcoin (mempool.space), EVM (Ethereum, Polygon, Arbitrum, Optimism, Base, Avalanche, BSC, Hyperliquid), Solana.
- **Secure storage** – Credentials encrypted with Fernet (key from `ENCRYPTION_KEY` or derived from `SECRET_KEY`).
- **Local-only, no sign-in** – Create and switch between **profiles** on your device. No email, no cloud. Export a profile to a file to back it up or move it to another machine; import from a file to restore.

## Quick start

**One command (after setup):** from the repo root run:

```bash
npm start
```

This starts the backend (FastAPI) and the frontend in a **dedicated desktop window** (Electron). No browser tab is opened.

### First-time setup

Run these from the **repo root** (`mantracker3/`). If you run step 1 and then step 2 in the same shell, you’ll be in `backend/` after step 1 — run `cd ..` before step 2 so you’re back at the repo root.

1. **Backend** (once):
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   cp .env.example .env       # edit .env as needed
   cd ..                      # back to repo root before next step
   ```

2. **Frontend** (once, from repo root):
   ```bash
   cd frontend
   npm install
   cd ..                      # back to repo root for npm start
   ```

3. **Run everything** from repo root:
   ```bash
   npm start
   ```

The app opens in a local Electron window and talks to the API on port 8000 (proxied via the dev server).

### Troubleshooting

**Frontend: `Library not loaded: ... libicui18n.74.dylib` (Node/ICU)**  
Your Node was built against a different ICU version than Homebrew has. Fix options:

1. **Reinstall Node so it links to current ICU:**
   ```bash
   brew reinstall icu4c node
   ```
2. **Or use a Node version manager** (avoids Homebrew ICU): install [nvm](https://github.com/nvm-sh/nvm) or [fnm](https://github.com/Schniz/fnm), then `nvm install 20` (or fnm equivalent) and run `npm install` / `npm run dev` in that shell.

**Backend: `python: command not found`**  
Use `python3` instead: `python3 -m venv .venv` and run the app with `python3` or the venv’s `python` after activating.

**Backend: `cp: production is not a directory`**  
Run the copy and comment as two steps: `cp .env.example .env` then edit `.env` as needed. Don’t paste the `# comment` as part of the `cp` arguments.

**Upgrading from an older (user-based) version:** The app now uses local profiles instead of email sign-in. If you have an existing `backend/portfolio.db`, remove it and run again so the new schema (profiles table) is created. Export any data you need before deleting.

### Optional: Plaid (banks/brokerage)

1. Create a [Plaid](https://dashboard.plaid.com) account and get **Client ID** and **Secret**.
2. In backend `.env` set:
   - `PLAID_CLIENT_ID=...`
   - `PLAID_SECRET=...`
   - `PLAID_ENV=sandbox` (or `development` / `production`)

Then use “Add account → Bank or brokerage” in the UI to open Plaid Link and link an account.

### Adding other accounts

- **Exchange** – Choose provider (e.g. Binance), enter a label, API key, and secret. Optional passphrase for exchanges that use it (e.g. Coinbase). Credentials are encrypted before storage.
- **Wallet** – Paste the **public address** only. Choose **EVM (all chains)** to see balances from every supported EVM chain (Ethereum, Polygon, Arbitrum, Optimism, Base, Avalanche, BSC, HyperEVM) in one place; or pick a single chain. **Solana** shows native SOL and all SPL tokens. **EVM** shows all tokens (native + ERC‑20) when `COVALENT_API_KEY` is set in backend `.env` (free at [covalenthq.com](https://www.covalenthq.com)); HyperEVM requires the key. With **EVM (all chains)**, one address is queried across all chains and each balance is labeled (e.g. "ETH (Ethereum)", "USDC (Arbitrum)").

## Security notes

- Set **ENCRYPTION_KEY** in production (Fernet key). If unset, a key is derived from **SECRET_KEY** (less ideal).
- **Import/export**: Exported profile files contain encrypted credentials. They can only be decrypted on a machine that uses the same **ENCRYPTION_KEY** (e.g. same `.env`). Keep export files private.
- Run the backend over HTTPS in production and restrict CORS origins.
- API keys and wallet addresses are only decrypted in memory when fetching balances; they are never returned in API responses or written to logs.

## Project layout

```
mantracker3/
├── backend/
│   ├── app/
│   │   ├── adapters/       # Plaid, CCXT, wallet (BTC/EVM/Solana)
│   │   ├── models/         # Profile, Account, AccountCredential
│   │   ├── routers/        # profiles, accounts, plaid, portfolio
│   │   ├── security/      # encryption, profile-scoped access (X-Profile-Id)
│   │   ├── services/       # credential store, portfolio aggregation
│   │   ├── config.py
│   │   ├── db.py
│   │   └── main.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/               # Vite + React + TypeScript + Electron
│   ├── src/
│   │   ├── pages/          # ProfilePicker, Dashboard, Accounts, AddAccount, Profiles
│   │   ├── api.ts
│   │   └── ProfileContext.tsx
│   └── package.json
└── README.md
```

## API overview

All account/plaid/portfolio routes require the **X-Profile-Id** header (current profile id). Profile list/create/import/export do not.

| Endpoint | Description |
|----------|-------------|
| `GET /profiles` | List all profiles |
| `POST /profiles` | Create profile (body: `{ name }`) |
| `PATCH /profiles/{id}` | Rename profile |
| `DELETE /profiles/{id}` | Delete profile and its accounts |
| `GET /profiles/{id}/export` | Download profile as JSON (accounts + encrypted credentials) |
| `POST /profiles/import` | Import profile from uploaded JSON file |
| `GET /accounts` | List accounts (X-Profile-Id) |
| `POST /accounts` | Add exchange or wallet (X-Profile-Id) |
| `DELETE /accounts/{id}` | Remove account (X-Profile-Id) |
| `GET /plaid/link_token` | Plaid link token (X-Profile-Id) |
| `POST /plaid/exchange` | Exchange public token, create bank/brokerage account (X-Profile-Id) |
| `GET /portfolio` | Aggregated balances (X-Profile-Id) |
