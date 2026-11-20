# 旅行相册服务接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在 `/albums` 上传照片、选风格生成相册；生成的相册存在本浏览器，在 `/albums/library` 查看。

**Architecture:** FastAPI 新增 `/api/comic/upload`，校验后转发到独立的 comic-trip-agent（Quarkus），并把返回归一化。前端用 fetch 调它，结果写进 localStorage；两个相册页共用一个展示组件。

**Tech Stack:** FastAPI + httpx（后端，pytest + httpx.MockTransport）；Vue 3 + TS + Ant Design Vue 4（前端，Vitest + Vue Test Utils + jsdom）。

**Spec:** `docs/superpowers/specs/2026-11-20-album-service-design.md`

## Global Constraints

- 工作目录 `/Users/huangbaoxi/Code/Trip-planner-agent-album`，分支 `feat/album-service`。**不提交、不推送**（用户未要求）；本计划所有 Commit 步骤改为「不提交」。
- 不改 `~/Code/comic-trip-agent`；不读取或输出真实 `.env`；不调用 Gemini。
- 不升级/新增依赖；不加 UI 框架、Pinia、图标包；不改 LLM/RAG/定价/行程 API。
- 后端测试：`cd backend && /Users/huangbaoxi/Code/Trip-planner-agent/backend/.venv/bin/python -m pytest …`（借用主工作区 venv，不改它）。
- 前端：`cd frontend && npm run test`，`npm run build`（node_modules 是指向主工作区的软链）。
- 限制：最多 `10` 张；单张 `15 * 1024 * 1024` 字节；风格 `comic | watercolor-journal | retro-film | anime`，默认 `comic`；代理超时 `330s`（connect `10s`）。
- 本地存储键 `tripPlanner.albums.v1`，结构 `{version: 1, albums: Album[]}`，最多 `30` 本，新在前，`tripId` 去重。
- 保留 `#album-workspace-title`、`#album-library-title` 两个标题 id（`AppShell.test.ts` 依赖）；两个视图必须是单根元素（out-in 过渡）。
- 模型文字一律文本插值渲染，禁止 `v-html`。

## Review Focus

1. 上游 200 但图片地址全部非 http(s) → 不能返回空相册；应变成 502 `all_failed`，原因 `bad_image_url`（Task 1 测试）。
2. iPhone 的 `.heic` 等 `file.type` 为空或非 image/* → 选图时就被拒并提示，不进入列表（Task 3 测试）。
3. 两个标签页各生成一本 → 保存时重新读取存储再合并，不能用页面缓存覆盖另一本（Task 2 测试）。
4. localStorage 写满 / 不可用 → 结果照常展示，并提示「未能保存到本浏览器」（Task 2 返回值 + Task 3 测试）。
5. 打开 `?album=<已移除的 id>` → 显示「找不到这本相册」并能回到列表，不白屏（Task 4 测试）。

---

### Task 1: 后端代理 `/api/comic/upload`

**Files:**
- Create（从 `feat/comic-trip` 取来再改）：`backend/app/api/routes/comic.py`、`backend/tests/test_comic_route.py`
  - `git checkout feat/comic-trip -- backend/app/api/routes/comic.py backend/tests/test_comic_route.py`
- Modify：`backend/app/config.py`（`comic_service_url: str = ""`、`comic_service_timeout_seconds: float = 330.0`，带中文注释）、`backend/app/api/main.py`（include router，prefix `/api`）、`backend/.env.example`（末尾追加 `COMIC_SERVICE_URL=`、`COMIC_SERVICE_TIMEOUT_SECONDS=330` 与说明）

**Interfaces:**
- Produces（HTTP）：`POST /api/comic/upload`，multipart：`file`（0..n）、`style`（可选字符串）。
  - 200：`{tripId, title, style, pictures: [{imageUrl, description, location, pointsOfInterest}], failed: [{file, reason}]}`
  - 错误体 `{error: <code>, failed?: [...]}`；码：`comic_not_configured`(503)、`no_files`(400)、`too_many_files`(400)、`not_an_image`(400)、`unknown_style`(400)、`file_too_large`(413)、`all_failed`(502)、`comic_timeout`(504)、`comic_unavailable`(502)、`comic_failed`(502)。
- 模块常量：`MAX_FILES = 10`、`MAX_FILE_BYTES = 15 * 1024 * 1024`、`STYLES = ("comic", "watercolor-journal", "retro-film", "anime")`。

- [ ] **Step 1: 改写/新增测试**（保留原有用例，下列为新增或改动）
  - `test_success_is_reshaped_for_the_frontend`：上游返回加 `"style": "anime"`，期望体含 `"style": "anime"`。
  - `test_style_is_forwarded_and_defaults_to_comic`：不传 style → 上游 body 含 `name="style"` 且值 `comic`；传 `" Anime "` → 转发 `anime`。
  - `test_unknown_style_is_rejected_without_calling_upstream`：style=`oil` → 400 `{"error": "unknown_style"}`，`upstream.requests == []`。
  - `test_oversized_file_is_rejected_without_calling_upstream`：`b"x" * (MAX_FILE_BYTES + 1)` → 413 `{"error": "file_too_large"}`，无上游请求。
  - `test_no_files_is_rejected`：改为期望 400 `{"error": "no_files"}`。
  - `test_non_http_image_urls_become_failures`：上游两张图，一张 `javascript:alert(1)`、一张 https → 200，pictures 只剩 https 那张，failed 追加 `{"file": "", "reason": "bad_image_url"}`。
  - `test_all_image_urls_bad_is_all_failed`：唯一一张是 `data:` → 502 `{"error": "all_failed", "failed": [{"file": "", "reason": "bad_image_url"}]}`。
  - `test_upstream_unknown_style_maps_to_400`：上游 400 `{"error": "unknown_style", ...}` → 400 `{"error": "unknown_style"}`。
  - `test_router_is_mounted_under_api`：`from app.api.main import app`，`app.url_path_for` 或遍历 `app.routes` 找到 `/api/comic/upload`。

- [ ] **Step 2: 跑测试确认失败**
  Run: `cd backend && …/python -m pytest tests/test_comic_route.py -q`
  Expected: 新增用例 FAIL（style / size / url / no_files / 挂载），原有用例 PASS 或因 config 缺字段整体报错。

- [ ] **Step 3: 实现**
  - `upload_photos(file: List[UploadFile] | None = File(None), style: str | None = Form(None))`。校验顺序：配置 → 数量 → MIME → 风格（`strip().lower()`，空 → `comic`）→ 逐个 `await f.read()` 检查大小。
  - 转发 `data={"style": style}` + `files=parts`。
  - `_picture` 之后按 `urlparse(url).scheme in ("http", "https")` 过滤，不合格的记为 `{"file": "", "reason": "bad_image_url"}`；过滤后为空 → 502 `all_failed`。
  - 上游 400 且 `error == "unknown_style"` → 400 `unknown_style`。

- [ ] **Step 4: 跑测试确认通过**
  Run: `cd backend && …/python -m pytest tests/test_comic_route.py tests/test_trip_route.py -q`
  Expected: 全部 PASS。

- [ ] **Step 5: 不提交**

### Task 2: 前端数据层（类型 / 接口 / 本地相册库 / 周边景点解析）

**Files:**
- Modify：`frontend/src/types/index.ts`、`frontend/src/services/api.ts`
- Create：`frontend/src/services/albumLibrary.ts`、`frontend/src/utils/pointsOfInterest.ts`（取自 `feat/comic-trip:frontend/src/utils/comic.ts`，改名）
- Test：`frontend/tests/albumApi.test.ts`、`frontend/tests/albumLibrary.test.ts`、`frontend/tests/pointsOfInterest.test.ts`（用例可取自 `feat/comic-trip:frontend/tests/comic.test.ts` 的解析部分）

**Interfaces:**
- Produces（types）：
  ```ts
  export type AlbumStyle = 'comic' | 'watercolor-journal' | 'retro-film' | 'anime'
  export const ALBUM_STYLES: AlbumStyle[]   // 上述顺序
  export interface AlbumPicture { imageUrl: string; description: string; location: string; pointsOfInterest: string }
  export interface AlbumFailure { file: string; reason: string }
  export interface Album { tripId: string; title: string; style: AlbumStyle; pictures: AlbumPicture[]; failed: AlbumFailure[]; createdAt: string /* ISO */ }
  ```
- Produces（api.ts）：`MAX_ALBUM_PHOTOS = 10`、`MAX_ALBUM_PHOTO_BYTES = 15 * 1024 * 1024`、`class AlbumUploadError extends Error { code: string; failed: AlbumFailure[] }`、`uploadAlbumPhotos(files: File[], style: AlbumStyle): Promise<Album>`（`createdAt` 由前端填 `new Date().toISOString()`；fetch 抛错 → code `network`；非 2xx → body.error 或 `comic_failed`）。
- Produces（albumLibrary.ts）：`ALBUM_LIBRARY_KEY = 'tripPlanner.albums.v1'`、`MAX_SAVED_ALBUMS = 30`、`loadAlbums(): Album[]`、`getAlbum(tripId: string): Album | null`、`saveAlbum(album: Album): boolean`（成功 true，存储异常 false）、`removeAlbum(tripId: string): void`。
- Produces（pointsOfInterest.ts）：`interface PointOfInterest { name: string; note: string }`、`parsePointsOfInterest(text: string): PointOfInterest[]`。

- [ ] **Step 1: 写失败测试**
  - albumApi：发送 FormData 含每个 `file` 和 `style`；URL 为 `${API_BASE_URL}/api/comic/upload`；200 → Album 带 `createdAt`；502 `{error:'all_failed', failed:[…]}` → `AlbumUploadError` code/failed；fetch reject → code `network`；非 JSON 500 → `comic_failed`。
  - albumLibrary：空存储 → `[]`；保存后 `loadAlbums()[0]` 是它；同 tripId 再存只有一本且在最前；存 31 本只留 30 本（最旧的被丢）；坏 JSON / version≠1 / 条目缺字段或 style 未知或 imageUrl 非 http(s) → 丢弃坏条目、保留好条目；`removeAlbum` 后 `getAlbum` 为 null；**并发**：直接往 localStorage 写入另一本后再 `saveAlbum`，两本都在；`setItem` 抛错 → `saveAlbum` 返回 false 且不抛；`getItem` 抛错 → `loadAlbums()` 为 `[]`。
  - pointsOfInterest：`- **Galata Bridge**: views` → `{name:'Galata Bridge', note:'views'}`；`* Name：中文冒号说明`；`[label](https://x)` 去链接；非列表行跳过；空串 → `[]`。

- [ ] **Step 2: 跑测试确认失败**
  Run: `cd frontend && npx vitest run tests/albumApi.test.ts tests/albumLibrary.test.ts tests/pointsOfInterest.test.ts`
  Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现上述签名**。albumLibrary 每次写前都重新 `read()`；校验函数与 `plannerDraft.ts` 同风格（逐字段、宽进严出）。

- [ ] **Step 4: 跑测试确认通过**（同上命令 → PASS），再跑 `npm run test` 全量 PASS。

- [ ] **Step 5: 不提交**

### Task 3: 展示组件 `AlbumView` + 生成页 `/albums`

**Files:**
- Create：`frontend/src/components/album/AlbumView.vue`、`frontend/src/utils/albumMessages.ts`
- Modify：`frontend/src/views/AlbumWorkspace.vue`（整页重写，单根 `<section class="shell album-page" aria-labelledby="album-workspace-title">`）、`frontend/src/i18n/messages.ts`（`album` 段 zh/en 扩充）
- Test：`frontend/tests/AlbumWorkspace.test.ts`

**Interfaces:**
- Consumes：Task 2 全部；`useShellNavigationLock(source)`（`@/services/shellNavigation`）；`onBeforeRouteLeave`。
- Produces：`AlbumView` props `{ album: Album; headingLevel?: 2 | 3 }`，渲染 `.album-view`、每张 `.album-picture`（`<img :src="imageUrl" :alt="location || title" loading="lazy">`、地点、描述、`parsePointsOfInterest` 列表）。`albumMessages.ts`：`albumErrorText(code: string): string`、`albumReasonText(reason: string): string`、`albumStyleLabel(style: AlbumStyle): string`（未知码回退到通用文案）。
- i18n 键（`album.*`，zh/en 都要）：`styleLabel, style_comic, style_watercolor-journal, style_retro-film, style_anime, pickPhotos, addMore, removePhoto, photoCount, generate, generating, generatingDesc, rejectedType, rejectedSize, rejectedCount, resultTitle, partialFailed, savedLocal, saveFailed, openInLibrary, again, err_<code>`（每个后端错误码 + `network`）、`reason_<reason>`（`timeout, no_image, billing, rate_limited, model_error, internal, bad_image_url`）、`leaveBusy`。删除不再使用的 `status/statusDesc`（若 Library 也不用）。

- [ ] **Step 1: 写失败测试**（mount 带 router + Antd；`uploadAlbumPhotos` 用 `vi.mock('@/services/api')`，`URL.createObjectURL/revokeObjectURL` stub）
  - 选 2 张图 → 出现 2 个缩略图；移除一张 → 剩 1 张，并 revoke 其 URL。
  - 选 `.heic`（type `''`）和 `text/plain` → 不加入，出现 `rejectedType` 提示；超 15MB → `rejectedSize`；第 11 张 → `rejectedCount`，列表保持 10 张。
  - 再次选择同一文件仍能触发（input 的 value 被清空）。
  - 未选图时「生成」按钮 disabled。
  - 生成：调用 `uploadAlbumPhotos(files, 'watercolor-journal')`；进行中按钮 `aria-busy="true"`、遮罩可见、shell lock 为 true（提供 `SHELL_NAVIGATION_BLOCKED` ref 检查）、`router.push('/')` 被拦（仍在 `/albums`）。
  - 成功：渲染 `AlbumView`（标题、图片 src），`loadAlbums()` 含该 tripId，出现「在我的相册中查看」链接到 `/albums/library?album=<id>`；有 failed 时列出文件名与 `reason_*` 文案。
  - `saveAlbum` 返回 false（mock localStorage.setItem 抛错）→ 结果仍显示，并显示 `saveFailed`。
  - 失败 `AlbumUploadError('comic_timeout')` → 显示 `err_comic_timeout` 文案，已选照片保留，可再试；lock 释放。
  - 卸载时 revoke 所有缩略图 URL。
  - 无 `v-html`：`AlbumView` 用 `<b>x</b>` 描述 → `text()` 含字面 `<b>`，DOM 中无 `b` 元素。

- [ ] **Step 2: 跑测试确认失败**
  Run: `cd frontend && npx vitest run tests/AlbumWorkspace.test.ts` → FAIL。

- [ ] **Step 3: 实现**。照片用隐藏 `<input type="file" accept="image/*" multiple>` + 可见按钮；风格用 `a-radio-group`（button 风格）；生成中遮罩沿用 Home 的思路（`role="status"`，文案说明可能需要几分钟）；样式沿用 `AlbumPlaceholder.vue` 的 serif 标题 / pine 色 / 细线，760px 以下单列。

- [ ] **Step 4: 跑测试确认通过**；`npm run test` 全量（含 `AppShell.test.ts` 的相册页导航用例）PASS。

- [ ] **Step 5: 不提交**

### Task 4: 「我的相册」`/albums/library` + 验收

**Files:**
- Modify：`frontend/src/views/AlbumLibrary.vue`（重写，单根 `<section class="shell album-page" aria-labelledby="album-library-title">`）、`frontend/src/i18n/messages.ts`、`frontend/src/main.ts`（更新那行"尚未实现"注释）
- Delete：`frontend/src/components/album/AlbumPlaceholder.vue`（若已无引用）
- Test：`frontend/tests/AlbumLibrary.test.ts`

**Interfaces:**
- Consumes：`loadAlbums/getAlbum/removeAlbum`、`AlbumView`、`albumStyleLabel`。
- i18n 新键：`libraryIntro, libraryLocalNote, libraryEmpty, libraryEmptyDesc, toWorkspace, pictureCount, openAlbum, backToLibrary, notFound, notFoundDesc, removeLocal, removeConfirmTitle, removeConfirmDesc, removeConfirmOk, cancel`。

- [ ] **Step 1: 写失败测试**
  - 空存储 → 空态文案 + 链接 `/albums`。
  - 两本 → 两张卡片，新的在前；卡片显示封面 `img` src = 第一张 imageUrl、标题、风格名、日期（按当前 locale 格式化）、张数。
  - 点卡片 → 路由变 `/albums/library?album=<id>`，渲染 `AlbumView`，有「返回我的相册」。
  - 直接打开 `?album=missing` → `notFound` 文案 + 返回链接。
  - 「从本浏览器移除」→ Modal.confirm（取最新 `.ant-modal-confirm`）确定后：`getAlbum` 为 null，回到列表；取消则保留。确认框说明服务器副本仍在。
  - 页面常驻 `libraryLocalNote`（只显示本浏览器生成的相册）。

- [ ] **Step 2: 跑测试确认失败** → `npx vitest run tests/AlbumLibrary.test.ts` FAIL。

- [ ] **Step 3: 实现**。列表用 CSS grid（`repeat(auto-fill, minmax(220px, 1fr))`）；详情由 `route.query.album` 计算，不新增路由名（侧栏选中项保持「我的相册」）。

- [ ] **Step 4: 全量验证**
  - `cd frontend && npm run test` → 全 PASS；`npm run build` → 成功。
  - `cd backend && …/python -m pytest tests/test_comic_route.py tests/test_trip_route.py -q` → PASS。
  - 浏览器验收（Playwright + 缓存 Chromium，见上一轮 `accept.cjs` 的启动方式；`page.route('**/api/comic/upload')` 返回模拟结果，图片用本地 data 生成的 PNG 由 `page.route` 提供 https 地址）：zh/en × 1440 / 390 宽：上传 3 张 → 生成中遮罩与侧栏锁 → 结果 → 我的相册列表 → 详情 → 移除；部分失败与 `comic_timeout` 各一次；无横向溢出；截图存 `out/album-service-review/`（主工作区路径）。

- [ ] **Step 5: 不提交**
