# Forma AI

[English](README.en.md) · [部署指南](docs/DEPLOYMENT.md)

Forma AI 是面向工业设计和硬件研发的中文工作台。团队可以从产品原图和参考图出发，生成并迭代设计方案，再对成果进行材料选型、BOM 编制和成本估算。

## 功能

- **设计生成** 支持多张原图和参考图，按设计方向、重构强度与保留项组合提示词，持续跟踪生成任务。
- **版本管理** 每张成果保留原始输出、生成参数和父版本关系。可分支修改、并排比较、收藏和下载。
- **材料与成本** 可编辑部件和材料建议，导入或导出 Excel 价格表，保存独立成本方案。
- **团队工作区** 提供账号和项目权限、项目 ZIP 导出、调用记录及整站备份与恢复。
- **模型接入** 内置 Mock，也支持 OpenAI、OpenAI Compatible 和 Gemini API。服务商与模型由超管配置。

## 快速开始

克隆本仓库或解压源码 ZIP，在含 `compose.yaml` 的目录执行对应命令。

**Windows 原生**需要 Python 3.12、Node.js 22.12 以上的 22.x 和 npm，使用 SQLite。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

打开 `http://localhost:8080/`，用 `.runtime\local\setup.token` 中的令牌创建超级管理员。脚本默认仅监听本机。

**Windows Docker Compose** 需要启动 Docker Desktop 并选择 Linux 容器，使用 PostgreSQL 17。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

同样打开 `http://localhost:8080/`。首次初始化令牌为本地 `.env` 中的 `APP_SETUP_TOKEN`。Linux 主机启动、端口、HTTPS 和恢复步骤见 [部署指南](docs/DEPLOYMENT.md)。

登录后点击「试用示例」，用内置 Mock 体验提示词优化、设计生成、分支、材料分析和成本评估。Mock 在本地运行，无需 API Key 或 GPU。

## 使用流程

1. 管理员创建账号并分配临时密码。成员首次登录时设置自己的密码。
2. 在「我的项目」新建项目，上传原图和可选参考图，设置方向、重构档位及输出格式。
3. 查看并比较成果与原图，选择已有版本继续修改。
4. 在「材料分析」或「成本评估」编辑部件、材料和价格，保存方案或导出项目。

## 凭据与数据

部署时生成实例口令和初始化令牌。仅在自己的实例中录入服务商 API Key。将实际 `.env`、`.runtime/`、数据库、密钥文件、备份和业务图片保存在部署环境中。业务图片和需求仅在操作者确认后随任务发送给所选外部服务。

## 开发文档

React、TypeScript 和 Vite 位于 `frontend/`。FastAPI、SQLAlchemy 和 Alembic 位于 `backend/`。生产环境由 FastAPI 提供页面，前后端通过同源的 `/api` 通信。

- [产品需求](docs/PRD.md) · [交互规范](docs/UI.md) · [提示词](docs/PROMPTS.md)
- [技术架构](docs/ARCHITECTURE.md) · [数据库](docs/DATABASE.md) · [业务 API](docs/API.md)
- [测试与验收](docs/TEST.md) · [开发进度](docs/PROGRESS.md)
