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
