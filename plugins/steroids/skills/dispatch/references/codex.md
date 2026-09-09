# Codex

## 当时可用的调用（实测于 2026-08）

探活：

```bash
codex exec --model gpt-5.6-sol "只回答两个字：收到" < /dev/null
```

正式任务：

```bash
codex exec --sandbox danger-full-access --model gpt-5.6-sol \
  -c model_reasoning_effort=xhigh --skip-git-repo-check \
  -o result.md "$(cat prompt.txt)" < /dev/null
```

| 参数 | 当时的作用 |
|---|---|
| `--sandbox danger-full-access` | 本地文件系统完全访问，**不含网络** |
| `-o result.md` | 把最终回复收进文件，后台跑时靠它取结果 |
| `-c model_reasoning_effort=...` | 调推理档位 |
| `--skip-git-repo-check` | 在非 git 目录里跑时需要 |

缺 `< /dev/null` 时卡在 `Reading additional input from stdin...` 一动不动。

宿主 shell 若给 `codex` 配了注入审批/沙箱参数的 alias，照用，不要 `command codex` 绕开。

## 沙箱无网

`danger-full-access` 只放开文件系统，网络仍是断的。缺依赖时它会反复尝试安装直到卡死。

## 生图

Codex CLI **内置 GPT Image 2**。提示词里直接说

> Generate an image and save to /path/to/file.png

它会调用内置的 image generation tool 生成。

**不要让它写 Python 调 OpenAI SDK**：环境里没有 `OPENAI_API_KEY`，一定失败。
Codex 走 ChatGPT Plus 的 OAuth，内置能力不需要额外的 key。
