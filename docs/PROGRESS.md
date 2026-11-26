# 开发进度

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| 1 | 产品需求、架构、数据模型、基础界面 | 已验证 SQLite 初始化迁移及重复升级，1 项测试通过，TypeScript 和 Vite 构建通过 |
| 2 | 账号权限、项目、文件、管理框架 | 4 项测试在 SQLite 和 Windows PostgreSQL 17 分别通过，包含跨账号图片读取和密码重置；前端构建通过 |
| 3 | 服务商、模板、优化和生成任务 | SQLite 和 PostgreSQL 各 9 项测试通过，覆盖 Mock 生成、优化、幂等、密钥加密及三类请求契约；前端构建通过 |
| 4 | 迭代、版本分支、比较、收藏 | SQLite 和 PostgreSQL 各 11 项测试通过，覆盖多图独立版本、分支、重试、快照和 ZIP 导出；前端构建通过 |
| 5 | 材料建议、价格、BOM、成本 | SQLite 和 PostgreSQL 各 13 项测试通过，覆盖选型方案、报价优先级、BOM、缺项、权限与 Excel；前端构建通过 |
| 6 | UI 完善、异常处理、安全和自动化验收 | SQLite 和 PostgreSQL 各 15 项测试通过；Chromium 2 项端到端通过；npm 与 Python 运行依赖审计未报告已知漏洞 |
| 7 | Docker、Windows 局域网、备份恢复与交付 | 已实现并验证 SQLite / PostgreSQL 整站恢复、原生 Windows 内网入口及进程重启。Compose 配置校验通过，容器启动因引擎缺失待验收 |

从空工作区初始化。开发验证使用 Windows 便携 Git、Node.js、Python 与 PostgreSQL。真实 API 密钥由部署者配置。

最终验收包含 SQLite 与 PostgreSQL 各 17 项后端测试和 Chromium、WebKit 各 2 项端到端测试。完整报告见 [测试与验收](TEST.md)。

阶段 3 兼容性补充（2026-11-26）。接入 VX API 文档中的同步文生图和单张原图编辑请求，并校验图片任务终态。SQLite 19 项测试通过，Ruff 检查及前端生产构建通过。真实 VX 出图仍需操作者确认后验证。

部署阶段在 Windows 主机上执行了 Compose 配置检查和启动尝试。当前没有可用的 Docker 引擎。启用 Docker 的主机需补做容器启动、跨设备局域网连接和容器重启验收。真实服务需等待部署者配置凭据并测试能力。
