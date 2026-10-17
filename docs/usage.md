# Telegram AI 使用指南

[返回项目首页](../README.md)

当前版本：**26.1.0 alpha**。

这是一个 Python/Telethon 个人账号客户端框架：只监听白名单群组里对账号的明确 @ 提及，并读取最近的纯文本上下文。程序通过 OpenAI Responses API 生成回复，并使用群组白名单、每群冷却、回复延迟、全局最短发送间隔和 SQLite 去重限制处理频率。

## Windows 本地运行

需要 Python 3.11 或 3.12。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

编辑 `.env`，确认 Telegram `API_ID`、`API_HASH`、`OPENAI_API_KEY` 和 `OPENAI_MODEL` 已填写。`OPENAI_BASE_URL` 留空即可使用 OpenAI 官方 API。首次获取账号授权并列出群组 ID：

```powershell
python main.py --list-chats
```

将允许监听的群组 ID 写入 `.env` 的 `ALLOWED_CHAT_IDS`，多个 ID 用逗号分隔，然后启动：

```powershell
python main.py
```

首次启动时 Telethon 会在终端提示输入登录验证码；启用了两步验证的账号还需要输入密码。授权后会在 `data/` 生成登录 session。不要把该目录或 `.env` 上传、提交或发给他人；session 等同于账号授权凭据。收到符合条件的 @ 后，程序会把近期群聊文本发送给配置的模型服务生成回复；生成期间显示 Telegram 标准“正在输入”状态，完成后按设置的延迟一次性发送回复。

如果收不到登录验证码，也可以运行 `python main.py --qr-login`，并使用已登录的 Telegram 客户端扫描终端二维码（设置 → 设备 → 连接桌面设备）。二维码是一次性登录凭据，只在本机终端显示，切勿截图或发送给他人。二维码授权成功后，再运行 `python main.py --list-chats` 获取群组 ID。

## 多账号切换（Windows）

选中账号后可直接按 **Delete（Del）** 打开删除确认；默认选择“否”，确认后只移除配置，session 和数据库继续保留。快捷键只在账号列表获得焦点时生效，不影响设置输入框中的文字删除；正在由该窗口使用的账号需要先停止进程。

工作台采用 GPT 结形与 Telegram 小飞机组合图标。窗口与设置弹窗以短距离位移和轻微回弹打开，关闭时向下退出；动画期间保持窗口及控件尺寸不变，避免反复排版闪动，全程不透明；按钮悬停、账号选中和状态文字也有过渡效果。更新后需重新打开工作台才能看到新界面。

双击 `open-account-manager.bat` 打开桌面窗口，选择账号后可用手机号验证码登录并列群、二维码登录、启动监听、停止由本窗口启动的监听、新建账号配置、导入已有 session、查看文件路径、设置列表显示名称、管理群白名单、管理触发用户白名单或从切换器移除配置。“生图设置”可开关生图并设置图片服务的 Key、Base URL 和模型；“语言模型管理”可设置聊天模型的模型名称、Key 和 Base URL。两者都编辑根目录 `.env`，由所有账号共享，保存后需重启监听生效。群白名单窗口的“获取群 ID”会从当前账号已授权的 session 获取群名和 ID，可多选后加入白名单；触发用户白名单可限制哪些成员能够触发模型。修改白名单后需重启该账号的监听进程。显示名称只用于区分列表项目，不会修改 Telegram 账号、配置名或 session。导入 session 只登记现有文件路径，不移动或复制文件；移除配置不会删除 session 或状态数据库。首次切换到新号时选择对应账号 → 手机号登录/列群，在弹出的终端按提示登录；收不到验证码时改选二维码登录。

## GitHub 在线更新

更新仓库：<https://github.com/Ac1oud/telegramai>，发布分支为 `main`。

当前电脑连接仓库后，双击 `open-account-manager.bat`，即可使用：

1. **检查更新**：后台连接 GitHub，显示当前提交版本和待更新数量，界面仍可操作。
2. **同步更新**：先停止所有监听、登录终端（包括其他窗口启动的进程），再点击此按钮。仅快进更新；本地有未提交的代码或分支分歧时会停止，并提示处理。
3. 更新成功后关闭并重新打开账号管理器，再启动监听。如果 `requirements.txt` 发生变化，窗口会提示先重新安装依赖。

`.env`、`profiles/`、`data/`、session、数据库、虚拟环境均不上传。更新不会迁移账号或登录状态，也不会自动推送本机修改。

### Windows 单文件 EXE

提供两个独立版本：`TelegramAI.exe`（无终端版）与 `TelegramAI-console.exe`（命令行版）。无终端版的监听、日志、验证码和两步验证均在图形操作窗口内处理，不启动 CMD / BAT 终端；命令行版保留控制台输出和输入，方便排错。两个 EXE 都能独立运行，共用同目录的本地配置。

从 [GitHub Releases](https://github.com/Ac1oud/telegramai/releases) 下载 `TelegramAI.exe`，放入可写文件夹后双击即可运行，无需另外安装 Python。首次运行只会在 EXE 旁创建空白配置模板；请填写自己的 Telegram API 信息，再创建账号并登录。账号配置、session 和数据库均保存在 EXE 所在目录，不会写入临时解压目录，也不会包含在发布包中。

在现有 Git 项目中使用时，将 EXE 放在 `open-account-manager.bat` 旁边，便可继续使用已有的本地配置。EXE 优先加载该 Git 项目中的程序源码，因此“同步更新”后的代码会在重启后生效；该模式仍需要 Git。EXE 内置的第三方依赖不会随源码更新，依赖变更时请下载新版 EXE。

单独使用 EXE（旁边没有 `.git`）时，更新按钮会打开 Releases。先退出工作台与监听进程，下载新版并替换原 EXE，保留旁边的 `.env`、`profiles/` 和 `data/`。BAT 与 Python 源码继续保留，可按原来的方式启动。

开发者可在 Windows 安装 Python 3.12 后运行 `powershell -ExecutionPolicy Bypass -File .\build-windows.ps1`，生成的两个单文件位于 `dist/TelegramAI.exe` 和 `dist/TelegramAI-console.exe`。打包只包含程序、运行依赖、图标与空白 `.env.example`，通过明确资源清单排除所有本地账号和密钥。

### 在另一台 Windows 电脑安装

安装 Git for Windows 和 Python 3.11/3.12，然后在终端运行：

```powershell
git clone https://github.com/Ac1oud/telegramai.git
cd telegramai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\open-account-manager.bat
```

填写本机 `.env`，在账号管理器中新建账号并登录。通过 `git clone` 安装会自动配置 `origin/main`，之后可以直接使用更新按钮；GitHub 的 Download ZIP 不包含更新所需的 Git 信息。私有仓库首次克隆需用有权限的 GitHub 账号登录。

### 发布后续更新

在修改代码的电脑测试完成后，提交并推送：

```powershell
git add -u
git add 新增的代码文件
git commit -m "说明这次更新内容"
git push origin main
```

`新增的代码文件` 是占位符；没有新增文件时跳过该行。另一台电脑随后点击“检查更新”和“同步更新”即可。不要强制推送或强行添加 `.env`、`data/`、`profiles/`。

### 更新失败时

- 网络或凭据问题：在项目终端运行 `git fetch origin`，按提示登录 GitHub；使用代理时需为 Git 配置可用代理。
- 未设置更新源：确认 `git remote -v` 指向本仓库，执行 `git fetch origin` 和 `git branch --set-upstream-to=origin/main main`。
- 本地有修改：运行 `git status` 查看，先提交或自行备份修改。程序不会自动丢弃修改。
- 本地与远程分歧：先通过 Git 处理并测试，再同步。
- 依赖变化：常规 `.venv` 安装运行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。如果沿用 `.deps` 安装方式，应使用原来的 Python/pip 将依赖安装到 `.deps`（`python -m pip install --upgrade --target .deps -r requirements.txt`）。

开发验证：`python -m unittest discover -s tests -v`。更新测试使用临时本地仓库，不访问 Telegram 或 GitHub。

新账号配置有独立的 `SESSION_PATH`、`STATE_PATH` 和白名单。根目录 `.env` 中的 Telegram API ID/Hash 与模型 API 配置由账号配置共享；`profiles/*.env` 只保存账号级设置，已加入 `.gitignore`。以后新增配置可运行 `python main.py --create-profile 名称 --copy-settings-from current`，也可以从窗口创建。不要同时启动同一个 profile 的多个进程。

Ubuntu/Linux 可通过 `python main.py --profile new_account --qr-login` 授权，或用 `python main.py --profile new_account` 启动监听。

测试固定回复时，可在 `.env` 设置 `TEST_REPLY_TEXT=这是一条固定测试回复`。此时程序不会调用模型，但会真实发送这条固定文本；测试结束后清空该项。请只在成员知情且由你管理的测试群中启用自动回复。

## Ubuntu 24 部署

把项目放到 `/opt/tg-group-assistant`，创建服务用户并安装依赖。只有在 `generate_reply()` 已接入模型后，systemd 服务才会真正发送回复：

```bash
sudo useradd --system --create-home --home-dir /opt/tg-group-assistant --shell /usr/sbin/nologin telegram-ai
sudo install -d -o telegram-ai -g telegram-ai /opt/tg-group-assistant/data
sudo chown -R telegram-ai:telegram-ai /opt/tg-group-assistant
cd /opt/tg-group-assistant
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -n .env.example .env
chmod 600 .env
```

填写 `.env` 后，以服务用户在 SSH 终端中运行一次 `python main.py --list-chats`，完成 Telegram 登录并找出群组 ID。然后更新 `ALLOWED_CHAT_IDS`，在前台运行一次 `python main.py` 确认能正常连接，按 `Ctrl+C` 停止。安装并启动 systemd 服务：

```bash
sudo cp deploy/tg-group-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tg-group-assistant
sudo journalctl -u tg-group-assistant -f
```

如果 systemd 的 `User`、`Group` 或 `WorkingDirectory` 与实际安装路径不同，请同步修改 unit 文件。首次 Telegram 授权需要交互式终端；完成后 systemd 使用已创建的 session。

## 设置项

- `ALLOWED_CHAT_IDS`：允许监听的群组 ID；程序在未配置白名单时拒绝启动。
- `ALLOWED_SENDER_IDS`：可选的触发用户 ID 白名单，逗号分隔；留空表示允许白名单群内所有成员触发。账号切换器的“管理用户白名单”可多选增删，也能读取 Telegram 联系人 ID。
- `OWNER_USER_IDS`：可选的主人身份用户 ID，逗号分隔；与触发名单分开保存。数字 ID 稳定，主人也允许触发智能体；不能通过聊天内容自称改变。
- `OWNER_USERNAMES`：主人用户名备用匹配，逗号分隔（可带 `@`）。Telegram 用户名可更改，因此数字 ID 更稳定；运行时用户名只从实际发言者 Telegram 实体读取，不会把消息正文或被提及对象当作发言者。
- 人设固定为 ChatGPT 龙娘，不使用账号切换器标签 `DISPLAY_NAME` 作为人物名字；明确询问身份时由本地固定回复，已正确介绍过的用户再次追问会得到简短的傲娇回应。
- 账号切换器的“获取联系人用户 ID”会通过当前 Telegram session 读取联系人姓名、用户名和数字 ID，供多选导入白名单；不会读取或展示手机号。
- `CONTEXT_MESSAGES` / `CONTEXT_MAX_CHARS`：只在用户直接 @ 账号或回复账号并成功完成一轮对话后，将该用户与账号的对话保存到本地 SQLite；按群和用户分别隔离，最多保留最近 100 条消息，默认每次提供最近 10 条作为记忆。普通触发不会读取群友消息。只有当前触发消息包含“总结上面信息”或“總結上面信息”时，才读取最近 60 分钟最多 40 条群聊消息（最多 8000 字符）用于总结。
- `CHAT_COOLDOWN_SECONDS`：同一群组两次处理提及之间的最短间隔，最低 5 秒。Telegram 返回 FloodWait 后，程序会遵守服务端等待时间，并在该窗口内跳过触发，避免继续请求和重复打扰。
- `REPLY_DELAY_SECONDS`：模型生成回复后至少等待多久再发送。
- `GLOBAL_SEND_INTERVAL_SECONDS`：所有群组共享的最短发送间隔，最低 1 秒。
- `MAX_REPLY_UTF16_UNITS`：回复长度上限，按 Telegram 的 UTF-16 单位截断。
- 普通文字回复超过 50 个字符时，先发送约一半（尽量落在句末），约 1 秒后编辑为完整内容；编辑失败时补发剩余文本。图片和语音回复保持原样。
- `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`：OpenAI API 密钥、模型名称和可选的兼容服务地址。
- 账号管理器的“语言模型管理”可直接修改上述三项；API Key 输入框隐藏当前密钥，留空保留原值，也可明确清除。修改后重启监听生效。
- `WEB_SEARCH_ENABLED`：启用后，包含网址或明确要求联网查询的提及会尝试调用 Responses API 的网页搜索工具；兼容服务需要支持该工具。
- `VOICE_REPLY_ENABLED`：主开关开启后，仅当当前 @/回复消息含“发语音”时合成语音；需要音频服务支持 `/v1/audio/speech`，失败时自动回退为单条文字。
- `OPENAI_AUDIO_BASE_URL` / `OPENAI_AUDIO_API_KEY`：可单独指定语音服务；留空时沿用模型 API 配置。
- `OPENAI_SPEECH_MODEL` / `VOICE_REPLY_VOICE`：语音合成模型和音色。
- `OPENAI_IMAGE_BASE_URL` / `OPENAI_IMAGE_API_KEY` / `OPENAI_IMAGE_MODEL`：可单独配置图片 API 地址、密钥和服务商提供的图片模型名；密钥和地址留空时分别沿用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`。仅填写服务商确实支持 Images API 的模型。
- `IMAGE_GENERATION_ENABLED`：生图总开关；也可在账号管理器“生图设置”中切换，关闭时命中关键词不会调用图片 API。
- `OPENAI_IMAGE_SIZE`：可选的图片尺寸；留空时使用图片服务默认值。

聊天模式会拒绝编写或输出脚本、程序、代码、命令和配置文件；代码类请求在调用模型前拦截，模型若仍返回常见代码格式也会被过滤。带网址或明确要求联网查询时会尝试 Responses API 的 `web_search` 工具；OpenAI-compatible 网关需支持该工具。只有当前触发消息含“发语音”时才请求语音合成；其余情况只发送文字。生图只有在当前消息直接 @ 账号，且“生成图片”或繁体“生成圖片”出现在当前消息正文或被回复的原消息中时才调用图片 API。例如 `@账号用户名 帮我生成图片：一只在窗边看雨的橘猫，水彩风格`。关键词之后的文本作为图片描述。调用图片 API 前，程序会检查群和账号的发消息及照片/文件权限；若原群禁止照片和文件，但其他已配置白名单群至少有一种媒体发送权限，仍可生图并在发送时由终端交互选择一个目标群。终端按 `1. 群组ID | 群名` 列表显示，输入序号后需输入 `y` 确认，输入 `n` 返回重新选择；每次只发送到一个群。若其他白名单群均不可接收媒体，则跳过生图避免无效费用。权限允许后先回复“收到正在绘画>w<”，生成完成后删除该状态消息并发图；若照片被禁止但允许文件，会改用文件方式发送。转交群发出图片后一秒，会以回复形式附上“由于部分群组受限制，已将生成好的图片转交至该群组”。交互要求监听进程运行在可输入的终端中；无终端版从工作台启动监听会打开图形操作窗口，命令行版保留终端。图片 API 需兼容 OpenAI Python SDK 的 Images API (`/v1/images/generations`)，不同网关的支持情况和模型名称以服务商文档为准。无附图时，描述会先发送给聊天模型判断是否需要搜索；有附图且未明确要求联网时，原图直接发送给图片编辑接口。

### 生图参考图片与联网资料

- **本地图片参考**：把图片作为 Telegram 照片或图片文件发送，配文 `@账号 生成图片：保留人物，换成雪山场景`；也可以回复那张图片并发送上述指令。支持当前消息与被回复消息各一张参考图，PNG/JPEG/WebP，单张不超过 8 MB；图片不跨请求自动沿用。可用当前配文补充被回复生图指令的要求。GIF 请先转换为静态图片。
- **联网参考**：`@账号 生成图片：联网搜索《作品名》中的角色全名，按原作服装画头像`。未附图的指令会先判断是否涉及具体人物、具名角色、品牌、作品、事件或陌生专有名词，需要时强制先搜索。普通原创场景直接生成；附图时优先使用原图，也可明确要求同时联网。明确写“不要联网”时按提供的信息生成。
- **来源与歧义**：联网后提取已核实的视觉特征和背景，保留用户原始要求，生成图片附上参考来源。附带参考图的普通请求即使联网服务不可用或没有检索到来源，也会继续把原图交给图片编辑接口；只有用户明确写出“联网搜索”等要求时，检索失败才会停止并请求补充资料。网页参考是文本资料，不会自动下载网页图片作为原图。
- **服务要求**：聊天服务需要支持 Responses API；联网还需要 `WEB_SEARCH_ENABLED=true` 和 `web_search` 工具。参考图需要图片服务支持 `/images/edits` 和所选模型的图片输入，纯文生图继续使用 `/images/generations`。参考图读取失败或服务不支持编辑时会停止，不会丢图改成纯文生图。搜索与资料整理可能增加服务调用费用。
- **数据流**：用户原始生图说明和明确回复的文字可发送给聊天/搜索服务；附图仅在内存处理并发送给已配置的图片服务，搜索不会上传这些图片；参考资料、原图与密钥不会写进 GitHub 发布包。设置改动后重启监听生效。

## 隐私与运行边界

只将成功完成的 @/回复对话轮次按群和用户分别保存在本地 SQLite；其他群友的普通发言不会写入记忆库。关键词总结时，从 Telegram 临时读取最近一小时最多 40 条群消息并发送给配置的模型服务，不把这些原始群消息存入记忆库。保存的对话记忆、总结上下文、被回复原消息中的图片（若成功读取）会发送给配置的模型服务；如果启用语音回复，生成的回复文本也会发送给同一服务做语音合成；明确生图命令中的描述会发送给图片 API。正文和图片不会写入日志。请只在成员知情、允许使用自动化处理的群组中运行。程序的冷却、白名单和发送间隔用于限制打扰和请求频率，不尝试绕过平台限制。Telegram 返回 FloodWait 时，本次处理会跳过并记录等待秒数，不会紧接着重试。

触发条件为：收到新群消息、群组 ID 在当前账号的白名单中，并且消息中明确 `@账号用户名`、带有指向该账号的 Telegram mention entity，或直接回复账号之前发出的消息。若配置了 `ALLOWED_SENDER_IDS`，还必须是触发用户白名单或主人 ID 中的成员；未配置时，群白名单内所有成员都可触发。主人身份白名单只用于识别角色关系，不扩大群白名单、不绕过平台权限。普通对话只读取该用户与账号本人已保存的对话记忆；只有当前消息包含“总结上面信息”或“總結上面信息”时，才临时读取近期群聊并总结。若触发消息回复了群友，模型会收到被回复原文；原文带有 8 MB 以内的 JPEG、PNG、WebP 或 GIF 图片时，会尝试提供给模型识别。原文中的网址会触发现有联网搜索逻辑，实际可用性取决于模型服务。

### 账号权限隔离

新建账号与导入 session 默认使用空白群名单，不自动复制当前选中账号的权限。群白名单、触发用户、主人 ID/用户名均仅从所选账号配置读取，缺失字段不继承全局或其他账号。群名单为空时拒绝启动监听。旧版已复制到配置内的 ID 会保留，请按账号打开群白名单核对并移除不需要的 ID，保存后重启该账号监听。
