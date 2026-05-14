# IEEE Xplore CDP Automation Reference

## CDP Endpoints

### List all open tabs

```
GET http://127.0.0.1:9222/json/list
```

Returns JSON array of tab objects:

```json
[
  {
    "id": "TAB_ID",
    "type": "page",
    "url": "https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=...",
    "title": "IEEE Xplore Search Results",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/TAB_ID"
  }
]
```

### Get browser version

```
GET http://127.0.0.1:9222/json/version
```

Returns browser info including `Browser`, `Protocol-Version`, `User-Agent`.

## Starting Edge with Remote Debugging

```powershell
# Windows - close all Edge instances first, then:
msedge.exe --remote-debugging-port=9222

# Or create a desktop shortcut with the flag
```

## IEEE Xplore URL Patterns

### Search URL

```
https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={keyword}&ranges={start}_{end}_Year&sortType=relevance
```

### Detail page

```
https://ieeexplore.ieee.org/document/{arnumber}
```

### PDF download (authenticated)

```
https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}
```

### Export citations

```
https://ieeexplore.ieee.org/document/{arnumber}/citations
```

## Key DOM Selectors (IEEE Xplore 2024+)

### Search Results Page

| Element | Selector |
|---------|----------|
| Result item | `xpl-search-results-item` |
| Title link | `h2 a, h3 a, [href*="/document/"]` |
| Authors | `.author a, .authors-info span` |
| Year | `text matching /Year:\s*\d{4}/` |
| Journal | `.publication-title, .publisher-info-container` |
| Next page | `button.next-btn, a[aria-label="Next"]` |
| DOI link | `a[href*="doi.org"]` |

### Detail Page

| Element | Selector |
|---------|----------|
| Title | `h1.document-title span, .document-title-text` |
| Abstract | `div.abstract-text div, xpl-abstract-view` |
| Authors | `xpl-author-info a, .authors-info a.author-link` |
| DOI | `a[href*="doi.org"]` |
| Keywords | `xpl-keywords-item a, .doc-keywords-list a` |
| PDF link | `a[href*="stamp/stamp.jsp"], a[href$=".pdf"]` |
| BibTeX tab | `a:has-text("BibTeX")` |
| RIS tab | `a:has-text("RIS")` |
| Citation count | `.document-ft-metrics-bar span` |

## Login Detection

Check for any of these elements to verify authentication:

- `.user-info`
- `[data-testid="user-menu"]`
- `.login-user-name`
- `a[href*="profile"]`

If none found, the user is not logged in.

## PDF Download Strategy

1. **Preferred**: Navigate to `https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}` and let browser download
2. **Alternative**: Extract cookies from CDP session, use `requests`/`urllib` with Cookie header
3. **Validation**: Check file size >= 50KB and header starts with `%PDF-`

### Cookie Extraction (Playwright)

```python
cookies = page.context.cookies()
# Returns list of {name, value, domain, path, ...}
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "Cannot connect to CDP" | Ensure Edge started with `--remote-debugging-port=9222` |
| "No IEEE tabs found" | Open https://ieeexplore.ieee.org in the debug Edge |
| "Not authenticated" | Sign in to IEEE Xplore in the debug Edge |
| "Response was HTML" | Likely paywall or expired session; re-login |
| "Invalid PDF header" | Download link may be broken; try alternative URL |
| CAPTCHA | Pause automation, alert user to solve manually |

## Troubleshooting Flow

```
1. msedge.exe --remote-debugging-port=9222
   ↓
2. python scripts/cdp_detector.py
   ↓ (if no IEEE tabs)
3. Open https://ieeexplore.ieee.org and sign in
   ↓
4. python scripts/cdp_detector.py (verify)
   ↓
5. python scripts/harvester.py --keyword "..." --count 10
```
