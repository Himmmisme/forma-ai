# 开发进度

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| 1 | 产品需求、架构、数据模型、基础界面 | 已验证 SQLite 初始化迁移及重复升级，1 项测试通过，TypeScript 和 Vite 构建通过 |
| 2 | 账号权限、项目、文件、管理框架 | 4 项测试在 SQLite 和 Windows PostgreSQL 17 分别通过，包含跨账号图片读取和密码重置；前端构建通过 |
| 3 | 服务商、模板、优化和生成任务 | SQLite 和 PostgreSQL 各 9 项测试通过，覆盖 Mock 生成、优化、幂等、密钥加密及三类请求契约；前端构建通过 |
| 4 | 迭代、版本分支、比较、收藏 | SQLite 和 PostgreSQL 各 11 项测试通过，覆盖多图独立版本、分支、重试、快照和 ZIP 导出；前端构建通过 |
| 5 | 材料建议、价格、BOM、成本 | SQLite 和 PostgreSQL 各 13 项测试通过，覆盖选型方案、报价优先级、BOM、缺项、权限与 Excel；前端构建通过 |
| 6 | UI 完善、异常处理、安全和自动化验收 | SQLite 和 PostgreSQL 各 15 项测试通过；Chromium 2 项端到端通过；npm 与 Python 运行依赖审计未报告已知漏洞 |
| 7 | Docker、Windows 局域网、备份恢复与交付 | 本机验收通过，覆盖 SQLite / PostgreSQL 整站恢复、原生 Windows 重启和本机 WLAN IPv4 健康检查。容器运行和跨设备访问待现场验收 |

从空工作区初始化。开发验证使用 Windows 便携 Git、Node.js、Python 与 PostgreSQL。真实 API 密钥由部署者配置。

首轮验收包含 SQLite 与 PostgreSQL 各 17 项后端测试和 Chromium、WebKit 各 2 项端到端测试。完整报告见 [测试与验收](TEST.md)。

阶段 3 兼容性补充（2026-11-26）。接入 VX API 文档中的同步文生图和单张原图编辑请求，并校验图片任务终态。SQLite 19 项测试通过，Ruff 检查及前端生产构建通过。真实 VX 出图仍需操作者确认后验证。

阶段 3 后续回归（2026-11-26）。单图编辑按 VX 示例上传 PNG，调用记录保存网关请求编号。生成任务显示提交时的型号，并在型号失效时提示新建任务。SQLite 和 PostgreSQL 17 各 21 项、Chromium 和 WebKit 各 2 项、Ruff 检查和前端生产构建通过。

阶段 6 交付复验（2026-11-26）。任务执行前补校验项目访问权与源图片归属。SQLite 和 PostgreSQL 17 各 22 项后端测试通过，Chromium 和 WebKit 各 2 项端到端通过。Ruff 与前端生产构建通过。npm audit 和 pip-audit 对运行依赖未报告已知漏洞。

阶段 7 本机复验（2026-11-26）。用 `start-local.ps1 -Lan` 重启原生实例，回环与本机 WLAN IPv4 的健康检查均返回 HTTP 200，项目和任务记录可读取。隔离实例完成 Mock 生成和下载，重启后复用原登录会话，并核对了同一版本与成果图片的 SHA-256。Compose 5.8.0 配置和容器入口脚本语法检查通过。

阶段 3 HTTP 服务商补充（2026-11-27）。OpenAI Compatible 和 Gemini API 支持 HTTP 与自定义端口。SQLite 25 项后端测试通过，覆盖无 Key 的本地连接、Gemini 自定义路径、DNS 校验和模拟模型调用。临时回环服务的自定义 HTTP 端口返回 200。Ruff 与前端生产构建通过。原生 Windows 实例重启后，8080 的首页与健康接口均返回 200。真实服务连接待操作者确认后验证。

阶段 7 源码发布复验（2026-11-27）。完成中英文 README 与部署说明，覆盖 Windows 原生启动和 Windows、Linux Docker Compose。25 项后端测试、TypeScript 检查、Vite 生产构建、Compose 配置及文档命令语法检查通过。扫描 Git 历史并与本地凭据比对，未发现实际凭据匹配。

待现场验收的项目包括容器镜像构建、容器启动及重启、另一台局域网设备的访问和真实模型调用。本机固件虚拟化关闭，WSL 未启用，Docker 客户端无法连接引擎。VX 生图使用日志已报上游 HTTP 502，真实出图待服务恢复后由操作者确认验证。
