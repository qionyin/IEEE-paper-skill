# IEEE Xplore Harvester —— 学术论文自动化采集工具

基于 Edge 浏览器 CDP 协议的 IEEE Xplore 学术论文批量采集工具。连接到已登录的 Edge，自动搜索、提取元数据、下载 PDF、生成报告。全程本地运行。

## 快速开始

1. 关闭所有 Edge 窗口，以调试模式启动：msedge.exe --remote-debugging-port=9222
2. 在该 Edge 窗口访问 https://ieeexplore.ieee.org 并登录机构账号
3. 安装依赖：pip install playwright websocket-client && playwright install chromium
4. 运行：python scripts/harvester.py --keyword "deep learning" --years 2023-2025 --count 30 --download-pdf
5.或者直接导入codex用skill运行，skill运行也需要执行123
6.建议根据自己情况修改，博主能力有限，这个skill只是针对博主自身情况设计，很多地方都是量身定制，建议将此skill扔给gpt或opus修改成适合自己的

输出默认保存到桌面【论文】文件夹下的 {时间戳}_{关键词} 子目录。

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| --keyword | str | 必填 | 搜索关键词，多词用引号 |
| --years | str | 2020-2025 | 年份范围 |
| --count | int | 50 | 最大论文数 |
| --sort | str | relevance | relevance/newest/oldest/cited |
| --download-pdf | flag | 关闭 | 是否下载 PDF |
| --min-if | float | 0 | 最低影响因子 |
| --output | str | 自动 | 自定义输出目录 |
| --cdp-port | int | 9222 | Edge 调试端口 |

## 使用示例

python scripts/harvester.py --keyword "solid electrolyte" --years 2020-2025 --count 50
python scripts/harvester.py --keyword "5G network slicing" --years 2023-2025 --count 20 --download-pdf
python scripts/harvester.py --keyword "transformer" --years 2024-2025 --count 10 --sort cited --min-if 5.0 --download-pdf

## 输出目录

桌面/论文/{timestamp}_{keyword}/
  metadata/      JSON + CSV 元数据
  pdfs/          PDF 全文
  citations/     BibTeX + RIS 引用
  abstracts/     摘要 TXT
  reports/       HTML 报告 + 统计 + 日志
  urls.csv       论文链接
  pending.csv    失败/待处理列表

## 脚本说明

harvester.py         主入口，编排完整流水线
cdp_detector.py      Edge CDP 浏览器检测与登录验证
ieee_automation.py   IEEE Xplore 搜索、分页、元数据提取
pdf_downloader.py    PDF 下载、重试、校验
storage.py           输出目录与文件管理
reporter.py          HTML 报告与统计
utils.py             日志、重试、公共工具

## 工作流程

1. cdp_detector.py 检测 Edge 调试端口，定位 IEEE 标签页，验证登录
2. 构造搜索 URL，翻页获取论文列表，按 DOI/ARN/URL/标题去重
3. 逐篇打开详情页提取摘要、关键词、参考文献、引用次数、访问状态
4. 检查本地论文库跳过已有 PDF，复用 Cookie 下载，校验后重试最多 3 次
5. 生成交互式 HTML 报告 + 统计 JSON + 运行日志

## 常见问题

无法连接 Edge 调试端口 -> 关闭所有 Edge 后：msedge.exe --remote-debugging-port=9222
未检测到登录状态 -> 在调试窗口访问 ieeexplore.ieee.org 登录
PDF 下载失败 -> 付费/未订阅，记录在 pending.csv
出现验证码 -> 手动在 Edge 窗口完成验证
网络超时 -> 自动重试 3 次（指数退避）
PDF 校验失败 -> 自动重下 1 次
结果重复 -> 内建 DOI/ARN/URL/标题多维去重

## 实用技巧

1. 保持 Edge 窗口可见以确保页面正常加载
2. 用精确关键词避免结果重复
3. 先用 --count 3 测试，再扩大数量
4. 桌面论文库自动跳过已有 PDF
5. citations/ 下 BibTeX 可直接导入 Zotero/EndNote
