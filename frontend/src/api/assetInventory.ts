import { http, type ApiEnvelope } from './http'

export interface Dictionary { businessUse: string; grain: string; businessKey: string; timeField: string; timeMeaning: string; domain: string; owner: string; refreshSla: string }
export interface DictionaryState { publishedRevision: number; published: Partial<Dictionary>; draftRevision: number; draft: Partial<Dictionary> | null; history: {revision:number;values:Partial<Dictionary>;updatedAt:string}[] }
export interface AssetObject { asset_id:string;source:string;instance_id:string;database:string;table:string;object_type:string;table_comment:string;column_count:number;partition_column_count:number;layer_candidate:string;collected_at:string;gapCount:number;dictionary:{revision:number;values:Partial<Dictionary>;updatedAt:string|null};registeredContext:{purpose:string;grain:string;evidence:string;timeField?:string;metrics?:string[]}|null }
export interface AssetColumn { name:string;type:string;comment:string;nullable:string;key:string;is_partition:string }
export interface AssetGap { gap_id:string;asset_id:string;gap:string;detail:string;canLocate?:boolean }
export interface AssetEdge { evidence_id:string;source_asset_id:string;target_asset_id:string;source_reference:string;target_reference:string;edge_type:string;evidence:string;sha256:string;endpoint_status:string;runtime_status:string }
export interface AssetSummary { version:string;publishedAt:string;databases:{source:string;instance_id:string;database:string;object_count:string;collected_at:string;status:string}[];objectCount:number;fieldCount:number;dictionaryCount:number;layers:Record<string,number>;gapCounts:Record<string,number>;gapLabels:Record<string,string>;evidenceCounts:Record<string,number>;edgeEvidenceCount:number;uniqueDependencyCount:number;matchedEvidenceCount:number;runtimeEvidenceStatus:string;coverage:{sqlFiles?:number;parsed?:number;partialOrFailed?:number;unsupported?:number};canManageDictionary:boolean;scopeNote:string }
export interface AssetPage { version:string;total:number;page:number;pageSize:number;items:AssetObject[] }
export interface AssetDetail { version:string;object:AssetObject;columns:AssetColumn[];keys:Record<string,string>[];indexes:Record<string,string>[];gaps:AssetGap[];dictionaryState:DictionaryState }
export interface AssetLineage { version:string;runtimeEvidenceStatus:string;edges:AssetEdge[];impacts:{asset_id:string;table:string;source:string;database:string;depth:number}[];unresolvedFrontier:number|null;truncated:boolean }
async function get<T>(path:string, params?:Record<string,string|number|undefined>) { return (await http.get<ApiEnvelope<T>>('/v1/assets/inventory/'+path,{params})).data.data }
export const inventoryApi = {
  summary:()=>get<AssetSummary>('summary'),
  objects:(params:Record<string,string|number|undefined>)=>get<AssetPage>('objects',params),
  detail:(assetId:string,version:string)=>get<AssetDetail>('detail',{assetId,version}),
  lineage:(assetId:string,version:string,scope:string,depth=5)=>get<AssetLineage>('lineage',{assetId,version,scope,depth}),
  gaps:(params:Record<string,string|number|undefined>)=>get<{version:string;total:number;items:AssetGap[]}>('gaps',params),
  save:async (body:{assetId:string;version:string;draftRevision:number;publishedRevision:number;values:Dictionary})=>(await http.put<ApiEnvelope<DictionaryState>>('/v1/assets/inventory/dictionary',body)).data.data,
  publish:async (body:{assetId:string;version:string;draftRevision:number;publishedRevision:number})=>(await http.post<ApiEnvelope<DictionaryState>>('/v1/assets/inventory/dictionary/publish',body)).data.data,
}
