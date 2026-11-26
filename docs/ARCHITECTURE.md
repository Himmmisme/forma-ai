# 技术架构

浏览器使用 React 和 TypeScript。FastAPI 提供 REST 接口，并在生产环境提供构建后的静态页面。SQLite 用于本地开发和快速测试，Docker Compose 使用 PostgreSQL。Alembic 负责迁移。本地文件卷存放图片、备份和实例密钥。

采用同源、单 Web 服务和持久化数据库任务表，局域网部署仅需要应用和数据库两个容器。数据库事务记录任务状态、检查幂等键和分配版本号。独立执行线程运行耗时任务，HTTP 接口提交后即返回，页面轮询状态。后端以租约识别中断任务，生成请求可能已计费时交给用户确认重试。

UI 使用自有 CSS 设计变量和可复用组件，Lucide 提供应用图标。这样可以统一中文排版和深浅色，并减少样式工具链。密码采用 Argon2id，服务端会话使用随机令牌和 HttpOnly Cookie，密钥由独立卷中的 Fernet 密钥加密。

适配器面向真实模型能力进行配置。已查阅 [OpenAI 图片生成](https://developers.openai.com/api/docs/guides/image-generation)、[OpenAI 视觉输入](https://developers.openai.com/api/docs/guides/images-vision)、[Gemini 图片生成](https://ai.google.dev/gemini-api/docs/image-generation)及 [Gemini REST](https://ai.google.dev/api/generate-content)。业务流程可以使用内置 Mock 本地验收。
