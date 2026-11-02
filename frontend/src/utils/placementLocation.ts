export function placementLocationName(type: unknown, code: unknown) {
  if (!code) return '不限'
  const names: Record<string, string> = { AIRPORT: '机场', CITY: '城市', COUNTRY: '国家', LEGACY: '历史地点' }
  return `${names[String(type || 'LEGACY')] || '地点'}：${code}`
}

export function placementRouteName(record?: { departureCode?: unknown; arrivalCode?: unknown; departureType?: unknown; arrivalType?: unknown }) {
  if (!record?.departureCode && !record?.arrivalCode) return '不限航程'
  return `${placementLocationName(record?.departureType, record?.departureCode)} → ${placementLocationName(record?.arrivalType, record?.arrivalCode)}`
}
