/** Format a two-decimal source value without converting its cents to Number. */
export function decimalDisplay(value: unknown): string {
  if (value == null || value === '') return '—'
  const raw = String(value)
  const match = /^(-?)(\d+)(?:\.(\d{0,2}))?$/.exec(raw)
  if (!match) return raw
  return `${match[1]}${match[2]!.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${(match[3] || '').padEnd(2, '0')}`
}
