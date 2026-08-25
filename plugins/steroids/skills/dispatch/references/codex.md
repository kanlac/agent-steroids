# Codex

**参数和数值都带日期，会过期；调用方式以你当下 `--help` 看到的为准。**
记录它们是因为「问题长什么样」比「用哪个 flag」更耐久——参数改名了，坑还在。

## 当时可用的调用（实测于 2026-08）

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

缺 `< /dev/null` 时的具体表现是卡在 `Reading additional input from stdin...` 一动不动。

## 沙箱禁网

`danger-full-access` 给的是文件系统权限，网络仍然是断的。所以：

- 先在宿主机把依赖装好。
- 提示词里明确写「禁止执行任何联网命令；缺少依赖时只报出包名，不要尝试安装」。
  否则它会反复尝试 `pip install` 然后卡在那里。

## 并发

多个实例同时写一个仓库会互相覆盖。做法是每个实例一个独立工作目录；
只读/调研类任务干脆放在仓库之外跑，结果用 `-o` 收到文件里。

## 生图

Codex CLI **内置 GPT Image 2**。提示词里直接说

> Generate an image and save to /path/to/file.png

它会调用内置的 image generation tool 生成。

**不要让它写 Python 调 OpenAI SDK**——环境里没有 `OPENAI_API_KEY`，一定失败。
Codex 走 ChatGPT Plus 的 OAuth，内置能力不需要额外的 key。
