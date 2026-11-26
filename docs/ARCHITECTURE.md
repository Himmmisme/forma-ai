# 技术架构

浏览器使用 React 和 TypeScript。FastAPI 提供 REST 接口，并在生产环境提供构建后的静态页面。SQLite 用于本地开发和快速测试，Docker Compose 使用 PostgreSQL。Alembic 负责迁移。本地文件卷存放图片、备份和实例密钥。

采用同源、单 Web 服务和持久化数据库任务表，局域网部署仅需要应用和数据库两个容器。数据库事务记录任务状态、检查幂等键和分配版本号。独立执行线程运行耗时任务，HTTP 接口提交后即返回，页面轮询状态。后端以租约识别中断任务，生成请求可能已计费时交给用户确认重试。

UI 使用自有 CSS 设计变量和可复用组件，Lucide 提供应用图标。这样可以统一中文排版和深浅色，并减少样式工具链。密码采用 Argon2id，服务端会话使用随机令牌和 HttpOnly Cookie，密钥由独立卷中的 Fernet 密钥加密。

适配器面向真实模型能力进行配置。已查阅 [OpenAI 图片生成](https://developers.openai.com/api/docs/guides/image-generation)、[OpenAI 视觉输入](https://developers.openai.com/api/docs/guides/images-vision)、[Gemini 图片生成](https://ai.google.dev/gemini-api/docs/image-generation)及 [Gemini REST](https://ai.google.dev/api/generate-content)。业务流程可以使用内置 Mock 本地验收。

OpenAI 官方文本与视觉走 Responses，图片工作台将多角度素材传给 Images Edits。兼容协议使用 Chat Completions 和 Images，具体支持范围由能力测试确认。Gemini 使用 generateContent 的 inlineData 和 generationConfig，每个输出发起一次调用。管理后台由部署者填写已开通的模型 ID。参见 [OpenAI Images Edits](https://developers.openai.com/api/reference/resources/images/methods/edit/)和 [Gemini GenerateContent](https://aistudio.google.com/api-reference/generate-content/generate-content)。

VX API 的指定图片型号使用其文档中的同步 Images 请求。历史 GPT 图像型号只提供文生图测试，带原图的任务可选 VX 已验证的 Gemini 图像型号。该网关的单图编辑使用 `image` 表单字段，返回 `succeeded` 和图片数据后才接收结果。[VX API 接入文档](https://la-api.vxvxvx.top/manual/vx-api.html)

外部请求仅使用 HTTPS，禁用重定向和系统代理。解析到的地址均须为公网地址，连接固定在已验证的 IP，并用原始域名验证 TLS。预签名图片地址按相同规则访问，下载请求不携带服务商凭据。

任务执行器在单个 Web 进程内运行，PostgreSQL 队列取用行锁及 `SKIP LOCKED`；并发按全局槽位和服务商设置限制。执行线程每 8 秒更新租约，40 秒未更新的运行任务可标记为中断。计划内停机等待执行线程，上游接收情况不明时保留调用记录并由用户重试。SQLite 是本地单进程模式。

备份从一致性读快照提取业务表，图片对象不可变且在事务提交前写入。备份将清单与已校验的图片打包，独立保管凭据解密密钥。恢复到空实例保留账号和所有业务记录，登录会话由应用重新创建。
