---
name: wechat-desktop
description: Operate the macOS WeChat desktop app via computer-use MCP to read, navigate, and summarize group chat messages. Use this skill whenever the user asks to read WeChat messages, summarize WeChat groups, check unread WeChat messages, or any task involving the WeChat desktop application. Also trigger when the user mentions "微信", "群消息", "未读消息", or wants to interact with WeChat on their Mac.
---

# 桌面端微信操作 (WeChat Desktop)

通过 computer-use MCP 操作 macOS 微信客户端，读取并总结群聊消息。

## 前置准备

1. `request_access` 申请 WeChat 权限
2. `open_application` 打开微信（若未在前台）
3. 截图确认微信界面已就绪

## 核心工作流：读取群消息

### 识别未读群

在左侧会话列表中识别未读标识：
- **红色数字角标**（如 `70`）：普通未读计数
- **小红点**（无数字）：免打扰群有未读消息，容易遗漏

左侧列表文字较小，用 `zoom` 放大侧边栏区域来辨认群名和角标。

### 跳到未读起点

进入群聊后，点击聊天区域右上角的 **「xxx new message(s)」** 按钮，一步跳到最早的未读消息。不要手动向上滚动去找未读起点。

### 滚动阅读

微信的滚动灵敏度很低，单次 `scroll(100)` 几乎不移动。必须用 `computer_batch` 打包多次滚动：

```
5 x scroll(100)  ≈ 1 屏（适合逐屏精读）
10 x scroll(100) ≈ 2-3 屏（适合快速浏览）
20 x scroll(100) ≈ 5+ 屏（适合跳过旧消息）
```

每次 batch 结束后截图读取内容。通过检查前后截图的**消息重叠**来确认没有漏读——上一屏底部的消息应该出现在新截图的顶部。如果完全没有重叠，说明滚动量过大，下次减小。

### 判断是否到底

**唯一可靠的方法**：滚动后截图，与上一张对比，内容完全一样 = 到底了。

以下方法都**不可靠**，不要使用：
- 看输入框是否可见（输入框始终在底部，无论滚动位置）
- 看最新消息时间戳是否匹配侧边栏（不精确）
- 按 End 键（End 键滚动的是左侧会话列表，不是聊天内容）

## 图片处理

微信聊天中的图片以缩略图显示，信息不完整。

- **查看大图**：直接点击缩略图，微信会打开一个**独立窗口**显示全尺寸图片
- **关闭大图**：按**空格键**。不要按 Escape（无效），不要试图点红色关闭按钮（太小容易点偏，可能点成缩小）
- 读完图片内容后务必关闭大图窗口再继续滚动，否则后续操作会作用在大图窗口上

## 微信界面的坑

- **End 键**：滚动左侧会话列表到底部，不是聊天内容
- **Escape 键**：不关闭图片查看器
- **点击头像**：会弹出个人名片卡片，需点击其他区域关闭
- **转账消息**：Mac 版微信显示「当前微信版本不支持展示该内容」，无法查看金额
- **群成员面板**：某些操作可能意外打开右侧群成员列表，点击聊天区域关闭

## 输出：消息总结

读完一个群后，立即整理总结。总结模板：

```
**群名** (人数, 未读数)
时间跨度: x/x ~ x/x

1. [话题类别] — 概要描述
2. [话题类别] — 概要描述
...
```

关注有实质内容的消息（讨论、公告、链接、图片内容），略过纯表情互动和系统通知（入群、转账提示）。

多个群读完后，汇总成一条推送，按群分段，末尾附「与用户相关的行动项」（如即将到来的活动、需要回复的消息）。
