# Forma AI

面向工业设计师、硬件研发和产品经理的中文设计工作区。从产品原图出发，组合工业设计提示词，生成独立设计版本，再对同一成果开展材料选型与成本估算。

## 启动

Windows 主机安装并启动 Docker Desktop，选择 Linux 容器。在本目录打开 PowerShell 并执行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

浏览器打开 `http://localhost:8080/`，使用 `.env` 中的 `APP_SETUP_TOKEN` 初始化超级管理员。登录后点击「试用示例」，用内置 Mock 依次体验提示词优化、生成、分支、材料分析和成本计算。配置真实模型后，应用才会按用户确认的任务发送相关输入。

Docker 部署不需要本地 GPU。Windows 无 Docker 时也可运行 `scripts/start-local.ps1` 启动本地 SQLite 实例。局域网、环境变量、原生启动与恢复步骤见 [Windows 局域网部署](docs/DEPLOYMENT.md)。

## 使用路径

1. 管理员在「用户管理」创建账号并分配临时密码。成员首次登录后设置自己的密码。
2. 在「我的项目」创建项目，上传原图和可选参考图，并选择方向、重构档位与输出格式。
3. 在生成成果中查看图片和参数，继续修改任意版本，或将成果与原图并排比较。
4. 从任意成果进入「材料分析」或「成本评估」，编辑部件与价格并保存独立方案。
5. 超管可配置 API、查看调用记录及创建整站备份。项目 ZIP 用于交付单个项目。

## 文档

- [产品需求](docs/PRD.md)
- [技术架构](docs/ARCHITECTURE.md)
- [数据库](docs/DATABASE.md)
- [业务 API](docs/API.md)
- [交互规范](docs/UI.md)
- [提示词](docs/PROMPTS.md)
- [测试与验收](docs/TEST.md)
- [Windows 局域网部署](docs/DEPLOYMENT.md)
- [开发进度和环境限制](docs/PROGRESS.md)
