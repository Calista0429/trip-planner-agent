# 「相册书签」SideMenu：Claude Code 实现 Prompt

以下正文可直接交给 Claude Code。它同时是本次实现的设计规格；任务拆分见 `docs/superpowers/plans/2026-11-20-bookmark-sidemenu.md`。

---

请在仓库 `/Users/huangbaoxi/Code/Trip-planner-agent` 中实现「相册书签」风格的 SideMenu。用户已在五套方案中选定「相册书签」，请按本文直接实施，不重新提供风格选项，也不要停留在静态原型阶段。先核对代码，再按任务实施、验证并汇报。

## 1. 本次交付范围

将当前顶部的功能导航迁入左侧书签式导航，让用户能在旅行规划、旅行相册、我的行程、我的相册之间切换。保留 Trip Planner 品牌、顶部中英切换、真实规划流程与结果页。

本轮交付可用的导航框架、响应式布局、相册入口占位页，以及导航引入的必要状态保护。相册生成是下一阶段：本轮不实现照片上传、AI 文案、排版生成、相册存储、相册导出或相册后端接口，不添加虚假的成功提示和演示相册。

仅修改前端与必要文档。不得改变后端、LLM、LangGraph、RAG、预算/定价、训练或现有 API 协议。保留工作区已有未提交改动，尤其 `frontend/vite.config.ts`，不得覆盖、reset、清理或回滚他人的工作。不升级依赖、不引入新的 UI 框架、Pinia 或图标包，不自动提交、推送或部署。不要读取或输出真实 `.env` 和密钥。

## 2. 先阅读与核对

先读根目录 `AGENTS.md`、`CLAUDE.md` 及目标目录内适用的说明，然后读：

- `frontend/src/App.vue`
- `frontend/src/main.ts`：当前路由就在这个文件，不存在 `src/router/index.ts`。
- `frontend/src/styles/base.css`、`frontend/src/styles/theme.ts`
- `frontend/src/i18n/index.ts`、`frontend/src/i18n/messages.ts`
- `frontend/src/views/Home.vue`、`Result.vue`、`Credits.vue`
- `frontend/src/services/tripSession.ts`、`routeTransition.ts`
- `frontend/src/composables/useTripPlanRun.ts`
- `frontend/src/components/home/TripTransitionOverlay.vue`、`CameraCarousel.vue`
- `frontend/src/components/result/DayNavigation.vue`、`TripMap.vue`、`ExportSheet.vue`
- `frontend/tests/Home.integration.test.ts`、`useTripPlanRun.test.ts`、`TripTransitionOverlay.test.ts`
- `frontend/package.json`、`frontend/vitest.config.ts`

本地设计参照：

- `out/sidemenu-designs-20261119/trip-sidemenu-concepts.html`
- `out/sidemenu-designs-20261119/preview.html`
- `out/sidemenu-designs-20261119/design-notes.md`

重点查看 `data-variant="相册书签"`、`.tp-v3` 的侧栏、纸面底色、书签选中态、留白和字体。共享模板中的导航内容也需要阅读。可打开 `http://127.0.0.1:8767/preview.html`，从底部选择「相册书签」。服务不可用时，在独立终端运行：

```bash
cd /Users/huangbaoxi/Code/Trip-planner-agent
python3 -m http.server 8767 --bind 127.0.0.1 --directory out/sidemenu-designs-20261119
```

先检查端口是否已被占用，不终止未知进程。如果原型文件不存在，本文的尺寸、配色、结构和交互足以实现，不因此停止。原型只用于视觉对照；正式代码不能依赖 `out/`、`window.openai`、`Tweak`、轮播切换器、原生 DOM 页面拼接或原型内的 Base64 图片。

## 3. 视觉规格

这是旅行手记的目录与书签，整体安静、轻盈，沿用当前摄影与宋体气质。

| 项目 | 规格 |
| --- | --- |
| 页面纸面 | 复用 `--paper: #f6f7f5` |
| 侧栏纸页 | 新增 `--sidebar-paper: #eef0e8` |
| 主色 / 选中书签 | 复用 `--pine: #315348` |
| 主色 hover | 复用 `--pine-dark: #24403a` |
| 正文 | 复用 `--ink: #2a3d35` |
| 次要文字 / 分隔线 | 复用 `--muted: #6d7971`、`--line: #dce2dc` |
| 侧栏右边线 | `#c6d0c4` |
| 桌面展开 / 折叠宽度 | `188px / 76px` |
| 移动端抽屉宽度 | `min(280px, calc(100vw - 48px))` |
| 桌面 / 手机页头高度 | `84px / 64px`；允许英文或系统放大时内容自然撑高 |
| 导航行 | 最小高度 `48px`；字体 `14px`，中等字重；行间距 `6px` |
| 图标 | `18–20px`，统一线性风格、`currentColor` |
| 书签外伸 | 向右 `9px`，与选中行同高，中间浅 V 形缺口 |
| 侧栏内边距 | 顶部约 `28px`；左侧 `16px`；选中项延伸到右侧边线 |
| 内容区内边距 | 桌面 `32px`，移动端 `20px` |
| 动画 | hover / 书签反馈 `120–180ms`；折叠宽度直接切换，避免地图重排拖影；遵守 reduced motion |

标题与侧栏的「把远方，收进日常。」使用现有 `--serif`，两行、约 `23px`、正常字重；导航标签和操作使用 `--sans`。英文标语为 `Keep your journeys close.`，允许自然换行。不要引入远程字体。

选中态使用松绿底、白色文字和图标，配合字重与 `aria-current="page"`。书签尾部用 CSS 伪元素与 `clip-path` 实现，装饰不截获点击；不靠大阴影制造层次。hover 使用浅绿底，选中项 hover 仍保持白字。键盘 focus 清晰可见，不能与选中态混淆。

折叠时保留图标，隐藏分组、标语和底部副文案；链接保留完整可访问名称，并用现有 Ant Design Vue Tooltip 在 hover/focus 时提示名称。折叠状态的书签尾部缩至 `6px`。手机抽屉中的书签止于抽屉内侧，不能溢出遮罩或制造横向滚动。

保留原品牌 H 标识与 Trip Planner 字样。移除顶部旧的「首页 / 我的行程」导航，避免出现两套同级导航。不要加入头像、登录、积分、通知、搜索、社交、机票酒店预订或额外功能入口。

## 4. 信息架构与真实路由

```text
顶部：H Trip Planner                              中文 / EN
┌────────────────┬──────────────────────────────────┐
│ 把远方，        │                                  │
│ 收进日常。      │ 当前路由页面                      │
│                │                                  │
│ 旅行创作        │ 规划：现有 Home                   │
│  路线 旅行规划  │ 相册：新入口页                    │
│ ▰照片 旅行相册 ▷│ 行程：现有 Result                 │
│                │ 我的相册：新空态页                │
│ 我的旅行        │                                  │
│  地图 我的行程  │                                  │
│  书册 我的相册  │                                  │
│                │                                  │
│ 出发前，有计划。│                                  │
│ 归来后，有回忆。│                                  │
│ 收起侧栏        │ 页脚 / 摄影来源与许可             │
└────────────────┴──────────────────────────────────┘
```

| 分组 | 中文 / 英文 | 路径 | 路由名 | 页面 |
| --- | --- | --- | --- | --- |
| 旅行创作 / Create | 旅行规划 / Trip planner | `/` | `Home` | 现有 `Home.vue` |
| 旅行创作 / Create | 旅行相册 / Album studio | `/albums` | `AlbumWorkspace` | 新增 `AlbumWorkspace.vue` |
| 我的旅行 / My journeys | 我的行程 / My itinerary | `/result` | `Result` | 现有 `Result.vue` |
| 我的旅行 / My journeys | 我的相册 / My albums | `/albums/library` | `AlbumLibrary` | 新增 `AlbumLibrary.vue` |

保留 `/credits` / `Credits`，从页脚访问；此页面没有一级菜单选中。未来相册编辑详情页不在本轮添加。

使用 Vue Router 的真实 `RouterLink`，保留链接语义、键盘与新标签打开能力。精确按 route name 计算选中状态，不用 `startsWith('/albums')`，防止 `/albums/library` 同时高亮两个入口。普通页只有一项 `aria-current="page"`，`/credits` 为零项。`/result?day=2` 始终选中「我的行程」。已经处于 `/result` 时点击当前项应保留 query，不重置 `day`。

保留 `main.ts` 的现有路由和 `scrollBehavior`，直接在原 routes 数组追加两个相册路由，不为四个入口进行无关的路由目录重构。新页面可懒加载；不要改成原型的 `?view=...` 或通过手写 DOM 切页。

注意：当前 `tripSession.ts` 只保存一份最新计划，不是历史列表。保留「我的行程」原行为，有计划展示真实计划，无计划展示现有空态。不能填入杭州、大理样例，不能声称已有多份历史行程。

## 5. 相册入口页：明确预留、无虚假功能

`AlbumWorkspace.vue`：

- 宋体标题「让旅途，再翻一页。」；副文案「把照片与沿途故事，整理成一本旅行相册。」
- 显示明确状态「相册功能准备中」，并说明「照片上传、故事整理与相册生成将在后续开放。」
- 展示一个真实可用的文本链接「查看我的相册」到 `/albums/library`，以及「返回旅行规划」到 `/`。
- 不显示可点击但无效的上传/生成按钮；不进行 API 请求；不用设计原型的照片数量、完成状态或相册卡片。

`AlbumLibrary.vue`：

- 标题「我的相册」，空态「还没有旅行相册」。
- 说明「相册功能开放后，你的旅行作品会保存在这里。」
- 链接「了解旅行相册」到 `/albums`；不提供假列表、假计数、草稿筛选和不可用的创建按钮。

两页延续浅纸面、宋体标题、细分隔线与留白，只需一个适度的线性相册图标。新增全部可见文案与 aria/tooltip 文案必须中英齐全，加入现有 `messages.ts`；相应更新 `Messages` 类型。英文分别使用 `Turn your journey into an album.`、`Album features are coming soon.`、`My albums` 等自然表达。

## 6. 组件、布局与响应式

建议文件职责如下，按仓库现有实现进行最小调整：

| 文件 | 职责 |
| --- | --- |
| `src/components/layout/AppSideMenu.vue` | 书签式导航内容、分组、选中态、图标、折叠按钮 |
| `src/components/layout/SideMenuIcon.vue` | 四种轻量线性 SVG 图标及折叠图标；按现有 `SectionIcon.vue` 风格实现 |
| `src/data/navigation.ts` | 菜单分组、路由名、翻译 key、图标 id；不存翻译后的字符串 |
| `src/composables/useSideMenu.ts` | 折叠偏好、移动断点、抽屉状态与清理 |
| `src/services/shellNavigation.ts` | 提供导航暂时锁定的 typed InjectionKey，连接 App 与生成/导出页面 |
| `src/services/plannerDraft.ts` | 本标签页未提交表单草稿的读取、验证与写入 |
| `src/views/AlbumWorkspace.vue`、`AlbumLibrary.vue` | 两个真实可访问的相册占位路由 |
| `src/App.vue` | 保留全局配置、页头、主区、转场和页脚；组装侧栏与手机抽屉 |
| `src/main.ts` | 追加相册路由 |
| `src/i18n/messages.ts` | 新导航、抽屉、空态与必要提示的中英文 |
| `src/styles/base.css` | 少量侧栏公共 token；不批量覆盖 Ant Design 默认样式 |
| `src/views/Home.vue`、`Result.vue` | 内容宽度适配、草稿/离开保护、导航锁的必要接线 |

`AppSideMenu.vue` 使用受控 props：`collapsed: boolean`、`mobile: boolean`、`blocked: boolean`；emit `toggle-collapse` 与 `select(routeName: string)`。组件内部读取 route 和 i18n，不拥有另一份路由状态。`select` 只通知点击，不等于导航成功；路由跳转仍由 RouterLink 完成。

桌面 `>760px`：外层最大宽度沿用 `1360px`，主体为 `188px minmax(0, 1fr)` 的两列；折叠后第一列 `76px`。侧栏背景延伸至主体底部，导航内容 sticky 于 `top:16px`，长页滚动时仍可切换。顶部 header 保持现有非吸顶行为，避免新增遮挡；低高度窗口允许侧栏导航自身纵向滚动，底部折叠按钮不能被裁掉。

不要给整个页面新建滚动容器。保留浏览器文档滚动、结果页日期导航和地图 sticky 的预期行为。`.app-main` 必须 `min-width:0`。主内容里的 `.shell` 仅在 App 主区范围覆盖为 `width:100%; max-width:none; padding-inline:32px`，手机 `20px`；不影响顶部/页脚的 `.shell` 和离屏 ExportSheet。内层网格都使用 `minmax(0,1fr)`。

`761–1100px`：仍保留侧栏，但 Home 的表单/相机与 Result 的行程/地图改为上下布局，避免减去侧栏后仍被旧双栏断点挤压。`>1100px` 保留合理双栏并收敛原有 `76px/58px` 大间距至约 `32px`。`<=760px` 保留现有手机 Home 内容顺序与 Result 单列规则；不重排业务内容。

手机 `<=760px`：不占据侧栏宽度；header 左侧添加带可访问名称的菜单按钮。用现有 Ant Design Vue Drawer，`placement="left"`，宽度如上；抽屉内容复用 `AppSideMenu`，使用展开态，不显示折叠按钮。设置正确标题/aria、Escape、遮罩点击、关闭按钮、焦点约束与焦点归还。关闭抽屉后隐藏内容不能进入 Tab 顺序。不要只做一个可点击蒙层而缺失对键盘的支持。

折叠偏好保存在 `localStorage['tripPlanner.sidebarCollapsed.v1']`，仅接受 `'true'` / `'false'`，默认展开；读写失败仍可操作。手机抽屉状态仅存内存，不能保存为下次自动打开；跨越断点关闭抽屉并释放滚动锁，不修改桌面折叠偏好。移除 matchMedia 监听器。可使用现有组件的滚动/焦点能力，不另建通用状态框架。

路由成功切换后关闭手机抽屉，普通跨页面导航将焦点移至 `#main`；被取消的导航不能当作成功，不清空草稿。点击当前菜单项只关闭抽屉，焦点回菜单按钮。同一路由改变 day query 不强制滚动或抢焦点。自动生成完成的转场也不能被焦点处理破坏。

## 7. 防止导航带来功能回归

### 7.1 未提交规划表单

当前 Home 只从最后一次成功请求 `tripRequest` 回填。新增菜单后必须保留尚未提交的表单：编辑日期、预算和偏好 → 打开相册 → 返回规划，输入仍在。

采用独立 `sessionStorage['tripPlanner.formDraft.v1']`，不要提前覆盖 `tripRequest`、`tripPlan` 或 `tripPlanMeta`。草稿使用 `version:1`，包含省份选择、全部可编辑表单字段、日期（`YYYY-MM-DD` 或 null）、严格预算开关、更多选项展开状态。保存不完整输入，包括仅选省份、清空日期/金额/人数等状态，不把 0 当缺失；合计人数、天数等派生值按现有规则重新计算。

恢复优先级：有效草稿 → 原有已提交请求 → 当前默认值。读取时校验结构、已知字段和日期，非法/旧版本/损坏 JSON 不得导致页面崩溃；不盲目 `Object.assign` 不可信对象。恢复完成后再启用草稿写入，防止初始空表单覆盖草稿；日期与同行类型 watchers 不能破坏回填值。保存不触发表单校验或重复提示。

正常编辑做轻量合并/防抖写入（约 `200ms`），成功离开页面前和组件卸载前同步落盘，并取消待执行 timer，避免快速切页丢最后一次输入。存储失败本次内存仍能工作，不用阻塞性弹窗。新一次成功生成后清除本轮草稿，继续由已提交请求回填；成功导航卸载时不能把已清除的草稿重新写回。失败/取消导航保留草稿。

Result 的「修改条件」应明确恢复当前计划对应的 `tripRequest`：点击该按钮时先清理旧草稿，再回到 `/`；一般点击侧栏「旅行规划」则保留最新未提交草稿。这两种入口不要混淆。

不要用全局 KeepAlive 缓存所有页面来保留输入。`useTripPlanRun` 和 `CameraCarousel` 依赖卸载清理，Result 又有地图实例；默认维持现有卸载行为。

### 7.2 生成与导出期间

现有生成进度弹层是 `position:fixed; z-index:1000`，不要让新抽屉遮住它，也不要给它的祖先添加 transform/filter/contain 导致全屏弹层变成局部定位。

App 提供一个 `Ref<boolean>`，通过 `SHELL_NAVIGATION_BLOCKED` InjectionKey 供页面使用。Home 将 `overlayOpen` 同步进去，Result 将 `exporting` 同步进去；不要求独立挂载这些页面的旧测试必须提供它（允许无注入）。页面卸载时释放。App 在锁定期间关闭手机抽屉，让 header、SideMenu、footer 不可交互（`inert` + 合理禁用状态），但不能把包含进度弹层的整个 `main/app` 设为 inert。

手机 Drawer 的 z-index 设为 `600`，结果页离开确认使用 `900`，现有规划弹层保持 `1000`。Drawer 的滚动锁必须在关闭后释放，不能与生成弹层的滚动锁互相覆盖；优先复用 Ant Design 行为并实际验证。

Home 增加最小路由离开保护：运行中和成功/fallback 交接等待期不能被用户菜单/浏览器后退中断。只有 `useTripPlanRun` 注入的现有 `navigate()` 回调设置一次性内部交接标志后，允许它自动前往 `/result?day=1`，随后复位。不能简单拦截所有离开，否则会挡住正常成功跳转。错误态保留现有重试/返回修改行为，卸载继续调用已有 dispose，不修改服务端取消语义。

Result 导出期间阻止离开，等待现有导出完成；布局变化不得把侧栏、页头和遮罩截入 PNG/PDF。继续只截取既有 `.export-sheet`，导出全部日期，而不是当前日。

### 7.3 行程编辑与地图

Result 有未保存修改时，侧栏/后退离开应触发离开保护，选择「继续编辑」或「放弃修改并离开」。只在与 `originalPlan` 相比确有修改时提示，进入编辑但没改不提示；取消离开不得丢数据，放弃离开不得写入新计划。继续复用现有保存和撤销逻辑，不新增另一套编辑数据源。中英文提示都要提供。

保留 `?day=N`、前进后退、日期滚动位置、保存撤销、预算、天气、照片署名、地图图层与完整导出。侧栏展开/折叠使地图宽度改变时应正确重绘；先检查现有 Amap 对容器变化的处理，确有必要才在 `TripMap.vue` 添加 `ResizeObserver` 与卸载清理。不能每次折叠都重建地图、重取 POI 或重置用户选中的日期/图层。

## 8. 实现顺序与验证

按 `docs/superpowers/plans/2026-11-20-bookmark-sidemenu.md` 分步执行：菜单与路由 → App 桌面/手机外壳 → 草稿与导航保护 → 布局回归和浏览器验收。每步先确认相关行为的验证方式，再实现；为路由状态、草稿恢复和离开保护补必要行为测试，不写与样式实现逐行对应的快照测试。

使用现有 Vue Test Utils / Vitest / jsdom。需要覆盖：

- 四个入口真实跳转、唯一选中、`/credits` 无选中、`/result?day=2` 不被重置；相册两个入口不双选。
- 中文/英文即时切换，包括折叠 tooltip、aria 和占位页；英文不出现裁切。
- 折叠状态持久化、坏值与存储异常降级；手机 Drawer 关闭、断点切换、事件监听清理。
- 未提交字段离开再回来仍在；快速切页、损坏草稿、空值/0、手选同行类型、成功清理草稿，以及「修改条件」恢复当前已提交请求。
- 运行中离开被阻止；成功/fallback 仍保存一次并自动跳转一次；失败后可修改重试；不增加 stream 调用。
- 行程未保存修改时取消/放弃两条分支；仅进入编辑不提示；导出期间不离开。

从 `frontend/` 运行针对性测试，再运行：

```bash
npm run test
npm run build
```

测试失败需区分本次回归和已有问题，不删断言或跳过失败来伪造通过。不要为完成导航任务重跑训练或后端评测。

浏览器逐项验收，逻辑单测不能替代画面检查：

- 1440、1280、1024、768、760、390、320px，至少中文/英文各一次；折叠/展开与窄屏高度下无裁切，整页无横向溢出。
- 桌面展开/折叠、手机抽屉打开/关闭，书签形状、字体、纸面底色与第三套设计一致。
- 键盘 Tab / Shift+Tab / Enter / Escape，抽屉焦点约束、关闭后归还、当前项可访问名称；reduced motion。
- 所有真实路由直接访问和刷新；首页表单、相机、结果页日期/地图/预算/编辑/导出仍可用。
- 生成进度始终覆盖全屏；没有侧栏穿透或错误滚动锁；生成结束正常显示结果。
- 无计划时不编造内容；相册占位页不发送 API 请求，不显示假照片数量或成功状态。
- 实际检查 PNG/PDF 不含新侧栏且涵盖全部日期；地图宽度变化与 resize 不泄漏实例/监听。

先检查并复用现有开发服务，不假设旧会话端口还有效，不更改 Vite 代理或后端配置。若需要启动前端，可从 `frontend/` 运行 `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`；若端口被其他程序占用，报告并使用明确空闲端口。不要启动真实 LLM 请求来验证纯导航；使用现有受控 fixture 验证交接，真实联调是否完成必须如实说明。

## 9. 最终交付报告

给出改动文件与职责、能访问的本地前端链接、测试/build 的真实结果，以及桌面展开、桌面折叠、手机抽屉三类截图。明确说明「已完成书签式导航和相册入口；真实相册生成未在本轮实现」。若浏览器或外部服务不可用，分别列明哪些离线检查已通过、哪些视觉/联调尚未验证，不能把静态代码检查称作浏览器验收。
