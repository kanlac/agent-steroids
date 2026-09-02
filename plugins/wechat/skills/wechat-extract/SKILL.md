---
name: wechat-extract
description: 读取、总结、提取本机微信桌面端（macOS 微信 4.x）的聊天记录与群聊消息。做法是只读本地磁盘上的加密数据库、在本地解密，绝不操作微信客户端。当用户要翻看/总结某个微信群、看群里最近讨论了什么、提取聊天记录、找某人某段对话、或把微信消息喂给 agent 分析时使用。首次使用需按 references/setup.md 完成一次性初始化（临时关 SIP 截取口令、恢复 SIP、开启完全磁盘访问）。仅 macOS + Apple Silicon。
---

## 这个 Skill 解决什么

让 agent 能翻看、总结、提取本机微信的群聊/聊天记录——**只读本地数据库、在本地解密**，把消息变成可查询的明文，不碰微信客户端本身。

## 铁律：绝不自动化操作微信客户端

- 只允许**本地只读 + 本地解密**。绝不模拟点击 / 发消息 / 自动回复，绝不用非官方协议登录，绝不改微信的数据或二进制，绝不让微信产生任何账号侧（服务器可见）行为。
- 风控封号看的是**服务器侧的账号行为**；本地读文件、解密腾讯服务器根本看不到，所以守住这条 = **零封号风险**。一旦破了这条（自动化客户端、外挂协议）才可能封号，不值得。

## 心智模型

微信 4.x 把聊天记录锁在 **SQLCipher4 加密 + 分片** 的数据库里，钥匙不落盘、只在运行时内存中现算。整条链路是：**一次性截取"口令(passphrase)" → 用口令为每个库派生 key → 本地解密 → 查询/导出**。

- 口令是万能钥匙：每个库的真 AES key = `PBKDF2-HMAC-SHA512(口令, 该库文件头 16 字节 salt, 256000 轮, 32 字节)`。
- 口令**只在退出微信重登 / 大版本迁移后才变**；平时解密、导出**不需要关 SIP**。

## 初始化

**首次使用前，必须先按 [`references/setup.md`](references/setup.md) 完成一次性初始化**（临时关 SIP 截口令 → 恢复 SIP → 开完全磁盘访问）。这几步涉及系统安全设置和 root，必须用户亲手做，agent 只引导、给命令、读输出——具体步骤、原理和排查都在手册里，照着它带用户走，别在本文件里展开。

口令存在工作目录（默认 `~/wechat-extract/`，可用环境变量 `WECHAT_EXTRACT_HOME` 覆盖）的 `passphrase.hex`（权限 600），**不进仓库**。

## 工具：scripts/wechat.py

初始化完成后，用管线读数据（用系统 libcommonCrypto 做 AES、Homebrew libzstd 解压消息）：

- `python3 ${SKILL_PATH}/scripts/wechat.py decrypt` —— 增量解密所有库到工作目录 `plain/`（源没变则跳过）
- `python3 ${SKILL_PATH}/scripts/wechat.py groups [-n N]` —— 按最后活跃时间列出群
- `python3 ${SKILL_PATH}/scripts/wechat.py contacts <关键词>` —— 按名字搜群/人拿到 id
- `python3 ${SKILL_PATH}/scripts/wechat.py dump <群名或id> [--days N | --since YYYY-MM-DD] [-o 文件]` —— 导出某群某时间段的可读转录（默认最近 2 天）

**要读最新消息，先 `decrypt` 再 `dump`。**

## 解析要点（推不出来的关键事实）

- 加密：AES-256-CBC；page 4096；reserve 80（IV 16 + HMAC-SHA512 64）；首页前 16 字节是 salt（布局 A，解密首页从 offset 16 起，输出补回 `SQLite format 3\0`）。
- 消息表名 `Msg_<md5(对话id)>`，分布在各 `message_*.db` 分片；群消息在 `message/`，公众号在 `biz_message_*.db`。
- `message_content`：文本（`local_type=1`）通常是明文字符串，其余类型（表情/图片/链接/引用等）是 **zstd** 压缩的 XML（magic `28b52ffd`），需解压后解析。
- 发送者：`real_sender_id` = **该分片内** `Name2Id.rowid` → `user_name`(wxid 或群 id) → 再到 `contact` 表取昵称/备注。
- 群名/联系人名在 `contact.db` 的 `contact.nick_name / remark`；会话列表（含最后活跃时间）在 `session.db` 的 `SessionTable`。

## 总结风格

用户要的不只是"话题清单"，而是**大家表达了什么观点、有什么个人经验 / 踩坑**，并**穿插原话引用**（用「」包裹、注明发言人；多群一起总结时**标注原话出自哪个群**）。优先抓：谁持什么立场、给了什么具体经验 / 数字 / 结论、有没有分歧，而不是只列"聊了 X"。

## 什么时候要重做初始化

只有当用户**退出微信重新登录**、或微信**大版本数据迁移**导致口令失效（表现为 `decrypt` 报解密失败 / 首页魔数不符）时，才需要重跑 `references/setup.md` 的第 1–3 步重新截口令；FDA 是一次性的，不用重来。

## 敏感性

工作目录 `plain/` 是**全量明文聊天数据**，极敏感——不外传、不进公开仓库、不复制到无鉴权目录；`passphrase.hex` 同理。
