# OpenCode

## 先确定 provider 与模型

先用 `opencode models` 和 `opencode auth list` 看哪些 provider
有凭证，选定后再查它的详情：

```bash
DISPATCH_PROVIDER_ID="replace-with-provider-id"
opencode models "$DISPATCH_PROVIDER_ID" --verbose
```

从输出读取模型 ID、输入输出上限和 `variants`。如用户未指定模型，选型参考 `batch-orchestration.md`；
清单里有不代表能调用，选中后用下文的探活确认。

## 推理档位（variant）

OpenCode 通常把推理档位称为 **variant**。先检查目标模型的有效配置：若 `variants` 为空或没有目标档位，
`--variant` 可能被忽略，也可能由 provider 拒绝，不能仅凭退出码判断它已生效。

需要自定义档位时，在当前环境实际使用的 OpenCode 配置中为对应 provider 和模型声明 variants。例如：

```jsonc
"provider-id": {
  "models": {
    "model-id": {
      "variants": {
        "low":  { "reasoningEffort": "low" },
        "high": { "reasoningEffort": "high" }
      }
    }
  }
}
```

字段名和可用值取决于当前 OpenCode schema 与 provider。常见配置使用 `reasoningEffort`，但服务端可能只接受
部分档位；`xhigh` 不可用时按统一标尺向下映射到 `high`。用有效配置输出、机器可读事件、请求日志或一次可控的
真实调用确认档位确实进入请求，不把某份个人配置的结果推广到其他环境。

## 调用形状

```bash
DISPATCH_PROVIDER_ID="replace-with-provider-id"
DISPATCH_MODEL_ID="replace-with-model-id"

# 探活
opencode run --pure -m "$DISPATCH_PROVIDER_ID/$DISPATCH_MODEL_ID" \
  "只回答两个字：收到" < /dev/null

# 正式任务；按当前 --help 决定是否使用 --auto
opencode run --pure -m "$DISPATCH_PROVIDER_ID/$DISPATCH_MODEL_ID" --format json \
  "$(cat prompt.txt)" < /dev/null > events.jsonl 2> stderr.txt
```

| 参数 | 常见用途 |
|---|---|
| `--pure` | 不加载外部插件，减少启动阶段变量；需要 MCP 时不要使用 |
| `--auto` | 在当前版本支持且任务已获相应权限时，自动批准未被显式拒绝的操作 |
| `--format json` | 保存工具调用、步骤结束原因和 token 信息 |
| `-s` / `--session <id>` | 显式续指定会话；比依赖“当前目录最近会话”更适合多任务环境 |
| `--fork` | 续之前先分叉；同一上下文上要分头做两个方向时配合 `-s` 使用 |

## 权限与会话

外部目录、网络和写入权限由当前配置决定。出现 `permission requested`、`auto-rejecting` 或等价事件时，按实际
权限策略处理，不假设所有安装都支持同一批准参数。

### 续跑

每条 `--format json` 事件都带 `sessionID`。派发时从第一条取出并落盘，中断、追加指令或复审同一 HEAD 时
用 `-s <id>` 续上，不新起会话；`--pure`、`--auto` 可同时使用。

```bash
opencode run --pure --auto -m "$DISPATCH_PROVIDER_ID/$DISPATCH_MODEL_ID" --format json \
  -s "$SESSION_ID" "追加指令" < /dev/null > events2.jsonl 2> stderr2.txt
```

`opencode session` 列出和管理会话，`opencode export <id>` 导出 JSON 归档。

同一会话的续问保持串行。等上一进程退出并确认事件流已正常停止后再续；残轮状态不明时导出会话检查，或新开
会话。并行写代码时为每份工作使用独立 worktree 或等价隔离环境。

## 输出上限与静默结束

有效单步输出上限可能同时受模型、provider、OpenCode 版本和环境配置约束。某些版本还支持
`OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`；只有当前版本文档或行为确认该变量生效时才使用它。

推理 token 可能计入单步输出预算。若任务退出码为 0 但没有结果，检查事件流最后一步：

| 证据 | 更可能的原因 | 处理方向 |
|---|---|---|
| `reason=length` 或等价字段 | 单步输出或推理触顶 | 调整有效上限、降低 effort、缩小单步任务或换模型 |
| 权限拒绝事件 | 工具或路径未获授权 | 修正权限或缩小任务范围 |
| 明确的 quota / rate-limit 错误 | provider 配额或限流 | 等待重置、换可用 provider，或降低并发 |
| `--variant` 无报错但行为不变 | 档位没有进入有效配置或请求 | 检查 `variants`、schema 和请求证据 |

不要把固定时间窗口、错误文本或 token 数写成跨 provider 规律；只按当前运行留下的证据判断。
