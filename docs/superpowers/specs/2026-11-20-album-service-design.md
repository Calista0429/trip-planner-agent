# 旅行相册服务接入 — 设计

日期：2026-11-20 · 状态：已确认（用户 2026-11-20 回复「确认」）

## 意图

侧栏里的「旅行相册」「我的相册」目前是占位页。把独立部署的相册服务
`~/Code/comic-trip-agent`（Java/Quarkus + Gemini，图存 GCS，元数据存 Firestore）
接进来：用户上传照片、选风格，生成一本相册；生成过的相册在「我的相册」里可以再看。

## 目标

- `/albums`：选照片（最多 10 张、仅图片、单张 ≤ 15MB）、选风格（comic /
  watercolor-journal / retro-film / anime，默认 comic），生成相册并在页面上展示结果。
- `/albums/library`：列出**本浏览器**里保存过的相册；`?album=<id>` 打开详情。
- 后端 `POST /api/comic/upload` 代理到相册服务，前端只认识本项目后端。

## 非目标

- 不改 `comic-trip-agent` 仓库（它没有列表 JSON 接口，用户选择只存浏览器）。
- 不从相册服务删除相册；「移除」只删浏览器记录。
- 不跨页面保留已选照片（浏览器无法持久化 File）。
- 不做行程结果页 →「为这次行程生成相册」入口。
- 不升级依赖、不加 UI 框架 / Pinia / 图标包；不改 LLM/RAG/定价逻辑。

## 反目标（即使能跑也算失败）

- 非法请求（超量、非图片、超大、未知风格）仍然打到相册服务、产生 Gemini 费用。
- 模型生成的文字被当 HTML 渲染；非 http(s) 的图片地址进到 `<img src>`。
- 生成中可以通过侧栏 / 后退离开页面，丢掉一个几分钟的请求而用户不知道。
- localStorage 里一条坏数据让「我的相册」整页崩溃。

## 方案（已选：A）

- **A. 本项目后端代理（选定）**：复用 `feat/comic-trip` 已有并有测试的
  `backend/app/api/routes/comic.py`，补 `style`。前端同源、无密钥、错误只见短码。
- B. 前端直连 Quarkus：需要 CORS、暴露服务地址、拿到上游原始报错文本。否决。
- C. iframe / 跳转到相册服务自带页面：与侧栏风格割裂、拿不到结果存本地。否决。

「我的相册」数据来源，用户在三项中选择了「只保存在浏览器里」（另两项：给相册服务
加只读接口；本轮不做）。

## 设计

### 后端（`backend/app/api/routes/comic.py`）

- 配置：`COMIC_SERVICE_URL`（空 → 503 `comic_not_configured`），
  `COMIC_SERVICE_TIMEOUT_SECONDS=330`（上游每张 240s、HTTP 300s，代理要更长）。
- 表单：`file`（多个）+ `style`（可选）。校验顺序：配置 → 数量（0 → 400
  `no_files`，>10 → 400 `too_many_files`）→ 类型（400 `not_an_image`）→ 风格
  （400 `unknown_style`）→ 读文件时逐个检查大小（>15MB → 413 `file_too_large`）。
  全部通过后才发起上游请求。
- 上游返回 200 → 归一化为
  `{tripId, title, style, pictures:[{imageUrl, description, location, pointsOfInterest}], failed:[{file, reason}]}`；
  `imageUrl` 不是 http(s) 的图片丢弃。上游 502 `all_failed` → 透传 failed；
  上游 400 `unknown_style` → 400；超时 → 504 `comic_timeout`；连不上 → 502
  `comic_unavailable`；其它 → 502 `comic_failed`（上游文本只进日志）。

### 前端

- `types/index.ts`：`AlbumStyle`、`AlbumPicture`、`AlbumFailure`、`Album`（含 `createdAt`）。
- `services/api.ts`：`uploadAlbumPhotos(files, style)`，fetch（无自带超时），
  失败抛 `AlbumUploadError(code, failed)`。
- `services/albumLibrary.ts`：`localStorage['tripPlanner.albums.v1']`，
  `{version:1, albums:[...]}`；逐字段严格校验，坏条目丢弃；最多 30 本，新在前，
  同 `tripId` 去重；读写异常吞掉。
- `utils/pointsOfInterest.ts`：把模型的 Markdown 列表解析成 `{name, note}` 纯文本。
- `components/album/AlbumView.vue`：展示一本相册（标题、风格、每张图 + 地点 +
  描述 + 周边景点），生成结果页与详情页共用。
- `views/AlbumWorkspace.vue`：选图（缩略图 + 移除，`URL.createObjectURL`，卸载时
  revoke）、风格单选、生成按钮；生成中全屏遮罩 + `useShellNavigationLock` +
  离开守卫；结果用 `AlbumView`，部分失败列出文件与原因；成功即存入本地。
- `views/AlbumLibrary.vue`：空态（链接去生成）、卡片网格（封面、标题、风格、日期、
  张数）；`?album=` 详情（找不到 → 提示并返回列表），「从本浏览器移除」需确认，
  并写明服务器上的副本仍在。
- i18n：zh / en 全量；错误码 → 文案映射。

## 约束

- 代码在 `feat/album-service` 工作目录（从 `main` 切出），不碰用户当前工作区。
- 不自动提交 / 推送。不读取或输出真实 `.env`。
- 验收全用模拟上游 / Playwright 路由拦截，不调用 Gemini。

## 交给实现者决定的

- 页面具体排版与动效，沿用现有 A2 设计语言（serif 标题、pine 色、细线）。
- 错误文案措辞。
