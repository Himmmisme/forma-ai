# 部署 Forma AI

[English](DEPLOYMENT.en.md) · [README](../README.md)

克隆仓库或解压源码 ZIP 后，从含 `compose.yaml` 的项目根目录运行命令。两种部署方式都通过同一端口提供页面和 `/api`。内置 Mock 无需外部凭据或 GPU。

## Windows 原生启动

安装 Python 3.12、Node.js 22.12 以上的 22.x 和 npm。在 PowerShell 中执行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

脚本会安装依赖、构建前端、迁移 SQLite，并在当前窗口前台运行服务。打开 `http://localhost:8080/`，用 `.runtime\local\setup.token` 中的令牌初始化超级管理员。可另开 PowerShell 检查服务。

```powershell
Invoke-RestMethod http://localhost:8080/api/health
```

默认仅监听本机。可传 `-Port 8081` 更换端口，传 `-Lan` 允许可信局域网访问，或用 `-Python`、`-Npm` 指定可执行文件绝对路径。按 Ctrl+C 停止。再次从同一目录启动时会复用 `.runtime\local\` 中的 SQLite 数据库、图片和密钥。

## Windows Docker Compose

1. 安装并启动 Docker Desktop，启用所需的 WSL 2 或 Hyper-V 后端并选择 Linux 容器。用 `docker version` 确认输出包含 Server，再运行 `docker compose version`。[Docker Desktop Windows 安装说明](https://docs.docker.com/desktop/setup/install/windows-install/)
2. 在 PowerShell 中运行以下命令。脚本首次运行时会生成随机数据库密码和初始化令牌，之后复用同一份 `.env`。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
   docker compose ps
   Invoke-RestMethod http://localhost:8080/api/health
   ```

3. 打开 `http://localhost:8080/`。填入本地 `.env` 中的 `APP_SETUP_TOKEN` 和自行选择的账号、显示名称、密码。初始化完成后可登录。
4. 局域网客户端用 Windows 主机的 IPv4 地址访问应用端口。用 `ipconfig` 查看主机地址，在专用网络的防火墙规则中允许可信设备访问。

首次运行可传 `-Port 8081`。已有实例可修改 `.env` 中的 `APP_PORT` 后重启应用。Windows Docker 启动脚本默认监听所有接口。仅供本机访问时，设 `APP_BIND=127.0.0.1` 后运行 `docker compose up -d --wait`。

## Linux Docker Compose

安装 Docker Engine、Compose 插件和 `openssl`。在项目根目录生成 `.env`。以下命令保留已存在的 `.env`，新文件仅供当前用户读写。

```sh
(
  set -euC
  umask 077
  if [ ! -e .env ]; then
    forma_db_password=$(openssl rand -hex 32)
    forma_setup_token=$(openssl rand -hex 32)
    cat > .env <<EOF
APP_PORT=8080
APP_BIND=127.0.0.1
APP_COOKIE_SECURE=0
APP_WORKER_SLOTS=4
POSTGRES_PASSWORD=$forma_db_password
APP_SETUP_TOKEN=$forma_setup_token
EOF
  fi
)
```

配置就绪后构建、启动并检查服务。

```sh
docker compose up --build -d --wait
docker compose ps
curl -fsS http://127.0.0.1:8080/api/health
```

远程主机只监听回环时，可通过 SSH 转发完成首次初始化。将用户名和主机名换成自己的部署地址。

```sh
ssh -N -L 18080:127.0.0.1:8080 your-user@server.example.com
```

在客户端打开 `http://localhost:18080/`，使用服务器本地 `.env` 中的 `APP_SETUP_TOKEN`。若已修改 `APP_PORT`，同时调整隧道的目标端口。

## 配置与日常运维

用于共享或存放业务图片的实例通过受信任的 HTTPS 反向代理访问。将页面和 `/api` 转发到同一应用。代理需允许 32 MiB 请求体，并设置应用的 `APP_COOKIE_SECURE=1`。更新 `.env` 后运行 `docker compose up -d --wait`。本机 HTTP 使用 `APP_COOKIE_SECURE=0`。PostgreSQL 仅在 Compose 网络内提供服务，应用在数据库健康后执行 Alembic 迁移。

| 变量 | 用途 |
| --- | --- |
| `APP_PORT` / `APP_BIND` | 宿主机监听端口和地址 |
| `POSTGRES_PASSWORD` | 创建数据库卷时采用的密码，应用连接也使用它 |
| `APP_SETUP_TOKEN` | 首次注册超级管理员的令牌，部署时随机生成 |
| `APP_COOKIE_SECURE` | HTTPS 填 `1`，本机 HTTP 填 `0` |
| `APP_WORKER_SLOTS` | 单应用进程的队列槽位，默认 `4`，范围 `1–8` |

```sh
docker compose ps
docker compose logs --tail 100 app
docker compose restart app
docker compose stop
docker compose up -d --wait
```

更新或重启时保留 Compose 项目名和 `postgres_data`、`files_data`、`instance_secrets` 三个命名卷。应用与数据库使用 `unless-stopped` 重启策略。实际 `.env`、本地运行目录、数据库、密钥、备份和业务图片仅保存在部署环境中。[Docker 数据卷](https://docs.docker.com/engine/storage/volumes/)

## 启用真实 API

超管登录后打开「管理后台 → API 服务商与模型」。先添加服务商并保存 Key，再到模型列表填入供应商实际启用的模型 ID、能力、输入限制和输出规格，分别测试连接和模型。OpenAI 官方使用固定上游地址。Gemini API 默认使用官方地址，也可填写自定义 API 前缀。OpenAI Compatible 使用填写的 API 前缀。路径和参数支持情况以测试为准。

图片工作台会把产品原图作为输入。OpenAI 及兼容协议需为工作台的生成模型勾选图片生成和图片编辑，并按模型文档填写规格。后台可按任务分别绑定模型。使用者在操作入口同意发送相关图片和需求后才发起外部调用。超管可以在系统设置中暂停外部 API，暂停期间仍可用 Mock。

### 自定义 HTTP 服务商

- Gemini 原生 REST 接口选 `Gemini API`。输入 `http://api.example.com:8080` 时，Forma AI 会补全 `/v1beta`。服务使用其他路径时可填写完整 API 前缀，例如 `http://api.example.com:8080/proxy/v1`。添加模型时，模型 ID 填写连接测试返回的 `models/` 之后的部分。[Gemini API 模型列表](https://aistudio.google.com/api-reference/models)
- OpenAI 兼容接口选 `OpenAI Compatible`，填写后端能访问的完整 API 前缀，例如 `http://127.0.0.1:8080/v1`。图片响应可以使用 `b64_json` 或公网 HTTPS 下载链接。

保存后运行「连接测试」，Forma AI 会在前缀后添加 `/models`。无需验证的 HTTP 服务可留空 Key。公网 HTTP 会明文传输凭据和请求内容。已保存 Key 的服务商更换地址时，需重新填写目标地址的 Key。同一台 Windows 主机上若 API 已占用 8080，可用 `-Port 8081` 启动 Forma AI。

### VX API 图片模型

服务商协议选择 `OpenAI Compatible`，Base URL 填 `https://la-api.vxvxvx.top/v1`。令牌开通 `gemini-nano-banana-2.1` 后，可在该服务商下添加此模型。勾选「图片生成」和「图片编辑」，将最大输入张数与最大生成张数均设为 `1`，图片规格可填 `1:1 | 1K 方图 | 1K`。在「任务默认模型」中将「图片生成」绑定到该模型，然后在工作台选择一张原图。分支修改同时使用父版本图和原图，需要另选支持多图编辑的模型。[VX API 接入文档](https://la-api.vxvxvx.top/manual/vx-api.html)

`gpt-image-2.5` 和 `gpt-image-2.5-pro` 的文生图接口在 VX 文档中列为历史资料。对于仍有相应权限的令牌，Forma AI 的图片生成能力测试可按该历史请求格式提交。两款型号均缺少工作台使用原图所需的图像编辑能力。正式使用前，先核对当前令牌权限和模型分组，再由操作者确认实际调用。[VX API 接入文档](https://la-api.vxvxvx.top/manual/vx-api.html)

换用模型后，在工作台点「生成设计」创建任务。失败卡片显示提交时使用的型号，按原模型重试沿用原参数。排查 VX 的上游错误时，可用任务记录里的请求编号查询 [VX 使用日志](https://la-api.vxvxvx.top/usage-logs/common)。

## 备份及恢复

1. 超管打开「管理后台 → 系统日志及备份 → 整站备份」，创建并下载 ZIP。项目 ZIP 可独立交付给项目成员，实例恢复使用含 `manifest.json` 的完整快照。
2. 如果录入过真实 API Key，单独备份 `provider.key`。将数据库快照和密钥分别保管。

   ```powershell
   New-Item -ItemType Directory -Force .\.runtime\recovery\files, .\.runtime\recovery\keys
   docker compose cp app:/var/lib/forma/secrets/provider.key .\.runtime\recovery\keys\provider.key
   ```

3. 将完整 ZIP 放入 `.runtime\recovery\files` 并命名为 `snapshot.zip`。用新的 Compose 项目名和未被占用的端口恢复到空实例，先启动数据库。在恢复完成前保持目标应用停止。

   ```powershell
   $backupDir = (Resolve-Path .\.runtime\recovery\files).Path
   $keysDir = (Resolve-Path .\.runtime\recovery\keys).Path
   $env:APP_PORT = '8081'
   $env:APP_BIND = '127.0.0.1'
   $env:APP_COOKIE_SECURE = '0'
   docker compose -p forma-recovery build app
   docker compose -p forma-recovery up -d --wait db
   docker compose -p forma-recovery run --rm --no-deps -v "${backupDir}:/recovery/files:ro" -v "${keysDir}:/recovery/keys:ro" app python -m app.manage restore /recovery/files/snapshot.zip --key-file /recovery/keys/provider.key
   docker compose -p forma-recovery up -d --wait app
   ```

   恢复须使用与快照迁移版本匹配的镜像。如果没有加密密钥文件，省略第二个 `-v` 和 `--key-file`，恢复后重新录入相关凭据。恢复会检查表结构、图片大小及 SHA-256，已有业务记录的实例会拒绝恢复。备份时仍排队或执行的任务会以失败状态恢复，以便核对来源实例后明确重试。
4. 打开 `http://localhost:8081/`，用备份中的账号重新登录。确认项目、图片、版本与方案后，安排切换入口。恢复项目的运维命令需继续使用 `-p forma-recovery` 和已选择的端口。

本地 SQLite 环境也可使用 CLI。先退出目标服务，在 `backend` 目录为 `APP_DATA_DIR` 与 `APP_SECRET_DIR` 指定新的空目录，再执行 `..\.venv\Scripts\python.exe -m app.manage restore <快照路径>`。可以追加 `--key-file <密钥路径>`。日常 CLI 备份使用 `python -m app.manage backup <新ZIP路径>`，调用时传入源实例相同的数据库地址和文件目录。

## 部署现场验收

1. 用独立的测试实例执行对应启动步骤，确认健康接口返回 HTTP 200 和状态 ok。Docker 部署还需通过 `docker compose ps` 确认应用和数据库健康。
2. 在同一局域网的另一台设备打开主机 IPv4 地址，登录测试账号，使用示例素材生成一版 Mock 成果并下载图片。
3. 重启应用和所用数据库服务。再次确认健康状态、登录、项目、版本及图片下载。可对比重启前后下载图片的 SHA-256。
4. 需要验证真实模型时，在部署环境确认已配置的型号与凭据，由操作者确认提交测试。
