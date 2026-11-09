# Git 增量发布与更新指南

本文用于源码交付和后续小体积更新。Git bundle 是一个可离线传输的 Git 仓库文件，不要求目标机连接 GitHub、GitLab 或源服务器。

当前版本由根目录 `VERSION` 定义，发布标签统一使用 `radar-v<版本号>`，例如 `radar-v0.3.0`。实验方案、仿真结果、日志、`.env.radar`、`.venv` 和 `node_modules` 不进入 Git，切换版本时会保留。

## 1. 首次安装

源机器生成完整 bundle：

```bash
./scripts/create_git_bundle.sh
```

传输以下两个文件：

```text
radar-v0.3.0-full.bundle
radar-v0.3.0-full.bundle.sha256
```

目标机器校验、克隆并安装：

```bash
sha256sum -c radar-v0.3.0-full.bundle.sha256
git clone -b radar-v0.3.0 radar-v0.3.0-full.bundle radar_simulate
cd radar_simulate
./scripts/install_radar_workbench.sh
./scripts/verify_deployment.sh
./scripts/start_radar_workbench.sh
```

克隆后处于发布标签对应的 detached HEAD，这是部署目录的预期状态。不要直接在这个目录修改受 Git 跟踪的源码；开发修改应在单独克隆或分支中完成。

## 2. 制作后续增量包

完成新版本代码后：

1. 更新 `VERSION` 和前端版本；
2. 运行测试并生成前端生产构建；
3. 提交全部发布文件；
4. 创建带说明的标签；
5. 指定上一个发布标签生成增量 bundle。

示例：

```bash
git tag -a radar-v0.3.1 -m "Radar workbench 0.3.1"
./scripts/create_git_bundle.sh \
  --tag radar-v0.3.1 \
  --from-tag radar-v0.3.0
```

默认生成：

```text
deliverables/radar-v0.3.0-to-radar-v0.3.1.bundle
deliverables/radar-v0.3.0-to-radar-v0.3.1.bundle.sha256
```

增量 bundle 只包含两个标签之间新增的 Git 对象。每个目标版本都必须从已安装版本的后代提交产生，脚本会拒绝分叉历史和轻量标签。

## 3. 在目标机器应用更新

把 bundle 和同名 `.sha256` 文件放在一起，在现有项目根目录执行：

```bash
./scripts/apply_git_bundle.sh \
  /path/radar-v0.3.0-to-radar-v0.3.1.bundle
```

脚本依次执行：

1. 确认受跟踪源码没有本地修改；
2. 校验 SHA-256、bundle 完整性和增量包前置提交；
3. 确认当前提交是目标发布的祖先；
4. 记录当前提交和服务状态，停止正在运行的服务；
5. 切换到目标发布标签，检查版本与预构建界面；
6. 验证本地 Python/Sionna 环境，恢复原服务状态；
7. 任一步失败时切回更新前提交并尝试恢复服务。

若本次更新修改了 Python 依赖，显式允许重新安装：

```bash
./scripts/apply_git_bundle.sh UPDATE.bundle --install-dependencies
```

依赖安装可能访问 Python 软件源，且虚拟环境本身不由 Git 回滚。重要生产环境应先备份 `.venv`，或在新目录完成更新验证后再切换。

服务原本停止时，更新后仍保持停止。可用 `--restart` 强制启动，或用 `--no-restart` 保持停止。

## 4. 验证与手动回滚

查看当前发布：

```bash
cat VERSION
git describe --tags --exact-match
git status --short
curl http://127.0.0.1:8000/api/health
```

自动回滚只处理本次更新过程中的错误。更新成功后若业务验证发现问题，可手动切回旧标签：

```bash
./scripts/stop_radar_workbench.sh
git checkout --detach radar-v0.3.0
./scripts/verify_deployment.sh
./scripts/start_radar_workbench.sh
```

忽略目录中的历史结果不会因标签切换而删除。若新版本对结果格式进行了不可逆迁移，应先按部署指南备份 `outputs/radar_workbench/`。

## 5. 常见拒绝原因

- `Tracked files have local changes`：先提交开发修改，或在确认内容后使用 `git stash`；不要用强制 checkout 覆盖。
- `Repository lacks these prerequisite commits`：目标机不是该增量包要求的旧版本，先安装正确的前置 bundle，或改用最新完整 bundle 新建目录。
- `not an ancestor`：目标目录有独立提交，不能安全快进；在新目录克隆完整 bundle。
- `Release has no prebuilt frontend`：发布过程不完整，重新构建前端并制作新标签。
- 健康检查失败：脚本会恢复旧提交；运行 `scripts/collect_error_report.sh` 收集完整错误报告。
