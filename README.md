<p align="center">
  <img src="assets/app-icon-64.png" alt="Telegram AI 图标" width="64" height="64">
</p>

# Telegram AI

一个在本机运行的 Telegram 多账号 AI 助手。通过桌面工作台管理账号、登录会话和群组权限，让 AI 在指定群组中响应提及与回复。

**26.1.3 alpha** · Windows 桌面版 · Python / Telethon

[下载 Windows EXE](https://github.com/Ac1oud/telegramai/releases) · [完整使用指南](docs/usage.md)

## 能做什么

- **管理多个账号**：手机号或二维码登录、导入 session、自定义显示名称。
- **并行监听多个账号**：每个账号使用独立监听进程、白名单、session 和状态库，可分别启用或关闭生图后同时运行。
- **账号独立模型**：每个账号分别保存聊天模型、图片模型、服务地址与 API Key，可同时连接不同模型服务。
- **控制响应范围**：群组与用户白名单、主人身份设置、发送冷却与频率限制。
- **参考后生图**：附图或回复图片时优先按原图编辑；只有明确要求联网搜索时，才把检索成功作为生图前提。
- **连接模型服务**：配置聊天、图片和语音 API，按需启用联网查询。
- **保留对话记忆**：按群组和用户分别保存对话，支持指定消息触发的群聊总结。
- **更方便的桌面操作**：选中账号按 Del 确认删除，窗口弹出与收回动画，GPT 与 Telegram 组合图标。

## 开始使用

### Windows EXE

1. 在 [Releases](https://github.com/Ac1oud/telegramai/releases) 下载 `TelegramAI.exe`，放入可写文件夹。
2. 双击启动；首次运行会在旁边生成 `.env` 模板。填写自己的 Telegram API ID / Hash，再配置模型服务。
3. 新建账号并登录，设置群白名单；在“生图设置”中选择当前账号的生图开关，然后可使用“启动全部监听”同时运行多个账号。

`TelegramAI.exe` 为无终端版，运行与登录使用图形操作窗口，不打开 CMD。`TelegramAI-console.exe` 为命令行版，保留终端输出及交互，便于排错。两者各自包含完整依赖，可单独使用。

独立 EXE 启动时会在后台检查 GitHub Releases。发现新版后可选择稍后提醒或立即更新；应用会在窗口内下载对应 EXE、校验 SHA-256、替换并自动重启，完成后显示更新成功。若新版启动失败，会恢复旧版并重启。更新不会覆盖同目录下的 `.env`、`profiles`、`data` 和 session 文件。源码仓库目录中的 EXE 仍可通过“同步更新”快进 Git 仓库。

EXE 已包含 Python 和运行依赖。已有本地项目可将 EXE 放在 `open-account-manager.bat` 旁边，继续使用现有账号配置；BAT 启动方式仍然保留。

### Python 源码

安装 Python 3.11 / 3.12 和 Git 后运行：

```powershell
git clone https://github.com/Ac1oud/telegramai.git
cd telegramai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\open-account-manager.bat
```

填写本机 `.env` 后创建账号并登录。私有仓库需使用有访问权限的 GitHub 账号。

## 更新方式

| 使用方式 | 如何更新 |
| --- | --- |
| Git 项目中的 BAT / EXE | 停止监听，点击“检查更新”或“同步更新”，完成后重启工作台。 |
| 单独使用 EXE | 启动后自动检查公开 Release；在应用内确认并更新，完成后自动重启。 |

Git 更新保留本地配置；存在未提交的代码或分支分歧时会停止并提示。EXE 更新只替换程序文件，保留本机配置和数据。匿名在线更新要求 GitHub 仓库与 Release 公开；否则 GitHub 会对未登录的其他电脑返回 404。

## 本地数据与隐私

账号配置、API Key、登录 session 和对话数据库仅保存在本机，已从 Git 提交和 EXE 打包清单中排除。发布包只包含程序、依赖、图标和空白配置模板。请妥善保管 `.env`、`profiles/`、`data/`，不要上传或分享。

调用 AI 时，对应的对话上下文及所需图片会发送到你配置的模型服务。仅在成员知情、允许自动处理的群组中使用。

## 更多说明

账号管理、模型配置、Linux 部署、更新排错与 Windows 打包步骤见[完整使用指南](docs/usage.md)。
