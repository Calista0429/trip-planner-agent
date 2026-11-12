import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'

// A2 palette. Category colors are shared by list headings and map markers so a
// hotel/sight/meal reads the same everywhere.
export const COLORS = {
  paper: '#f6f7f5',
  pine: '#315348',
  pineDark: '#24403a',
  ink: '#2a3d35',
  muted: '#6d7971',
  line: '#dce2dc',
  hotel: '#98614f',
  attraction: '#315348',
  meal: '#856435'
} as const

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: COLORS.pine,
    colorLink: COLORS.pine,
    colorText: COLORS.ink,
    colorTextSecondary: COLORS.muted,
    colorBorder: '#c5d0c6',
    colorBorderSecondary: COLORS.line,
    colorBgLayout: COLORS.paper,
    borderRadius: 2,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif',
    controlOutline: 'rgba(49, 83, 72, 0.18)'
  }
}
