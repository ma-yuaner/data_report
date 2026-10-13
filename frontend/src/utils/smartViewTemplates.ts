export interface NamedViewTemplate<T> {
  id: string
  name: string
  value: T
  updatedAt: string
}

function storageKey(scope: string, userId: number | string | undefined) {
  return `smart-view-templates:${scope}:user-${userId ?? 'anonymous'}`
}

export function loadViewTemplates<T>(
  scope: string,
  userId: number | string | undefined,
  isValid: (value: unknown) => value is T,
): NamedViewTemplate<T>[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(scope, userId)) || '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is NamedViewTemplate<T> => (
      Boolean(item) && typeof item.id === 'string' && typeof item.name === 'string'
      && typeof item.updatedAt === 'string' && isValid(item.value)
    )).slice(0, 20)
  } catch {
    return []
  }
}

export function saveViewTemplate<T>(
  scope: string,
  userId: number | string | undefined,
  templates: NamedViewTemplate<T>[],
  rawName: string,
  value: T,
) {
  const name = rawName.trim()
  if (!name) throw new Error('请输入模板名称')
  if (name.length > 30) throw new Error('模板名称不能超过30个字符')
  const existing = templates.find(item => item.name === name)
  const next: NamedViewTemplate<T> = {
    id: existing?.id || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    value,
    updatedAt: new Date().toISOString(),
  }
  const values = [next, ...templates.filter(item => item.id !== next.id)].slice(0, 20)
  localStorage.setItem(storageKey(scope, userId), JSON.stringify(values))
  return { values, saved: next }
}

export function removeViewTemplate<T>(
  scope: string,
  userId: number | string | undefined,
  templates: NamedViewTemplate<T>[],
  templateId: string,
) {
  const values = templates.filter(item => item.id !== templateId)
  localStorage.setItem(storageKey(scope, userId), JSON.stringify(values))
  return values
}
