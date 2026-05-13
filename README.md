# feishu-to-markdown

飞书文档转 Markdown，单文件，零依赖，自动降级。

## 快速开始

```bash
python3 feishu2md.py https://xxx.feishu.cn/wiki/abc123
```

公开文档直接输出，私有文档自动引导扫码配置，无需手动选模式。

## 工作原理

三层自动降级：

```
SSR 免凭证抓取（公开文档）
  ↓ 失败
扫码配置（自动创建飞书应用，获取凭证）
  ↓
API 模式转换（私有文档）
```

| 模式 | 适用场景 | 依赖 |
|------|---------|------|
| SSR | 公开文档 | 无 |
| 扫码配置 | 首次使用私有文档 | 飞书账号 |
| API | 私有文档 | `~/.feishu_config` |

## 用法

```bash
# 默认（自动降级）
python3 feishu2md.py <飞书链接>

# 指定输出路径
python3 feishu2md.py <飞书链接> ./output.md

# 强制 API 模式
python3 feishu2md.py <飞书链接> --api

# 仅扫码配置（不转换文档）
python3 feishu2md.py --setup

# Lark 国际版
python3 feishu2md.py --setup --lark
```

支持链接类型：`/docx/`、`/wiki/`、`/docs/`，含 `feishu.cn` 和 `larksuite.com`。

## 凭证配置

三种方式（按优先级）：

**1. 扫码自动配置（推荐）**

```bash
python3 feishu2md.py --setup
```

飞书扫码后自动创建应用并保存凭证到 `~/.feishu_config`。

**2. 环境变量**

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
```

**3. 配置文件**

```json
// ~/.feishu_config
{
  "app_id": "cli_xxx",
  "app_secret": "xxx"
}
```

## 支持的文档元素

- 标题（1-9级）、段落、引用、分割线
- 有序/无序列表、待办事项
- 代码块（30+ 语言高亮标识）
- 表格（管道格式）
- 图片占位符、行内样式（加粗/斜体/删除线/行内代码/链接）
- 公式（`$...$`）、Callout 注释块

## 限制

- 图片仅保留占位符，不下载文件
- 复杂嵌入类型（如内嵌表格）输出为纯文本

## 技术细节

- 纯 Python 标准库，无第三方依赖
- SSR 模式通过 Googlebot UA 获取服务端渲染页面，解析嵌入的 `block_map` JSON
- API 模式通过飞书开放平台 DocX API 获取完整 Block 结构
- 扫码配置基于 Device Flow OAuth（逆向自 `@larksuite/openclaw-lark-tools`）

## License

MIT
