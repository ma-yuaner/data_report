import { theme } from 'ant-design-vue'
import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'

const light = {
  primary: '#2673ad', accent: '#397eb8', background: '#f7f9fc', surface: '#ffffff',
  text: '#203447', secondary: '#56697a', border: '#dfe7ef', hover: '#f0f6fc', selected: '#eaf3fc',
}
const dark = {
  primary: '#79b5e6', accent: '#79b5e6', background: '#141e28', surface: '#1c2b38',
  text: '#e2ecf5', secondary: '#acbecf', border: '#374c5e', hover: '#263c4e', selected: '#233c50',
}

const navigation = {
  'nav-background': '#30373e', 'nav-text': '#dce4eb', 'nav-secondary': '#b6c2cc',
  'nav-selected': '#405568', 'nav-selected-text': '#d9efff', 'nav-hover': '#3b4751',
  'nav-border': '#48535c', 'nav-indicator': '#5da5e0',
}

export function platformVariables(isDark: boolean) {
  const palette = isDark ? dark : light
  return Object.fromEntries(Object.entries({ ...palette, ...navigation }).map(([name, value]) => [`--platform-${name}`, value]))
}

// Keep navigation dark without applying its colors to account menus or content.
export function platformNavigationTheme(): ThemeConfig {
  return { components: { Menu: {
    colorItemBg: navigation['nav-background'], colorSubItemBg: 'transparent',
    colorItemText: navigation['nav-text'], colorGroupTitle: navigation['nav-secondary'],
    colorItemTextHover: '#ffffff', colorItemBgHover: navigation['nav-hover'],
    colorItemBgActive: navigation['nav-hover'],
    colorItemBgSelected: navigation['nav-selected'], colorItemTextSelected: navigation['nav-selected-text'],
  } } }
}

export function platformTheme(isDark: boolean): ThemeConfig {
  const p = isDark ? dark : light
  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: p.primary, colorInfo: p.primary, colorLink: p.primary,
      colorBgLayout: p.background, colorBgContainer: p.surface,
      colorText: p.text, colorTextSecondary: p.secondary, colorBorder: p.border,
      borderRadius: 8, fontSize: 14,
      fontFamily: '"Microsoft YaHei", "PingFang SC", Inter, system-ui, sans-serif',
    },
    components: {
      Layout: { colorBgHeader: p.surface, colorBgBody: p.background },
      Menu: {
        controlHeightLG: 42, itemMarginInline: 10, radiusItem: 7, radiusSubMenuItem: 7,
        colorItemText: p.secondary, colorItemTextHover: p.primary, colorItemBgHover: p.hover,
        colorItemTextSelected: p.primary, colorItemBgSelected: p.selected,
        colorSubItemBg: 'transparent', colorItemBg: p.surface,
      },
      Table: { colorFillAlter: p.hover, colorFillSecondary: p.hover, colorBorderSecondary: p.border },
    },
  }
}
