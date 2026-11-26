# Windows 局域网部署

采用 Docker Desktop Linux 容器和 Docker Compose。应用端口发布到 Windows 主机，数据库只在 Compose 网络中使用。数据卷保留 PostgreSQL、图片、备份和本实例的加密材料。安装步骤、局域网地址与防火墙设置、备份和恢复命令随部署实现更新。

部署要求见 [Docker Desktop Windows 安装说明](https://docs.docker.com/desktop/setup/install/windows-install/)和 [Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)。
