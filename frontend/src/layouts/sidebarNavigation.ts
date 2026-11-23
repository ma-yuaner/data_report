import menu from './sidebar-menu.json'

export interface SidebarNode {
  key: string
  label: string
  aliases?: string[]
  children?: SidebarNode[]
  menuCode?: string
  anyPermission?: string[]
  businessRole?: string
  requiresAdmin?: boolean
  requiresAccountManagement?: boolean
}

interface SidebarUser {
  isAdmin?: boolean
  menuCodes?: string[]
  permissions?: string[]
  businessRoles?: { name: string }[]
}

interface SidebarDestination {
  key: string
  label: string
  groups: string[]
  groupKeys: string[]
  keywords: string[]
}

export const sidebarNodes: SidebarNode[] = menu

export function visibleSidebar(
  nodes: SidebarNode[],
  user: SidebarUser | null | undefined,
  canManageAccounts: boolean,
): SidebarNode[] {
  return nodes.flatMap(node => {
    if (node.requiresAccountManagement && !canManageAccounts) return []
    if (!user?.isAdmin) {
      if (node.requiresAdmin) return []
      if (node.menuCode && !user?.menuCodes?.includes(node.menuCode)) return []
      if (node.anyPermission && !node.anyPermission.some(permission => user?.permissions?.includes(permission))) return []
      if (node.businessRole && !user?.businessRoles?.some(role => role.name === node.businessRole)) return []
    }
    if (!node.children) return [node]
    const children = visibleSidebar(node.children, user, canManageAccounts)
    return children.length ? [{ ...node, children }] : []
  })
}

export function sidebarDestinations(nodes: SidebarNode[], parents: SidebarNode[] = []): SidebarDestination[] {
  return nodes.flatMap(node => {
    if (node.children) return sidebarDestinations(node.children, [...parents, node])
    const groups = parents.map(parent => parent.label)
    return [{
      key: node.key,
      label: node.label,
      groups,
      groupKeys: parents.map(parent => parent.key),
      keywords: [node.label, ...(node.aliases ?? []), ...groups, ...parents.flatMap(parent => parent.aliases ?? [])],
    }]
  })
}

export function matchesSidebarQuery(query: string, keywords: string[]): boolean {
  const normalize = (value: string) => value.normalize('NFKC').toLowerCase()
  const terms = normalize(query).trim().split(/\s+/)
  const searchable = keywords.map(keyword => normalize(keyword).replace(/\s+/g, ''))
  return terms.every(term => searchable.some(keyword => keyword.includes(term)))
}
