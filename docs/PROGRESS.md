# 开发进度

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| 1 | 产品需求、架构、数据模型、基础界面 | 已验证 SQLite 初始化迁移及重复升级，1 项测试通过，TypeScript 和 Vite 构建通过 |
| 2 | 账号权限、项目、文件、管理框架 | 4 项测试在 SQLite 和 Windows PostgreSQL 17 分别通过，包含跨账号图片读取和密码重置；前端构建通过 |
| 3 | 服务商、模板、优化和生成任务 | SQLite 和 PostgreSQL 各 9 项测试通过，覆盖 Mock 生成、优化、幂等、密钥加密及三类请求契约；前端构建通过 |
| 4 | 迭代、版本分支、比较、收藏 | SQLite 和 PostgreSQL 各 11 项测试通过，覆盖多图独立版本、分支、重试、快照和 ZIP 导出；前端构建通过 |
| 5 | 材料建议、价格、BOM、成本 | SQLite 和 PostgreSQL 各 13 项测试通过，覆盖选型方案、报价优先级、BOM、缺项、权限与 Excel；前端构建通过 |
| 6 | UI 完善、异常处理、安全和自动化验收 | SQLite 和 PostgreSQL 各 15 项测试通过；Chromium 2 项端到端通过；npm 与 Python 运行依赖审计未报告已知漏洞 |
| 7 | Docker、Windows 局域网、备份恢复与交付 | 进行中 |

从空工作区初始化。开发验证使用 Windows 便携 Git、Node.js、Python 与 PostgreSQL。真实 API 密钥由部署者配置。
