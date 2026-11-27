# 业务 API

API 使用同源 JSON、Cookie 会话及后台权限校验。修改请求带 `X-Forma-Action: 1`，上传和导入使用 multipart。项目、图片内容和任务都有独立访问校验。

| 资源 | 路径前缀 |
| --- | --- |
| 登录、初始化、个人账户 | `/api/auth` |
| 项目、导出、素材、设计版本 | `/api/projects`、`/api/assets` |
| 模型能力、模板和提示词 | `/api/design` |
| 异步任务与重试 | `/api/jobs` |
| 材料与成本方案 | `/api/versions` |
| 账户、API、提示词、价格库及系统 | `/api/admin` |

业务错误使用可阅读的 `detail`。新任务携带幂等键。文件以身份认证请求读取。在线路由详情由 FastAPI OpenAPI 提供。

以下路径以 `/api` 开头。应用提供 `GET /api/openapi.json`。

| 路径 | HTTP 方法与行为 |
| --- | --- |
| `/health` | GET 检查应用与数据库连接 |
| `/auth/setup` | GET 初始化状态，POST 验证令牌并创建首个超管 |
| `/auth/login`、`/auth/logout` | POST 登录或撤销会话 |
| `/auth/me`、`/auth/password` | GET / PATCH 本人资料，POST 修改密码 |
| `/dashboard` | GET 本人汇总 |
| `/projects`、`/projects/demo` | GET 搜索、收藏与状态分页，POST 创建项目或载入示例 |
| `/projects/{id}`、`/projects/{id}/restore` | GET 详情，PATCH 基本信息和状态，DELETE 移入回收站，POST 恢复 |
| `/projects/{id}/assets` | GET 素材列表，POST multipart 单文件上传，`kind` 为 original、reference 或 cover |
| `/assets/{id}/content`、`/assets/{id}` | GET 预览，添加 `download=true` 下载，DELETE 移除输入 |
| `/design/catalog` | GET 可用模板、模型、输出规格和默认模型 |
| `/projects/{id}/preview`、`/projects/{id}/generate` | POST 预览提示词或入队生成，携带 `parent_id` 进入修改任务 |
| `/projects/{id}/optimize`、`/projects/{id}/inspect` | POST 需求优化或原图理解 |
| `/projects/{id}/jobs`、`/jobs/{id}`、`/jobs/{id}/retry` | GET 任务和请求记录，POST 重试 |
| `/projects/{id}/versions`、`/versions/{id}` | GET 版本列表或完整记录，PATCH 收藏 |
| `/projects/{id}/comparison-options`、`/favorites` | GET 比较数据或收藏成果 |
| `/projects/{id}/export` | GET 项目 ZIP。项目中的任务完成后可下载 |
| `/versions/{id}/analysis` | GET 材料、成本及任务，POST 入队分析 |
| `/versions/{id}/materials`、`/versions/{id}/materials/{plan}` | POST 新方案，PUT 编辑方案 |
| `/versions/{id}/costs`、`/versions/{id}/costs/{plan}`、`/versions/{id}/costs/calculate` | POST 保存或预计算、PUT 更新重算 |
| `/material-prices` | GET 按材料、牌号或供应商搜索报价 |
| `/admin/users`、`/admin/users/{id}`、`/admin/users/{id}/password` | GET / POST 创建与查询、PATCH 管理、POST 重置 |
| `/admin/catalog`、`/admin/providers`、`/admin/models`、`/admin/bindings/{task}` | 超管查看、创建或修改配置，PUT 更新指定默认模型 |
| `/admin/providers/{id}/test`、`/admin/models/{id}/test` | POST 入队连接或能力测试 |
| `/admin/templates`、`/admin/templates/{id}` | GET 列表、POST 创建方向、PUT 更新模板 |
| `/admin/prices`、`/admin/prices/{id}`、`/admin/prices/import`、`/admin/prices/export` | POST / PUT 保存、POST 导入 .xlsx、GET 导出或模板 |
| `/admin/system`、`/admin/audit`、`/admin/calls` | GET / PUT 设置，GET 操作和 API 调用记录 |
| `/admin/backups`、`/admin/backups/{id}/download` | GET 列表、POST 创建完整快照、GET 下载 |

超管保存 Gemini API 或 OpenAI Compatible 服务商时，`base_url` 支持 HTTP 接口前缀和自定义端口。Gemini API 留空时使用官方地址，自定义地址只有主机和端口时使用 `/v1beta`。HTTP 服务的 `api_key` 可省略。连接与任务调用时，公网域名必须解析为公网地址，本地 HTTP 域名必须解析为回环或私有 IPv4 地址。图片下载地址使用标准端口的公网 HTTPS。

`request_key` 由客户端生成。相同任务种类和幂等键仅接受同一组业务参数。提交返回任务 ID，状态为 queued、running、succeeded 或 failed。发送设计输入给外部服务须提供 `ack_external`，已知提示词冲突须提供 `ack_conflicts`。普通用户请求他人项目、素材和版本时返回 404。

分支修改同时使用父版本成果和产品原图。`edit` 默认模型须支持 `image_edit`、`multi_image`，且允许至少两张输入图。VX API 的已适配单图型号可用于图片编辑能力测试和单张原图的首轮生成。历史 GPT 文生图型号只可执行图片生成能力测试。模型配置示例见 [Windows 局域网部署](DEPLOYMENT.md#vx-api-图片模型)。

任务响应的 `model_code` 来自提交时的模型快照。图片任务重试沿用该快照。原型号、服务商地址或图片能力失效时，重试返回 409，可按当前工作台设置创建新任务。
