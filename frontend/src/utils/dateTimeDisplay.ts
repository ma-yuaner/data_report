/** Display only: preserve the source clock, precision, offset and underlying value. */
export function formatDateTimeDisplay(value: unknown): string {
  return value == null ? '—' : String(value).replace(/(\d{4}-\d{2}-\d{2})T(?=\d{2}:\d{2})/g, '$1 ')
}

export function isDateTimeField(field: string): boolean {
  return /(?:At|Time|Date|_at|_time|_date|_datetime)$/.test(field) || field === 'at' || field === 'asOf'
}

export function displayDateTimeField(value: unknown, field: string): unknown {
  return isDateTimeField(field) ? formatDateTimeDisplay(value) : value
}
