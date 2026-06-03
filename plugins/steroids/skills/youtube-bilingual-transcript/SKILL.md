---
name: youtube-bilingual-transcript
description: |
  Turn a YouTube link into a polished single-file bilingual (Chinese + original) transcript reading page.
  Use when the user gives a YouTube URL and asks to "转录" "做转录稿" "生成转录页面" "中英对照"
  "bilingual transcript" "transcribe this video", or wants a readable HTML transcript with clickable
  timestamps, chapter navigation, highlighted key points, and proper-noun annotations.
  Fetches captions + chapters via yt-dlp, the agent translates and curates, then a script renders the HTML.
---

# YouTube 中英对照转录页生成

把一个 YouTube 链接变成一份单文件 HTML 阅读页：中文为主、英文原文为下方小字，带时间戳跳转、带序号的章节目录、每章中文要点、重点金句高亮、以及专有名词「正文内联点击展开」注释。

## 三步流程

**1. 抓取字幕与章节 → `work.json` 骨架**

```bash
python3 ${SKILL_PATH}/scripts/fetch_transcript.py "<youtube-url>" work.json
```

脚本用 `uvx yt-dlp`（无需全局安装）抓取原语言自动字幕（json3）与 `info.json`（标题、时长、章节），把逐词字幕合并成可读段落、按章节分组，产出待翻译骨架。每个 segment 已填好 `en`，`zh` 留空。

环境注意（脚本已内置重试，但需了解）：
- 依赖浏览器登录态绕过 YouTube 机器人校验——脚本用 `--cookies-from-browser chrome`。Chrome 需已登录 YouTube。
- cookie 提取偶发只取到极少 cookie 而触发 bot 校验，脚本会重试多次；若始终失败，提示用户在 Chrome 里打开一次 YouTube 再重试。
- 解 n-challenge 需要 JS runtime，建议系统装有 `deno`（`brew install deno`）。

**2. 翻译与策展：把 `work.json` 补全为 `spec.json`**

这是本 skill 的核心智力环节，由 agent 完成。读取 `work.json`，**只填充、不改动 `ts`/`en`**，逐项补齐：

- **`meta.title_zh`、`meta.subtitle`、`meta.guest`**：中文标题、副标题（如播客期号）、嘉宾一句话身份。
- **`meta.has_speakers`**：自动字幕**没有**说话人信息 → 保持 `false`、各 segment 的 `speaker` 留空。只有当来源确实区分说话人（见下方「更高质量」）才设 `true` 并填 `speaker`。
- **每个 segment 的 `zh`**：忠实、自然的中文翻译。保留口语节奏；专有名词首次出现用「中文（English）」形式，便于内联注释命中。长视频分批翻译，**务必逐段覆盖、不漏段、不串行错位**（完成后校验每段 `zh` 非空且与 `en` 对应——本类任务最易出的就是漏一句短句导致整体错位一格）。
- **每章 `title_zh` 与 `summary`**：中文章节名；`summary` 为 2–4 条中文要点，提炼该章核心论点（用于章节顶部卡片）。
- **每章挑 1–3 句 `key: true`**：最值得高亮、可直接引用的金句，作为「重点」与「只看重点」的依据。宁缺毋滥。
- **`glossary`**：本视频出现的专有名词，`{term, zh, desc}`。只收**有辨识度的**名词（公司、人物、产品/架构、技术概念、模型/事件），**不要收 the/power 这类常见词**，否则正文会被误标。`desc` 用一句中文解释。注释在正文中文里命中（优先匹配 `zh`，无中文名则匹配 `term`），每词仅标注首次出现。

**3. 渲染 HTML**

```bash
python3 ${SKILL_PATH}/scripts/build_html.py spec.json output.html
```

默认输出放用户易取处（如 `$HOME/Desktop/<slug>.html`），生成后用系统命令打开预览（macOS：`open`）。

## spec.json 结构

```json
{
  "meta": {"title","title_zh","subtitle","channel","guest","duration",
           "upload_date","video_id","url","has_speakers"},
  "chapters": [
    {"title","title_zh","start","summary":["中文要点","..."],
     "segments": [{"ts","sec","speaker","en","zh","key"}]}
  ],
  "glossary": [{"term","zh","desc"}]
}
```

`fetch_transcript.py` 已产出除翻译/要点/术语外的全部字段，agent 在其基础上补全即可。

## 成页功能（已内置于 build_html.py，无需另写）

- 中文主体 + 英文小字淡色；左上「隐藏英文」一键切换纯中文。
- 带**序号**的章节目录（sticky 侧栏），点击跳转；每章标题旁「跳转视频」按钮。
- 时间戳点击直达 YouTube 对应秒数。
- `key` 段落金色高亮 + 「只看重点」筛选。
- 专有名词在正文中文里以虚线 + ⓘ 标注，**点击展开**注释气泡；完整术语表折叠在**页面底部**（不占据开头）。

## 更高质量（可选）

自动字幕无说话人、偶有断句瑕疵。若该创作者在自有网站发布了**官方逐字稿**（常含说话人标注与时间戳，如某些访谈/播客），优先抓取并解析官方稿填入 segments（设 `has_speakers: true`、填 `speaker`），质量显著更好。其余流程（翻译、要点、术语、渲染）不变。
