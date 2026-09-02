# 初始化手册：一次性配好微信本地解密

这份手册指导 **用户亲手** 完成一次性初始化。涉及系统安全设置（SIP）、root、隐私权限（FDA），**agent 只负责引导、给命令、读输出，绝不代替用户改系统安全设置**。

配好后，日常读取只跑 `scripts/wechat.py`，不再需要本手册。

---

## 前置条件

- **macOS + Apple Silicon（arm64）**。本手册的 lldb 寄存器映射按 arm64 调用约定写；Intel Mac 需另行调整。
- **微信 4.x 已登录**，保持登录状态。
- **Homebrew 装了 zstd**：`brew install zstd`（消息正文用 zstd 压缩，解压要用它）。
- **lldb 可用**：随 Xcode Command Line Tools 提供，缺则 `xcode-select --install`。
- 一个工作目录存口令和解密产物，默认 `~/wechat-extract/`（可用环境变量 `WECHAT_EXTRACT_HOME` 覆盖）。

## 铁律（先讲清，别越界）

只做**本地只读 + 本地解密**。绝不自动化操作微信客户端（点击/发消息/非官方协议登录/改数据）。lldb 截口令那步也只是本地读一次内存、用完 `detach`，不属于自动化操作，但非必要不频繁做。守住这条就零封号风险。

## 为什么需要这几步（原理）

微信 4.x 的聊天库是 SQLCipher4 加密的，**解密钥匙不落盘、只在微信运行时的内存里现算**；而且微信 4.1+ 内存里不再缓存"原始 key"，只保留一个**口令(passphrase)**，真正的 key 靠 `PBKDF2-HMAC-SHA512(口令, 各库自己的 salt, 256000 轮)` 临时派生、用完即弃。

所以要拿到口令，必须在**微信"现算 key 的那一刻"**把它截下来——微信在 macOS 上直接调苹果系统库 `CCKeyDerivationPBKDF`，用 lldb 断在这个公开符号上即可，**不需要逆向微信自己的代码**。而读别的进程内存需要突破系统保护，所以要**临时关一次 SIP**。口令只需截一次（除非退出重登/大版本迁移），之后用它离线解密所有库，SIP 可以保持开启——那时靠**完全磁盘访问(FDA)**让工具读到微信容器。

---

## 第 1 步：临时关闭 SIP

**由用户在恢复模式里操作，agent 无法代做。**

1. 完全关机（苹果菜单 → 关机）。
2. 长按电源键不放，直到出现"正在载入启动选项 / Loading startup options"，松手。
3. 点 **选项 Options → 继续**，选管理员账户，输密码。
4. 顶部菜单 **实用工具 Utilities → 终端 Terminal**，运行：

   ```bash
   csrutil disable
   ```

   按提示确认（可能要输 `y` 并再验证一次管理员账户）。
5. 苹果菜单 → 重新启动，正常进系统。回来后可 `csrutil status` 确认显示 `disabled`。

## 第 2 步：用 lldb 截取口令

保持微信登录。让用户在自己的终端里操作（截内存需要 root）。

**2.1 建 lldb 脚本**（本 skill 已自带，直接引用 `${SKILL_PATH}/scripts/wxkey.lldb`；若要放到工作目录也可复制过去）。脚本内容等价于：

```
break set -n CCKeyDerivationPBKDF -c '$w6 == 256000'
break command add
script print("=== PBKDF2(256000) hit: passphrase(x1, len=x2) + salt(x3) ===")
expression -f d -- (unsigned long)$x2
memory read --format x --size 1 --count 64 $x1
memory read --format x --size 1 --count 16 $x3
continue
DONE
process attach --name WeChat --waitfor
continue
```

条件 `$w6 == 256000` 只保留"主 key 派生"那次调用（跳过 2 轮的 HMAC 子钥派生）。arm64 调用约定下：`x1`=口令指针、`x2`=口令长度、`x3`=salt、`w6`=轮数。

**2.2 退出微信并挂 lldb 等它重启**（重启是为了触发一次全新的 key 派生；库已经开着时断点不会再命中）：

```bash
osascript -e 'quit app "WeChat"'; sudo lldb -s "${SKILL_PATH}/scripts/wxkey.lldb"
```

**2.3 触发**：看到 lldb 卡住（在等微信出现）后，**手动启动微信**（点 Dock 图标或 Spotlight），别在这个被 lldb 占用的终端里敲命令。

**2.4 读结果**：微信一起来，脚本会在派生 key 那一刻自动打印若干行。其中 `$x2 = 32` 表示口令 32 字节；`memory read ... $x1` 打印的**前 32 字节**就是口令（同一账号所有库共用一个口令，命中多次都一样）。示例：

```
(unsigned long) $NN = 32
0x...: 0x54 0xde 0xc4 0x35 ...   ← 取前 32 字节，拼成 64 位十六进制
```

按 `Ctrl-C`、`detach`、`quit` 退出 lldb（微信照常用）。

**2.5 存口令**（把上一步拼出的 64 位十六进制填进去）：

```bash
mkdir -p ~/wechat-extract
umask 077
printf '<这里填64位十六进制口令>' > ~/wechat-extract/passphrase.hex
chmod 600 ~/wechat-extract/passphrase.hex
```

> 如果 agent 能读用户的终端（如 tmux pane），可直接抓输出、解析出口令，减少手动复制。口令是敏感数据，别贴到聊天/公开处。

## 第 3 步：恢复 SIP

口令到手，把系统保护开回去（跟第 1 步一样进恢复模式）：

```bash
csrutil enable
```

重启回系统，`csrutil status` 应显示 `enabled`。之后日常解密**不需要再关 SIP**。

## 第 4 步：开启完全磁盘访问（FDA）

SIP 开着时，macOS 隐私保护（TCC）会拦住终端读微信容器（表现为 `Operation not permitted`）。给**真正运行 agent + python 的那个 App / 二进制**开 FDA 即可一劳永逸。

1. **先确认要授权谁**：跑一次工具（`python3 ${SKILL_PATH}/scripts/wechat.py decrypt`），若报"找不到微信数据目录"或 `Operation not permitted`，说明没权限。宿主是谁可看进程祖先链：

   ```bash
   pid=$$; for i in $(seq 1 12); do ps -o pid=,ppid=,comm= -p $pid; ppid=$(ps -o ppid= -p $pid|tr -d ' '); [ "${ppid:-0}" -le 1 ] && break; pid=$ppid; done
   ```

   常见宿主：终端 App（Terminal / iTerm / Ghostty…），或 Claude 桌面 App 内跑 Claude Code 时是那个**小写 `claude`** 的 CLI 二进制（与大写的 `Claude` 桌面 App 是两个独立授权项，要开的是实际跑命令的那个）。

2. 打开**系统设置 → 隐私与安全性 → 完全磁盘访问权限（Full Disk Access）**，找到上一步确认的 App / 二进制，把开关**打开**；列表里没有就点 **+** 手动添加。较新的 macOS 里新开的子进程通常不用重启即可生效；不生效就退出宿主 App 重开。

3. 验证：再跑 `python3 ${SKILL_PATH}/scripts/wechat.py decrypt`，成功解密即通。

**若之前误点过 "Don't Allow"**：macOS 会记住拒绝、不再弹框也不在 FDA 列表显示。用 tccutil 重置该 App 的"访问其它 App 数据"授权记录后再触发（把 `<bundle-id>` 换成宿主的，例如 Claude 桌面版是 `com.anthropic.claudefordesktop`）：

```bash
tccutil reset SystemPolicyAppData <bundle-id>
```

然后重新在 FDA 里打开，或触发一次访问让弹框重新出现。

---

## 完成后：日常怎么用

```bash
python3 ${SKILL_PATH}/scripts/wechat.py decrypt          # 拉最新、解密
python3 ${SKILL_PATH}/scripts/wechat.py groups -n 20     # 看活跃群
python3 ${SKILL_PATH}/scripts/wechat.py dump "群名" --days 3 -o out.md
```

## 什么时候要重做

- **口令失效**（`decrypt` 报解密失败 / 首页魔数不符）：通常是用户退出微信重登或大版本迁移换了口令 → 重做第 1–3 步重新截口令。
- **换了运行 agent 的宿主 App / 终端**：给新宿主重开一次 FDA（第 4 步）。
- FDA 本身是一次性的，SIP 恢复后不影响日常解密。

## 排查

- **lldb 断点不命中**：微信是多进程，可能挂错了子进程；确认按 `--name WeChat` 挂的是主进程。或改用 `sudo lsof | grep message_0.db` 找到持有库的 PID 再 `-p <pid>` 挂。也确认微信重启后确实开库（没停在登录二维码界面）。
- **`task_for_pid` 失败 / 非 root**：截内存要 root（`sudo lldb`）且 SIP 处于关闭状态。
- **微信被卡住不动**：多半是 lldb 还挂着把进程暂停了（`ps -o stat` 显示 `T`）。在 lldb 里 `detach` 再 `quit` 即恢复；不行就强制退出微信重开，无数据损失。
- **`Operation not permitted`**：FDA 没开或开错了对象，见第 4 步。
- **zstd 解压失败 / `<zstd unavailable>`**：没装或找不到 libzstd，`brew install zstd`。
- **导出条数偏少 / 没有最新消息**：`dump` 只读 `plain/`；先 `decrypt` 再 `dump` 才有最新数据。
