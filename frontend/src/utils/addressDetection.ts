/**
 * Detect wallet address type from string (Bitcoin, EVM, Solana).
 * Used to auto-set chain when user pastes or types an address.
 */

export type DetectedAddressType = 'bitcoin' | 'ethereum' | 'solana' | null

const EVM_REGEX = /^0x[a-fA-F0-9]{40}$/
const BITCOIN_BECH32_REGEX = /^bc1[a-z0-9]{39,59}$/
const BITCOIN_LEGACY_REGEX = /^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$/
const BASE58_REGEX = /^[1-9A-HJ-NP-Za-km-z]+$/

export function detectAddressType(input: string): DetectedAddressType {
  const s = input.trim()
  if (!s) return null

  if (EVM_REGEX.test(s)) return 'ethereum'
  if (BITCOIN_BECH32_REGEX.test(s)) return 'bitcoin'
  if (BITCOIN_LEGACY_REGEX.test(s)) return 'bitcoin'
  if (s.length >= 32 && s.length <= 44 && BASE58_REGEX.test(s)) return 'solana'

  return null
}

/** Split comma-, space-, or newline-separated text into trimmed non-empty strings. */
export function splitList(text: string): string[] {
  if (!text || !text.trim()) return []
  return text
    .split(/[\s,\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}
