# 制图档案

文章里需要信息图、对照表、原理示意图时，对照此档案。先讲品味方向，再讲技术实现。

## 核心品味：图形为主，文字为辅

一张图的观点要由**图形本身**承载——用大小对比、位置关系、图标、留白、连线来表达，而不是把话写满。文字只做必要的标签（标题、轴名、关键节点名），不替图形说话。

- **一张图聚焦一个观点**。不要在一张图里塞多条线索，读者看不过来。
- **不要把成串要点列表、长句塞进图里**。要点列表是文字的活，不是图的活——塞进图里只会干扰、显得拥挤、削弱图形传达的力量。如果内容本质是「几条并列的话」，那它该留在正文段落里，不该硬做成图。
- 判断标准：把图里的文字全删掉，图还能不能大致传达观点？如果完全看不懂，说明这张图在用文字而非图形说话，要重做。

## 默认用 HTML+CSS 画，不要手写 SVG 摆坐标

**做插图、信息图、中文对照表时，默认用 HTML+CSS 画。**

**为什么**：SVG 是绝对坐标系——文字不自动换行、盒子不自动撑大、元素不互相避让，密集文字/卡片/表格极易压线、错位、溢出。HTML 的 flexbox / grid / `table-layout:fixed` 自动排版，**结构上杜绝文字溢出**，稳定且省返工。要的是「稳定产出干净、简洁、整洁的图」——稳 > 天花板。

**怎么选**：
- 盒子 / 卡片 / 分层 / 对照表 / 文字密集 → **HTML+CSS**。
- 纯矢量曲线 / 箭头 / 折线图 / 异形（冰山、环形连线）→ SVG，或在 HTML 里**内嵌** SVG。
- 密集表格务必 `table-layout:fixed` + `<colgroup>` 定列宽，再用截图验证窄屏不挤压。

**配色**（一套扁平色块，作者最认可）：米白底 `#F4F0E9`、藏蓝 `#20324F`、青绿 `#1FA8A0`、琥珀 `#F2A516`、珊瑚 `#EC6A5A`、墨字 `#1B2330`、强调/砖红 `#C24234`。

## 转 PNG 流程（已验证）

微信公众号不支持 SVG，必须转 PNG。机器上一般没装 rsvg/inkscape/cairosvg/PIL，别浪费时间找——直接走 headless Chrome 截图。

1. 写 HTML，根容器固定 `width:1600px`，字体 `"PingFang SC","Heiti SC","Microsoft YaHei",sans-serif`。
2. 量真实高度：用共享 CDP Chrome（开 `file://...`，`evaluate_script` 取根容器 `getBoundingClientRect().height`）。SVG 同理可读 `height=` 属性。
3. 截图：用 `chrome-headless-shell` 跑——
   ```
   chrome-headless-shell --headless --disable-gpu \
     --force-device-scale-factor=2 \
     --window-size=1600,<H> --hide-scrollbars \
     --default-background-color=ffffffff \
     --screenshot=out.png "file://<abs-path>"
   ```
   出 2x（3200px 宽）PNG，中文走系统 PingFang，无需额外装字体。
   `chrome-headless-shell` 二进制一般在 `~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell`（版本号通配，按本机实际目录取；其它平台路径相应不同）。若无，可用本机已装的 headless Chrome / playwright chromium 替代。
