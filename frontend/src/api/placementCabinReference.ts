import { http, type ApiEnvelope } from './http'

export interface CabinReference {
  airline: string
  // Each entry is one unmodified ERP cabin value, including its original separators.
  cabins: string[]
  hasUnspecified: boolean
}

export async function fetchCabinReference(airline: string) {
  const response = await http.get<ApiEnvelope<CabinReference>>('/v1/smart-placement/cabin-reference', { params: { airline } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
