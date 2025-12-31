export const prettyValue = (value: unknown, fallback = '—'): string => {
  if (value === undefined || value === null) return fallback
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    const text = String(value)
    return text.length > 100 ? `${text.slice(0, 100)}…` : text
  }
  try {
    return JSON.stringify(value)
  } catch {
    return fallback
  }
}
