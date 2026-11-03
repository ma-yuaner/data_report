import { http, type ApiEnvelope } from './http'

export interface CabinReference {
  airline: string
  cabins: string[]
  hasUnspecified: boolean
}

export async function fetchCabinReference(airline: string) {
  const response = await http.get<ApiEnvelope<CabinReference>>('/v1/smart-placement/cabin-reference', { params: { airline } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
