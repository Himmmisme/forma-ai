# 测试与验收

验收覆盖新实例初始化、多账号登录与越权访问、项目状态和导出、图片上传及下载、Mock 提示词优化和生成、并发幂等、版本分叉和对比、BOM 计算、Excel 交换、实例重启和备份恢复。

## 2026-11-26 验收结果

| 范围 | 执行结果 |
| --- | --- |
| Python API 与服务 | Windows Python 3.12 下，SQLite 17 项与原生 PostgreSQL 17.12 17 项通过 |
| Chromium 浏览器 | 2 项通过。覆盖初始化、示例项目、优化、生成、刷新、分支、下载、对比、材料、成本、连接测试、备份及用户隔离 |
| WebKit 浏览器 | Windows Playwright WebKit 下同一套 2 项通过 |
| 项目与实例恢复 | 验证项目 ZIP、整站快照、账号重新登录、图片字节一致、多类方案恢复、分离密钥、校验错误及路径异常回滚 |
| 代码与依赖 | Ruff 检查通过，TypeScript 与 Vite 生产构建通过。npm audit 和 pip-audit 对当前锁定版本未报告已知漏洞 |
| Win 主机内网入口 | 通过本机内网 IPv4 完成登录、原生 PostgreSQL 入队、Mock 生成和下载。重启 Uvicorn 进程后，会话、项目、任务、版本和图片原始字节均保留 |
| Windows 本地启动脚本 | `start-local.ps1` 完成依赖安装、前端构建、SQLite 迁移，生产 UI 与首次初始化接口响应成功 |
| Compose | Compose CLI v5.8.0 校验通过。实际启动因当前宿主缺少 Docker 引擎而失败 |
| 三类适配器 | 模拟响应契约测试通过，验证请求路径、图片编码、附件格式和上游响应解析 |
| 凭据和付费调用 | 真实 OpenAI、Gemini 和第三方凭据测试待部署者执行 |

合计 17 个 Python 测试在两种数据库环境分别执行，浏览器端到端在两种浏览器引擎分别执行。Mock 包含本地图像结果和结构化文本示例。PostgreSQL 测试使用独立临时 schema，浏览器测试创建独立实例。

## VX API 兼容性回归

2026-11-26 在临时 SQLite 实例执行 19 项后端测试并通过。新增用例用模拟 HTTP 验证历史文生图的同步 JSON、HTTP 200 中的失败终态，以及单张原图生成的 multipart 字段、运行队列、图片下载和版本保存。Ruff 检查及 TypeScript、Vite 生产构建通过。真实 VX 模型权限与实际出图需由操作者确认后验证。

后续回归在 SQLite 和 PostgreSQL 17.12 两种环境各通过 21 项后端测试，在 Chromium 和 WebKit 分别通过 2 项端到端测试。模拟 HTTP 验证 PNG 附件、无状态字段的图片响应、VX 报告的上游 502、网关请求编号和旧型号失效时的重试保护。Ruff 检查及 TypeScript、Vite 生产构建通过。

## 交付复验

2026-11-26 补测持久任务读取快照图片时的归属校验。SQLite 和 PostgreSQL 17.12 两种环境各 22 项后端测试通过。Chromium 和 WebKit 使用隔离实例分别完成各 2 项端到端测试。前端生产构建与 Ruff 检查通过。`npm audit --omit=dev` 和 `pip-audit` 对各自锁定的运行依赖未报告已知漏洞。

## 复跑

前置环境为 Python 3.12、Node.js 22.12 以上的 22.x 和 npm。以下命令从项目根目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Push-Location backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
Push-Location frontend
npm ci
npm run build
npx playwright install chromium webkit
npm run test:e2e
npm run test:e2e -- --browser=webkit
Pop-Location
```

使用 PostgreSQL 运行后端测试时，将 `FORMA_TEST_DATABASE_URL` 设置为测试用数据库 DSN，测试用户需要创建临时 schema 的权限。使用前端生产构建执行浏览器用例。每种浏览器单独启动一轮测试，以便首次初始化用例使用独立数据。若默认测试端口 8185 已占用，可设 `FORMA_E2E_PORT`。

## 已知限制与未验证项

- 当前 Windows 主机没有可用的 Docker 引擎，Compose 构建、容器健康重启和另一台局域网设备的访问仍待部署环境验收。源码中的一键启动和恢复命令可直接用于该验收。
- 已验证 Windows 上的 Chromium 和 WebKit 浏览器引擎。尚无 macOS 实机验收。
- 实测主机对外部域名返回保留网段的 DNS 地址，按应用的公网地址规则拒绝。真实 API 还需在能正常解析公网地址的部署环境中录入模型与凭据后运行能力测试。
- 当前 Starlette 测试客户端对 httpx 发出弃用提示，服务接口、测试与上游 HTTP 适配器均可运行。
