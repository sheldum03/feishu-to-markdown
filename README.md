# feishu-to-markdown

飞书文档转 Markdown，单文件，零依赖，自动降级。支持公有云和私有化部署。

## 快速开始

```bash
python3 feishu2md.py https://xxx.feishu.cn/wiki/abc123
```

公开文档直接输出，私有文档自动引导扫码配置，无需手动选模式。

## 工作原理

三层自动降级：

```
SSR 免凭证抓取（公开文档）
  ↓ 失败（需登录 / 403）
检查凭证 → 无凭证？ → 飞书扫码配置 / 私有化部署交互输入
  ↓
API 模式转换（私有文档）
```

| 模式 | 适用场景 | 依赖 |
|------|---------|------|
| SSR | 公开文档 | 无 |
| 扫码配置 | 飞书/Lark 首次使用 | 飞书账号 |
| 交互输入 | 私有化部署首次使用 | app_id + app_secret |
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

支持链接类型：`/docx/`、`/wiki/`、`/docs/`。

支持域名：`feishu.cn`、`larksuite.com`、任意私有化部署域名。

## 凭证配置

### 飞书 / Lark 公有云

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

### 私有化部署

首次访问私有化部署链接时，工具会自动提示输入 `app_id` 和 `app_secret`，输入后自动保存，下次无需重复。

凭证按域名隔离存储：

```json
// ~/.feishu_config
{
  "app_id": "飞书公有云凭证",
  "app_secret": "...",
  "domains": {
    "xfchat.iflytek.com": {
      "app_id": "讯飞私有化凭证",
      "app_secret": "..."
    },
    "other.company.com": {
      "app_id": "其他部署凭证",
      "app_secret": "..."
    }
  }
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
- 私有化部署自动从文档 URL 推断 API 基址（同域名 + `/open-apis`）

## License

MIT
