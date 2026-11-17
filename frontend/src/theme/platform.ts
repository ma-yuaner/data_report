import { theme } from 'ant-design-vue'
import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'

const light = {
  primary: '#08757a', accent: '#40b3b6', background: '#f3f7f8', surface: '#ffffff',
  text: '#18383f', secondary: '#5b747d', border: '#dce7e9', hover: '#f0f7f7', selected: '#e5f3f3',
}
const dark = {
  primary: '#60c9cb', accent: '#40b3b6', background: '#111f24', surface: '#192b31',
  text: '#e2eff0', secondary: '#aac0c6', border: '#334a52', hover: '#233c43', selected: '#25494f',
}

export function platformVariables(isDark: boolean) {
  const palette = isDark ? dark : light
  return Object.fromEntries(Object.entries(palette).map(([name, value]) => [`--platform-${name}`, value]))
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
