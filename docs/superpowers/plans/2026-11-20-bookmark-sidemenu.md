# Bookmark SideMenu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户指定交给 Claude Code 实现；本次只交付方案与 prompt，不执行产品改造。

**Goal:** 将用户选定的「相册书签」方案落到真实 Vue 应用，提供四个导航入口与手机抽屉，保留现有规划/结果流程。

**Architecture:** App.vue 持有应用外壳，受控 AppSideMenu 负责导航内容；Vue Router 保持页面与选中状态的唯一来源。新增两个诚实的相册占位页，通过独立草稿存储和最小路由保护解决切页引入的数据丢失；继续使用现有页面卸载生命周期。

**Tech Stack:** Vue 3、TypeScript、Vue Router 4、Ant Design Vue 4、CSS、Vitest、Vue Test Utils、jsdom；不新增依赖。

**Spec:** [完整设计规格与 Claude Code Prompt](../../bookmark-sidemenu-claude-code-prompt.md)。视觉原型为 `out/sidemenu-designs-20261119/trip-sidemenu-concepts.html` 中的 `.tp-v3`。

## Global Constraints

- 用户已选定「相册书签」，不重新讨论风格；方案内的工程细节为本次建议，按规格执行。
- 本轮仅前端导航、两个相册占位页与必要的状态/布局保护；不实现真实相册生成、上传、存储、导出或后端。
- 展开 `188px`、折叠 `76px`，移动断点 `<=760px`；抽屉宽度 `min(280px, calc(100vw - 48px))`。
- 复用 `#f6f7f5 / #315348 / #2a3d35` 与现有宋体/无衬线；侧栏纸页 `#eef0e8`、外伸书签 `9px`。
- RouterLink 与精确 route name 高亮；保留 `/`、`/result?day=N`、`/credits` 和 main.ts 中的 scrollBehavior。
- 新增文字中英齐全；不加载远程字体、图标库或原型 runtime，不让正式代码依赖 out/。
- 不覆盖工作区改动，不自动 commit/push/deploy，不读取或输出密钥，不改变 API/LLM/RAG/定价。
- 测试覆盖真实状态与导航风险，不增加纯 CSS 快照；行为测试通过不等同于视觉验收。

## Review Focus

1. `/albums/library`、`/credits`、`/result?day=2`：正确且唯一高亮，当前项重选不丢 day；归 Task 1。
2. 关闭抽屉、跨越断点、低高度与英文：焦点可恢复、滚动锁释放、内容不裁切；逻辑归 Task 2，实际画面归 Task 4。
3. 快速切页、未填完的表单、损坏存储、成功后的卸载：草稿不丢失、不污染已提交请求、不会被旧 timer 写回；归 Task 3。
4. SSE 运行/成功交接/fallback/错误：用户离开被正确约束，自动跳转和手动重试仍正常；归 Task 3。
5. 行程有未保存修改或正在导出：取消离开保留数据，导出完整且无侧栏，地图不因折叠重建；保护归 Task 3，视觉与文件验收归 Task 4。

## 文件与接口约定

当前真实路由定义位于 `frontend/src/main.ts`。新增文件只按下列职责拆分，不引入通用导航平台。

| 文件 | 对外接口 / 职责 |
| --- | --- |
| `frontend/src/data/navigation.ts` | 导出 `SideMenuRouteName = 'Home' \| 'AlbumWorkspace' \| 'Result' \| 'AlbumLibrary'`、`SideMenuIconName = 'plan' \| 'album' \| 'trip' \| 'library' \| 'collapse' \| 'expand'`、`SideMenuItem { routeName, labelKey, icon }` 与 `SIDE_MENU_GROUPS: { labelKey: string; items: SideMenuItem[] }[]` |
| `frontend/src/components/layout/SideMenuIcon.vue` | props `{ name: SideMenuIconName }`，统一装饰 SVG，无业务状态 |
| `frontend/src/components/layout/AppSideMenu.vue` | props `{ collapsed:boolean; mobile:boolean; blocked:boolean }`；emits `{ 'toggle-collapse': []; select: [routeName: SideMenuRouteName] }` |
| `frontend/src/composables/useSideMenu.ts` | `useSideMenu(): { collapsed: Ref<boolean>; isMobile: Ref<boolean>; drawerOpen: Ref<boolean>; toggleCollapsed():void; openDrawer():void; closeDrawer():void }`；浏览器监听和偏好存储 |
| `frontend/src/services/shellNavigation.ts` | `SHELL_NAVIGATION_BLOCKED: InjectionKey<Ref<boolean>>`；provider 在 App，Home/Result 可选注入 |
| `frontend/src/services/plannerDraft.ts` | `loadPlannerDraft(): PlannerDraft \| null`、`savePlannerDraft(draft: PlannerDraft): void`、`clearPlannerDraft(): void`；版本/结构校验与容错 |
| `frontend/src/views/AlbumWorkspace.vue`、`AlbumLibrary.vue` | 实现规格第 5 节，只有真实路由链接与诚实空态 |

草稿类型定义在 `plannerDraft.ts`：

```ts
type DraftParty = Omit<TripFormData['party'], 'total' | 'adults' | 'children' | 'elders'> & {
  adults: number | null
  children: number | null
  elders: number | null
}
type PlannerDraftForm = Pick<TripFormData,
  'city' | 'transportation' | 'accommodation' | 'preferences' | 'free_text_input'> & {
  start_date: string | null
  end_date: string | null
  party: DraftParty
  budget_constraint: Pick<TripFormData['budget_constraint'], 'amount' | 'budget_level'>
}
interface PlannerDraft {
  version: 1
  provinceCode: string | null
  form: PlannerDraftForm
  strictBudget: boolean
  optionsOpen: boolean
}
```

`total/travel_days/strictness` 是派生状态，不保存旧计算结果；清空人数的 UI 草稿可以为 null，转成真实请求时仍走现有合法性校验。不要用类型断言掩盖 null。

---

### Task 1: 书签导航内容、翻译与真实路由

**Files:**
- Create: `frontend/src/data/navigation.ts`
- Create: `frontend/src/components/layout/{AppSideMenu,SideMenuIcon}.vue`
- Create: `frontend/src/views/{AlbumWorkspace,AlbumLibrary}.vue`
- Modify: `frontend/src/main.ts`、`frontend/src/i18n/messages.ts`
- Test: `frontend/tests/AppSideMenu.test.ts`

**Interfaces:**
- Consumes: 现有 `useRoute()`、`RouterLink`、`t()`、theme token。
- Produces: 上表的菜单 props/emits 与常量；`AlbumWorkspace`、`AlbumLibrary` 两个命名路由。

- [ ] 写 `AppSideMenu.test.ts`，用 memory router 验证四个菜单路径、高亮唯一性；`/credits` 零高亮，`/result?day=2` 点击当前项仍是 day=2。
- [ ] 在同一测试中验证切换 locale 后中文、英文 label/aria 变化，`blocked=true` 不触发导航；折叠仍有完整名称。
- [ ] Run: `cd frontend && npm run test -- tests/AppSideMenu.test.ts`。初次应因组件/数据文件尚未实现而失败，排除测试环境自身错误。
- [ ] 按接口实现 metadata、图标和受控侧栏。链接负责导航，Vue Router 决定 active；书签装饰不影响点击/焦点。
- [ ] 在 main.ts 追加两个懒加载路由；实现规格第 5 节的占位页和完整中英文文案。
- [ ] 再运行针对性测试并 `npm run build`；期望测试通过且 Vue/TS 构建成功。

### Task 2: App 外壳、桌面折叠与手机抽屉

**Files:**
- Create: `frontend/src/composables/useSideMenu.ts`
- Create: `frontend/src/services/shellNavigation.ts`
- Modify: `frontend/src/App.vue`、`frontend/src/styles/base.css`
- Test: `frontend/tests/useSideMenu.test.ts`、`frontend/tests/AppShell.test.ts`

**Interfaces:**
- Consumes: Task 1 的 `AppSideMenu` 与 `select(routeName)`；现有 `routeTransition` 和 `clearRouteTransition()`。
- Produces: `useSideMenu()`、App 提供的 `SHELL_NAVIGATION_BLOCKED`；唯一 `main#main` 和原 RouterView 转场。

- [ ] 写 `useSideMenu.test.ts`，覆盖存储 true/false/坏值/抛错、匹配 `max-width:760px`、跨断点关闭 drawer 但不改 collapsed，以及卸载移除 listener。
- [ ] 写 `AppShell.test.ts`，用 memory router / matchMedia mock 验证四入口和中英切换、手机按钮的 aria-expanded、成功跳转才关闭抽屉、当前项关闭但不重置 query；不要把 jsdom 当作真正焦点锁验收。
- [ ] Run: `cd frontend && npm run test -- tests/useSideMenu.test.ts tests/AppShell.test.ts`；先确认所需行为失败。
- [ ] 实现 composable 与 InjectionKey；App 将旧 product-nav 替换为 desktop aside/mobile Ant Design Drawer，保留 config-provider、品牌、语言、skip-link、route transition 与 footer。
- [ ] 按规格配置 188/76px grid、局部 shell padding、移动抽屉及 z-index=600；视口切换/关闭/卸载释放资源；不要在 App 主区祖先加 transform/contain。
- [ ] App 根据 blocked 控制 header/sidebar/footer inert 与 drawer 关闭；watch 真实成功路由切换，区分普通导航与 day query 的焦点/滚动行为。
- [ ] 再运行两组测试，期望全部通过。实际 Tab、遮罩、英文排版和滚动锁列入 Task 4。

### Task 3: 草稿恢复、生成交接与离开保护

**Files:**
- Create: `frontend/src/services/plannerDraft.ts`
- Modify: `frontend/src/views/Home.vue`、`frontend/src/views/Result.vue`
- Test: `frontend/tests/plannerDraft.test.ts`
- Modify/Test: `frontend/tests/Home.integration.test.ts`
- Create/Test: `frontend/tests/Result.navigation.test.ts`

**Interfaces:**
- Consumes: Task 2 的 `SHELL_NAVIGATION_BLOCKED`；现有 `loadRequest/saveRequest`、`run.busy`、`run.state`、`navigate` 回调；Result 的 `originalPlan/editMode/exporting`。
- Produces: 上表草稿服务；普通跨页恢复未提交字段，成功交接恢复现有已提交请求；Home/Result 路由离开保护。

- [ ] 写草稿存储测试：往返省份/空日期/人数 null/预算 0/strict/options；损坏 JSON、错误版本、结构和日期被安全忽略；getItem/setItem/removeItem 抛错不影响页面。
- [ ] 扩展 Home 集成用例，挂载真正 RouterView 并增加相册目标：编辑后立即离开再返回，输入、手选同行类型、省份-only 和 strict/options 保留，`tripRequest` 未提前改写。
- [ ] 扩展受控 SSE 用例：运行中用户 router.push/back 不离开；success/fallback 仍只保存/跳转一次；成功清草稿且卸载不再写回；失败重试沿用输入。
- [ ] 写 Result 导航用例，使用受控 fixture 与地图/导出 mock：无编辑或没改变允许离开；有编辑取消后数据仍在、确认放弃不落盘；exporting 阻止离开；「修改条件」清草稿但不改已提交请求。
- [ ] Run: `cd frontend && npm run test -- tests/plannerDraft.test.ts tests/Home.integration.test.ts tests/Result.navigation.test.ts`；确认失败是行为缺失。
- [ ] 实现草稿服务及 Home 回填优先级。完成回填后再启动约 200ms 防抖保存，正常离开/卸载 flush、取消 timer；成功生成设置跳过再保存标记并清理草稿。
- [ ] Home 可选注入导航锁并同步 overlayOpen；通过只在现有 navigate 回调设置的一次性交接标志允许成功跳转，其余 busy 状态离开返回 false。保留旧 dispose、SSE 请求协议与转场。
- [ ] Result 在 exporting 时锁定导航，清理卸载状态；加入基于真实编辑差异的异步离开确认；不替换现有保存/撤销数据源。「修改条件」先清草稿再调用原 router.push('/')。
- [ ] 再运行针对性测试，期望全部通过；检查一次成功请求仍只触发一个 stream，不让旧延迟回调在另一页面导航。

### Task 4: 内容宽度适配、回归与画面验收

**Files:**
- Modify: `frontend/src/views/Home.vue`、`frontend/src/views/Result.vue`（必要布局 CSS）
- Conditional modify: `frontend/src/components/result/TripMap.vue`（仅容器变宽验证确有问题时增加 resize 监听）
- Read/verify: `frontend/src/components/result/{DayNavigation,ExportSheet}.vue`，现有 progress/overlay/useTripPlanRun 测试。

**Interfaces:**
- Consumes: 真实 App 外壳、独立 ExportSheet、现有高德实例生命周期。
- Produces: 可在真实页面审查的书签导航，及测试/build/截图证据。

- [ ] 将 Home/Result 在 761–1100px 改为单列；大屏间距收敛至约32px；<=760px 保留原手机内容顺序。所有网格/内容列 min-width:0，不能靠 overflow-x:hidden 隐藏错误。
- [ ] 在真实浏览器验证侧栏折叠引发的地图尺寸变化。若现有 Amap 行为足够则不改；否则添加有尺寸变化才调用的 ResizeObserver（不用重建实例），卸载 disconnect，并补充对应 observer 清理行为测试。
- [ ] Run: `cd frontend && npm run test`；期望全套通过，已有故障与本次故障分开报告。
- [ ] Run: `cd frontend && npm run build`；期望 vue-tsc 和 Vite 均成功。
- [ ] 使用现有服务/fixture，在 1440、1280、1024、768、760、390、320px 审查导航、结果页、空态与中英文；记录未覆盖的组合，不声称全部已测。
- [ ] 实际检查 Drawer 的 Tab/Shift+Tab、Escape、遮罩、焦点归还、跨断点和低高度；关闭后滚动恢复，背景不接受输入，reduced motion 正常。
- [ ] 用受控数据走 running → success/fallback → Result、error → 修改/重试；检查 overlay 全屏、不被侧栏盖住、自动交接保留、抽屉与进度层滚动锁不冲突。
- [ ] 检查真实保存/撤销、日期 query、前进后退、地图/天气/预算；打开导出的 PNG/PDF，确认全部日期在内且无 header/SideMenu。保留摄影来源和署名。
- [ ] 保存桌面展开、桌面折叠、手机抽屉截图至 `out/bookmark-sidemenu-review/`；最终报告实际可访问的前端 URL、变更文件、检查结果及未验证项。不要自动提交或部署。

## 完成判定

用户能在真实项目里使用书签式菜单切换四个页面，桌面可折叠、手机可抽屉访问；中文英文和键盘可用；切页不丢规划草稿，也不破坏生成交接、编辑、地图和完整导出。相册页面明确标注准备中，没有虚假业务状态。

本轮计划编写已核对代码结构并自行审阅；上述实现任务均未执行。方案不依赖先前临时预览服务一直在线。
