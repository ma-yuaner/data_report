import { designRegistry } from './generated'
export function relatedRequirements(component:any,route:string){
  const field=designRegistry.fields.find(item=>item.key===component?.fieldKey || component?.binding?.endsWith(`.${item.key}`))
  if(field)return designRegistry.requirements.filter(item=>field.requirementIds.includes(item.id))
  const page=designRegistry.pages.find(item=>item.route===route)
  return page?designRegistry.requirements.filter(item=>item.pageIds.includes(page.id)):[]
}
