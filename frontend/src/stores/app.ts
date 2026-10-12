import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const collapsed = ref(false)
  const darkMode = ref(false)
  const navigating = ref(false)

  function toggleCollapsed() {
    collapsed.value = !collapsed.value
  }

  function toggleTheme() {
    darkMode.value = !darkMode.value
  }

  function startNavigation() {
    navigating.value = true
  }

  function finishNavigation() {
    navigating.value = false
  }

  return { collapsed, darkMode, navigating, toggleCollapsed, toggleTheme, startNavigation, finishNavigation }
})

