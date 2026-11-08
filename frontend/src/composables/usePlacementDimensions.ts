import { computed, type Ref } from 'vue'
import type { PlacementDimensionOption, PlacementDimensionOptions } from '@/api/smartPlacement'

interface DimensionForm {
  platformName?: unknown
  platformCode?: unknown
  siteName?: unknown
  siteCode?: unknown
  productType?: unknown
  airlineCode?: unknown
}

function selectOptions(items: PlacementDimensionOption[] | undefined, selected: unknown) {
  const values = new Map<string, string>()
  for (const item of items || []) {
    if (item.value) values.set(item.value, item.label || item.value)
  }
  const current = String(selected || '')
  if (current && !values.has(current)) values.set(current, current)
  return Array.from(values, ([value, label]) => ({ value, label }))
}

export function usePlacementDimensions<T extends DimensionForm>(
  dimensions: Ref<PlacementDimensionOptions | undefined>,
  form: Ref<T>,
) {
  const platformOptions = computed(() => selectOptions(dimensions.value?.platforms, form.value.platformName))
  const siteOptions = computed(() => selectOptions(
    dimensions.value?.sites.filter(item => !form.value.platformName || item.platformName === form.value.platformName),
    form.value.siteName,
  ))
  const productOptions = computed(() => selectOptions(
    dimensions.value?.products.filter(item => !form.value.platformName || item.platformName === form.value.platformName),
    form.value.productType,
  ))
  const airlineOptions = computed(() => selectOptions(dimensions.value?.airlines, form.value.airlineCode))

  function selectPlatform(value?: string) {
    const platform = dimensions.value?.platforms.find(item => item.value === value)
    form.value.platformCode = platform?.code || ''
    if (!value) {
      form.value.siteName = ''
      form.value.siteCode = ''
      form.value.productType = ''
      return
    }
    if (!dimensions.value?.sites.some(item => item.value === form.value.siteName && item.platformName === value)) {
      form.value.siteName = ''
      form.value.siteCode = ''
    }
    if (!dimensions.value?.products.some(item => item.value === form.value.productType && item.platformName === value)) {
      form.value.productType = ''
    }
  }

  function selectSite(value?: string) {
    const site = dimensions.value?.sites.find(item =>
      item.value === value && (!form.value.platformName || item.platformName === form.value.platformName),
    )
    form.value.siteCode = site?.code || ''
  }

  return { platformOptions, siteOptions, productOptions, airlineOptions, selectPlatform, selectSite }
}
