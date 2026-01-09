# dev-cycle

一个自动化的开发-验收反馈循环系统，通过持续迭代确保开发工作满足需求标准。

## 简介

dev-cycle 是一个 Claude Code 插件,通过两个专门的 AI agent（developer 和 evaluator）协同工作，建立起一个自动化的开发反馈循环。它能够：

- 自动执行开发任务
- 对开发结果进行客观验收测试
- 根据验收反馈持续迭代改进
- 记录完整的开发和验收过程

## 核心价值

- **自动化迭代**：无需人工干预，自动完成多轮开发-验收循环
- **质量保障**：通过明确的验收标准确保交付质量
- **过程透明**：完整记录每一轮的工作报告和验收报告，可追溯
- **需求驱动**：强制要求明确的验收标准，避免需求不清晰

## 架构

```
用户
  │
  ├─> /task-init  创建任务和需求文档
  │       ↓
  │   requirement.md
  │
  └─> /task-run   启动自动化循环
          │
          ├─> developer agent   执行开发工作
          │       ↓
          │   work-report.md    工作报告
          │       ↓
          ├─> evaluator agent   执行验收测试
          │       ↓
          │   eval-report.md    验收报告
          │       ↓
          └─> 判断结果
                  ├─> 通过 → 结束
                  └─> 未通过 → 继续下一轮（最多 20 轮）
```

## 安装

1. 确保已安装 Claude Code CLI
2. 克隆或复制此插件到 Claude Code 插件目录：
```bash
# 复制到 Claude Code 插件目录
cp -r dev-cycle ~/.claude/plugins/
```

3. 重启 Claude Code 或重新加载插件

## 使用方法

### 第一步：创建任务和需求文档

使用 `/task-init` 命令创建新任务：

```bash
/task-init user-authentication
```

该命令会：
1. 创建任务目录 `docs/user-authentication/`
2. 通过交互式对话收集需求信息
3. 生成 `requirement.md` 需求文档

**重要**：必须明确定义验收标准，例如：
- Playwright 测试用例
- API 接口测试步骤
- 单元测试要求
- 手动验证清单

### 第二步：启动自动化开发循环

```bash
/task-run user-authentication
```

该命令会自动：
1. 读取需求文档
2. 启动 developer agent 执行开发
3. 启动 evaluator agent 进行验收
4. 根据验收结果决定是否继续迭代
5. 最多迭代 20 轮，直到通过或达到上限

## 工作流程示例

```
第 1 轮:
  → developer 执行开发，生成 202501101430-work-report-sonnet.md
  → evaluator 执行验收，生成 202501101445-eval-report-sonnet.md
  → 结果: ❌ 未通过 (测试失败)

第 2 轮:
  → developer 根据验收反馈修复问题
  → evaluator 重新验收
  → 结果: ❌ 未通过 (部分功能缺失)

第 3 轮:
  → developer 补充缺失功能
  → evaluator 最终验收
  → 结果: ✅ 通过

任务完成！总共迭代 3 轮
```

## 输出文件结构

每个任务会在 `docs/{task-name}/` 目录下生成以下文件：

```
docs/user-authentication/
├── requirement.md                       # 需求文档（手动创建）
├── 202501101430-work-report-sonnet.md  # 第 1 轮工作报告
├── 202501101445-eval-report-sonnet.md  # 第 1 轮验收报告
├── 202501101500-work-report-sonnet.md  # 第 2 轮工作报告
├── 202501101515-eval-report-sonnet.md  # 第 2 轮验收报告
└── ...
```

文件命名格式：`{yyMMddHHmm}-{report-type}-{model}.md`

## Agent 说明

### Developer Agent
- **职责**：执行开发任务（编码、测试、调试）
- **输入**：需求文档 + 上一轮的验收报告（如有）
- **输出**：工作报告，记录完成的工作和遇到的问题
- **原则**：专注完成需求，编写可验证的代码

### Evaluator Agent
- **职责**：执行验收测试，客观评估开发成果
- **输入**：需求文档 + 最新的工作报告
- **输出**：验收报告，明确标注通过/未通过
- **原则**：只验收不开发，测试失败即停止

## 配置选项

可以在插件中修改以下参数（在 `/task-run` 命令文件中）：

```javascript
const MAX_ITERATIONS = 20;        // 最大循环次数
const TASK_BASE_DIR = 'docs';     // 任务目录根路径
const DEFAULT_MODEL = 'sonnet';   // 默认模型
```

## 最佳实践

1. **明确验收标准**：在 requirement.md 中清晰定义可执行的验收标准
2. **合理拆分任务**：复杂功能建议拆分成多个独立任务
3. **定期检查报告**：查看历史报告了解迭代过程
4. **控制任务规模**：避免单个任务过大导致难以收敛

## 注意事项

- 每个任务最多迭代 20 轮，超过上限会自动终止
- 验收标准必须可执行和可测试
- 所有报告以 Markdown 格式存储，便于版本控制
- 建议将 `docs/` 目录纳入 git 管理

## 适用场景

- 功能开发：实现新功能并通过测试
- Bug 修复：修复问题直到测试通过
- 重构任务：重构代码并确保功能不变
- 技术探索：尝试不同实现方案直到满足要求

## 未来计划

- [ ] 支持多模型配置（developer 和 evaluator 使用不同模型）
- [ ] 并行任务管理
- [ ] HTML 格式的可视化报告
- [ ] 中断和恢复机制

## 许可证

MIT

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**版本**：1.0.0
**创建日期**：2026-01-10
