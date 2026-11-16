export interface Asset { asset_id: string; source: string; instance_id: string; database: string; table: string; object_type: string; table_comment: string; column_count: string; partition_column_count: string; layer_candidate: string; missing_column_comment_count: string; collected_at: string }
export interface Column { asset_id: string; name: string; type: string; comment: string; nullable: string; key: string; is_partition: string }
export interface Edge { evidence_id?: string; source_asset_id: string; target_asset_id: string; source_reference: string; target_reference: string; edge_type: string; evidence: string; endpoint_status: string; runtime_status: string; sha256: string }
export interface Gap { gap_id?: string; asset_id: string; gap: string; detail: string }
export interface Dataset { tables: Asset[]; columns: Column[]; edges: Edge[]; gaps: Gap[]; databases: { source: string; database: string; object_count: string; collected_at: string }[] }
export const emptyDataset: Dataset = { tables: [], columns: [], edges: [], gaps: [], databases: [] }
export const gapNames: Record<string, string> = { missing_business_table_comment: '缺表用途', missing_column_comments: '字段注释不完整', no_declared_primary_key: '未声明主键', layer_unclassified: '分层待分类', lineage_endpoint_unresolved: '血缘端点待核对' }
export const edgeNames: Record<string, string> = { etl_static: 'ETL源码依赖', live_view_definition: '实库视图定义', datax_config: 'DataX配置依赖' }
export function filterAssets(rows: Asset[], query: string, database: string, layer: string) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return rows.filter(row => (!database || row.source + '/' + row.database === database)
    && (!layer || row.layer_candidate === layer)
    && words.every(word => [row.table, row.table_comment, row.database, row.source].join(' ').toLocaleLowerCase().includes(word)))
}
export function downstream(start: string, edges: Edge[], maxDepth = 5) {
  const visited = new Set([start]), result: { asset_id: string; depth: number }[] = []
  let frontier = [start]
  for (let depth = 1; depth <= maxDepth && frontier.length; depth++) {
    const next: string[] = []
    for (const node of frontier) for (const edge of edges) {
      if (edge.source_asset_id !== node || edge.endpoint_status !== 'both_exist' || !edge.target_asset_id || visited.has(edge.target_asset_id)) continue
      visited.add(edge.target_asset_id); next.push(edge.target_asset_id); result.push({ asset_id: edge.target_asset_id, depth })
    }
    frontier = next
  }
  return result
}
