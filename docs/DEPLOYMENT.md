# Windows 局域网部署

## 在 Windows 启动

1. 安装 Docker Desktop，启用它所需的虚拟化和 WSL 2 或 Hyper-V 后端，选择 Linux 容器。启动 Docker Desktop 后用 `docker version` 确认输出包含 Server，用 `docker compose version` 确认 Compose 可用。[Docker Desktop Windows 安装说明](https://docs.docker.com/desktop/setup/install/windows-install/)
2. 在含 `compose.yaml` 的项目根目录打开 PowerShell。执行下列命令，首次运行会生成随机数据库密码和初始化令牌，之后使用同一份 `.env`。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
   docker compose ps
   ```

3. 打开 `http://localhost:8080/`。在首次初始化页面填入 `.env` 中 `APP_SETUP_TOKEN` 的值、账号、显示名称和自选密码。初始化完成后，界面将切换为登录页。
4. 局域网其他设备使用 `http://Windows主机IPv4:8080/`。用 `ipconfig` 查看实际网络适配器的 IPv4。访问受 Windows 防火墙管理，在专用网络中允许可信局域网设备访问应用端口。

首次运行前可给启动脚本传 `-Port 8081`。已有实例修改 `.env` 的 `APP_PORT` 后重新启动。设置 `APP_BIND=127.0.0.1` 可只接受本机访问。用于共享或有敏感图片的实例应在受信任 HTTPS 反向代理后访问，并设 `APP_COOKIE_SECURE=1`。在本地直连 HTTP 流程中保留其默认值 0。数据库仅在 Compose 网络中使用，应用等待数据库健康后执行 Alembic 迁移。[Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)

| 变量 | 用途 |
| --- | --- |
| `APP_PORT` / `APP_BIND` | Windows 监听端口和地址 |
| `POSTGRES_PASSWORD` | 初次创建数据库时采用的密码，运行期同时供应用连接 |
| `APP_SETUP_TOKEN` | 首次注册超管使用，随机生成 |
| `APP_COOKIE_SECURE` | HTTPS 部署填 1 |
| `APP_WORKER_SLOTS` | 单应用进程的队列执行槽位，默认 4，范围 1–8 |

重复执行启动脚本可重建应用镜像。常用命令如下。

```powershell
docker compose ps
docker compose logs --tail 100 app
docker compose restart app
docker compose stop
docker compose up -d --wait
```

应用与数据库设置为 `unless-stopped`，Docker 引擎运行时会按策略重启退出的服务。数据分别位于 `postgres_data`、`files_data` 和 `instance_secrets` 命名卷。备份前保管好 `.env`。保留卷才能继续打开原实例。 [Docker 数据卷](https://docs.docker.com/engine/storage/volumes/)

## 无 Docker 的本地启动

安装 Python 3.12 和 Node.js 22.12 或更高的 22.x 版本。在项目根目录执行下列命令。脚本构建前端，准备本地数据库，再在当前 PowerShell 窗口前台运行服务。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

首次初始化令牌位于 `.runtime\local\setup.token`。默认端口为 8080，可传 `-Port 8081`。默认仅监听本机，传 `-Lan` 可进行同网络访问。可用 `-Python`、`-Npm` 传入可执行文件绝对路径。停止服务按 Ctrl+C。再次启动会读取同一份 SQLite、图片和密钥，均位于 Git 忽略的 `.runtime\local` 下。

## 启用真实 API

超管登录后打开「管理后台 → API 服务商与模型」。先添加服务商并保存 Key，再到模型列表填入供应商实际启用的模型 ID、能力、输入限制和输出规格，分别测试连接和模型。官方 OpenAI、Gemini 使用固定上游地址。兼容服务填写公网 HTTPS API 前缀，路径和参数支持情况以测试为准。

图片工作台会把产品原图作为输入。OpenAI 及兼容协议需为工作台的生成模型勾选图片生成和图片编辑，并按模型文档填写规格。后台可按任务分别绑定模型。使用者在操作入口同意发送相关图片和需求后才发起外部调用。超管可以在系统设置中暂停外部 API，暂停期间仍可用 Mock。

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
   docker compose -p forma-recovery up -d --wait db
   docker compose -p forma-recovery run --rm --no-deps -v "${backupDir}:/recovery/files:ro" -v "${keysDir}:/recovery/keys:ro" app python -m app.manage restore /recovery/files/snapshot.zip --key-file /recovery/keys/provider.key
   docker compose -p forma-recovery up -d --wait app
   ```

   恢复须使用与快照迁移版本匹配的镜像。如果没有加密密钥文件，省略第二个 `-v` 和 `--key-file`，恢复后重新录入相关凭据。恢复会检查表结构、图片大小及 SHA-256，已有业务记录的实例会拒绝恢复。备份时仍排队或执行的任务会以失败状态恢复，以便核对来源实例后明确重试。
4. 打开 `http://localhost:8081/`，用备份中的账号重新登录。确认项目、图片、版本与方案后，安排切换入口。恢复项目的运维命令需继续使用 `-p forma-recovery` 和已选择的端口。

本地 SQLite 环境也可使用 CLI。先退出目标服务，在 `backend` 目录为 `APP_DATA_DIR` 与 `APP_SECRET_DIR` 指定新的空目录，再执行 `..\.venv\Scripts\python.exe -m app.manage restore <快照路径>`。可以追加 `--key-file <密钥路径>`。日常 CLI 备份使用 `python -m app.manage backup <新ZIP路径>`，调用时传入源实例相同的数据库地址和文件目录。

## 部署现场验收

1. 在能运行 Linux 容器的 Windows 主机，用独立的测试实例执行 Docker 启动步骤。通过 `docker compose ps` 确认应用和数据库健康。
2. 在同一局域网的另一台设备打开主机 IPv4 地址，登录测试账号，使用示例素材生成一版 Mock 成果并下载图片。
3. 重启两个容器。再次确认健康状态、登录、项目、版本及图片下载。可对比重启前后下载图片的 SHA-256。
4. 需要验证真实模型时，在部署环境确认已配置的型号与凭据，由操作者确认提交测试。
