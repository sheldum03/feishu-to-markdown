---
name: feishu-to-markdown
description: Use when user provides a Feishu (飞书) document link and wants to convert it to a Markdown file, or mentions "飞书转markdown", "导出飞书文档", "feishu export"
---

# Feishu to Markdown

将飞书文档链接转换为 Markdown 文件保存到桌面。零配置，无需凭证。

## Quick Reference

```bash
# 直接使用（自动降级：SSR → 扫码配置 → API）
python3 ~/.claude/skills/feishu-to-markdown/feishu2md.py <飞书链接>

# 指定输出路径
python3 ~/.claude/skills/feishu-to-markdown/feishu2md.py <飞书链接> ./output.md

# 强制 API 模式（跳过 SSR 尝试）
python3 ~/.claude/skills/feishu-to-markdown/feishu2md.py <飞书链接> --api

# 仅扫码配置（不转换文档）
python3 ~/.claude/skills/feishu-to-markdown/feishu2md.py --setup

# Lark 国际版
python3 ~/.claude/skills/feishu-to-markdown/feishu2md.py --setup --lark
```

支持链接：`/docx/`、`/wiki/`、`/docs/`，含 `feishu.cn` 和 `larksuite.com`。

## 工作原理

默认自动降级，用户无需选择模式：

1. **免凭证 SSR**：Googlebot UA 获取公开文档，零配置
2. **SSR 失败 → 自动扫码配置**：Device Flow OAuth，飞书扫码创建应用，凭证存入 `~/.feishu_config`
3. **API 转换**：用凭证通过飞书开放 API 获取完整文档内容

纯 Python 标准库，无第三方依赖。

## Limitations

- 图片仅保留占位符（`![image]()`），不下载图片文件
- 需要登录才能查看的文档需使用 `--api` 模式
- 表格等复杂嵌入类型输出为纯文本
