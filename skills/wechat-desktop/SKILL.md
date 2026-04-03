---
name: wechat-desktop
description: Read, navigate, and summarize WeChat (微信) group chat messages on macOS desktop using computer-use MCP. Trigger this skill whenever the user wants to check WeChat messages, read a specific WeChat group, summarize unread WeChat chats, reply in a WeChat group, view images shared in WeChat, or push WeChat summaries elsewhere. Also trigger when the user mentions "微信", "群消息", "未读消息", "看群", "读消息", or any WeChat desktop interaction — even short requests like "帮我看一下微信" or "check my wechat". This skill handles the full workflow: opening the app, navigating groups, scrolling through messages, OCR for accurate Chinese text reading, and producing structured summaries.
---

# 桌面端微信操作 (WeChat Desktop)

通过 computer-use MCP 操作 macOS 微信客户端，读取并总结群聊消息。

## Payload 大小保护

本插件包含一个 `PostToolUse` hook（`guard-payload-size.sh`），在每次工具调用后检查会话 transcript 大小。当接近 20MB API 限制时（阈值 16MB），会提醒运行 `/compact` 压缩上下文。

这是 Claude Code 的一个已知 bug（[anthropics/claude-code#8092](https://github.com/anthropics/claude-code/issues/8092)）的临时解决方案：computer-use 截图会快速累积 payload 大小，超过 20MB 后会话直接报错失效。这个 hook 能在接近限制时提前预警，避免工作丢失。

## 前置准备

1. `request_access` 申请 WeChat 权限
2. `open_application` 打开微信（若未在前台）
3. 截图确认微信界面已就绪

## 消息发送者识别

微信聊天界面通过气泡颜色和位置区分发送者：

- **右侧绿色气泡**：用户自己发的消息。总结时标注为"你"或直接描述用户的行为（如"你约了复诊"）
- **左侧白色气泡**：群友/其他人发的消息。通过气泡旁边的头像和昵称识别具体是谁

总结时必须准确区分用户和群友的消息，不要把群友的消息当成用户的，也不要把用户的消息归给别人。

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

## OCR 辅助（提高文字识别准确率）

截图中的小字和中文容易被视觉模型误读。当需要精确阅读消息内容时，使用 PaddleOCR 脚本辅助。

### 环境准备（首次使用）

检查 venv 是否存在，不存在则创建（约需 1-2 分钟下载模型和依赖）：

```bash
VENV=$HOME/.local/share/paddleocr-venv
if [ ! -f "$VENV/bin/python" ]; then
  uv venv --python 3.12 "$VENV"
  uv pip install --python "$VENV/bin/python" \
    paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
  uv pip install --python "$VENV/bin/python" \
    paddleocr --index-url https://pypi.tuna.tsinghua.edu.cn/simple
fi
```

首次运行 OCR 时 PaddlePaddle 会自动下载模型到 `~/.paddlex/`（约 80MB），后续运行直接使用缓存。

### 使用方式

1. 用 `screencapture -x /tmp/wechat-ocr.png` 截取当前屏幕
2. 用 `zoom` 确定聊天内容区域在截图中的像素坐标（retina 2x，display 坐标 × 2）
3. 运行 OCR 脚本，用 `--crop` 裁剪到聊天区域：

```bash
$HOME/.local/share/paddleocr-venv/bin/python \
  ${CLAUDE_PLUGIN_ROOT}/skills/wechat-desktop/scripts/ocr_chat.py \
  /tmp/wechat-ocr.png \
  --crop x1,y1,x2,y2 \
  2>/dev/null
```

输出为逐行 JSON，按从上到下排序：
```json
{"y": 123, "x": 45, "text": "你好", "score": 0.98}
```

结合截图中的气泡位置（右绿=用户，左白=群友）理解每条消息的发送者。

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
