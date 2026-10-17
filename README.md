<p align="center">
  <img src="assets/app-icon-64.png" alt="Telegram AI 图标" width="64" height="64">
</p>

# Telegram AI

一个在本机运行的 Telegram 多账号 AI 助手。通过桌面工作台管理账号、登录会话和群组权限，让 AI 在指定群组中响应提及与回复。

**26.1.0 alpha** · Windows 桌面版 · Python / Telethon

[下载 Windows EXE](https://github.com/Ac1oud/telegramai/releases) · [完整使用指南](docs/usage.md)

## 能做什么

- **管理多个账号**：手机号或二维码登录、导入 session、自定义显示名称。
- **控制响应范围**：群组与用户白名单、主人身份设置、发送冷却与频率限制。
- **参考后生图**：附图或回复图片生成，具名人物、作品与事件先联网核实资料。
- **连接模型服务**：配置聊天、图片和语音 API，按需启用联网查询。
- **保留对话记忆**：按群组和用户分别保存对话，支持指定消息触发的群聊总结。
- **更方便的桌面操作**：选中账号按 Del 确认删除，窗口弹出与收回动画，GPT 与 Telegram 组合图标。

## 开始使用

### Windows EXE

1. 在 [Releases](https://github.com/Ac1oud/telegramai/releases) 下载 `TelegramAI.exe`，放入可写文件夹。
2. 双击启动；首次运行会在旁边生成 `.env` 模板。填写自己的 Telegram API ID / Hash，再配置模型服务。
3. 新建账号并登录，设置群白名单，然后启动监听。

`TelegramAI.exe` 为无终端版，运行与登录使用图形操作窗口，不打开 CMD。`TelegramAI-console.exe` 为命令行版，保留终端输出及交互，便于排错。两者各自包含完整依赖，可单独使用。

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
| 单独使用 EXE | 更新按钮打开 Releases；退出程序后替换 EXE，保留旁边的配置与数据目录。 |

Git 更新保留本地配置；存在未提交的代码或分支分歧时会停止并提示。EXE 的内置依赖发生变化时，需要下载新版 EXE。

## 本地数据与隐私

账号配置、API Key、登录 session 和对话数据库仅保存在本机，已从 Git 提交和 EXE 打包清单中排除。发布包只包含程序、依赖、图标和空白配置模板。请妥善保管 `.env`、`profiles/`、`data/`，不要上传或分享。

调用 AI 时，对应的对话上下文及所需图片会发送到你配置的模型服务。仅在成员知情、允许自动处理的群组中使用。

## 更多说明

账号管理、模型配置、Linux 部署、更新排错与 Windows 打包步骤见[完整使用指南](docs/usage.md)。
