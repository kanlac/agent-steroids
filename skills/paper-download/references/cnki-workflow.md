# CNKI (知网) Workflow

> Tool names below (e.g., `browser_navigate`, `browser_evaluate`) are from `@playwright/mcp`.
> Discover actual tool names from the connected MCP at runtime and use the closest match.

## Prerequisites

1. Agent Chrome running on port 9225 (call `check_port`)
2. User logged into CNKI in Agent Chrome profile
3. Playwright MCP connected (without `--isolated` flag — must share login cookies)

## Login Verification

```
browser_navigate → https://www.cnki.net
browser_snapshot → look for login indicator
```

**Logged in indicators:**
- Username/avatar visible in top navigation
- No "登录" / "注册" prominent buttons

**Not logged in:**
- Stop immediately
- Tell user: "知网登录已失效，请在 Agent Chrome 窗口中访问 https://www.cnki.net 重新登录"
- Wait for user confirmation before retrying

## Search Flow

1. Navigate to search page:
   ```
   browser_navigate → https://kns.cnki.net/kns8s/search
   ```

2. Fill search box:
   ```
   browser_fill → input#txt_SearchText → "{query}"
   ```

3. Click search:
   ```
   browser_click → button.search-btn (or input.btnSearch)
   ```

4. Wait for results:
   ```
   browser_wait_for → .result-table-list (timeout 10s)
   ```

5. Read results:
   ```
   browser_snapshot → extract paper titles, authors, sources
   ```

## Download Flow

1. Click target paper title link:
   ```
   browser_click → paper title link
   ```

2. Wait for detail page:
   ```
   browser_wait_for → .doc-top (or .wx-tit)
   ```

3. Find PDF download button:
   ```
   browser_snapshot → look for "PDF下载" link/button
   ```
   Common selectors: `a#pdfDown`, `a[href*="download"]`, link with text "PDF下载"

4. Click download:
   ```
   browser_click → PDF download link
   ```

5. If only CAJ available:
   - Inform user: "该论文仅提供 CAJ 格式，无 PDF 可下载"
   - Suggest alternatives

## CAPTCHA Handling

CNKI uses Tencent slider CAPTCHA.

**Detection:** After any action, check:
```
browser_evaluate → document.querySelector('#tcaptcha_transform_dy')?.getBoundingClientRect().top >= 0
```

If true (CAPTCHA visible):
- Take screenshot for user reference
- Tell user: "出现验证码，请在 Agent Chrome 窗口中手动完成滑块验证"
- Wait for user confirmation
- Retry the previous action

## Advanced: Batch Export

For multiple papers from search results:
1. Use `browser_evaluate` to check checkboxes for desired papers
2. Click batch export button
3. This avoids navigating to each paper individually

## Error Scenarios

| Error | Detection | Response |
|-------|-----------|----------|
| Not logged in | "请登录" text on page | Ask user to login |
| No permission | "没有该资源的使用权限" | "账户没有下载权限" |
| CAPTCHA | tcaptcha element visible | Ask user to solve |
| Paper not found | Empty result list | Suggest alternate search terms |
| Network timeout | Page load timeout | Retry once, then report |
| CAJ only | No PDF button, only CAJ | Inform user, suggest alternatives |
