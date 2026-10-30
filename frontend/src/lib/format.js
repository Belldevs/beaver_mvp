// Number formatting. The currency symbol always comes from the user's currency setting.
export function fmt(value, format, currency = 'USD') {
  if (value === null || value === undefined) return '-'
  if (format === 'currency') {
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2 }).format(value)
    } catch {
      return String(value)
    }
  }
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export function compact(value, format, currency = 'USD') {
  const n = Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
  if (format !== 'currency') return n
  try {
    const sym = new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).formatToParts(0).find((p) => p.type === 'currency')?.value
    return (sym || '') + n
  } catch {
    return n
  }
}
