// Side-menu structure. Labels are i18n keys, never translated strings; the
// active entry is decided by the exact route name (see AppSideMenu.vue).

export type SideMenuRouteName = 'Home' | 'AlbumWorkspace' | 'Result' | 'AlbumLibrary'
export type SideMenuIconName = 'plan' | 'album' | 'trip' | 'library' | 'collapse' | 'expand'

export interface SideMenuItem {
  routeName: SideMenuRouteName
  labelKey: string
  icon: SideMenuIconName
}

export interface SideMenuGroup {
  labelKey: string
  items: SideMenuItem[]
}

export const SIDE_MENU_GROUPS: SideMenuGroup[] = [
  {
    labelKey: 'nav.groupCreate',
    items: [
      { routeName: 'Home', labelKey: 'nav.plan', icon: 'plan' },
      { routeName: 'AlbumWorkspace', labelKey: 'nav.album', icon: 'album' }
    ]
  },
  {
    labelKey: 'nav.groupMine',
    items: [
      { routeName: 'Result', labelKey: 'nav.trip', icon: 'trip' },
      { routeName: 'AlbumLibrary', labelKey: 'nav.library', icon: 'library' }
    ]
  }
]
