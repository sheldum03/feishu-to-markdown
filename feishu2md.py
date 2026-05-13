#!/usr/bin/env python3
"""feishu2md - 飞书文档转 Markdown 工具。

用法: python3 feishu2md.py <飞书文档链接> [输出路径]
默认保存到 ~/Desktop/<文档标题>.md

三种模式:
  1. 免凭证模式（默认）: 抓取公开文档 SSR 页面，零配置
  2. API 模式（--api）: 通过飞书开放 API，需要凭证
  3. 扫码配置（--setup）: Device Flow 扫码创建应用，自动获取凭证
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse


# ══════════════════════════════════════════════════════
#  公共工具
# ══════════════════════════════════════════════════════

def parse_url(url):
    """从飞书链接中提取文档类型和 token。"""
    for pat, doc_type in [
        (r"/docx/([a-zA-Z0-9]+)", "docx"),
        (r"/wiki/([a-zA-Z0-9]+)", "wiki"),
        (r"/docs/([a-zA-Z0-9]+)", "docs"),
    ]:
        m = re.search(pat, url)
        if m:
            return doc_type, m.group(1)
    raise ValueError(f"无法识别的飞书链接: {url}")


def save_md(md, title, output_path=None):
    """保存 Markdown 到指定路径或桌面。"""
    if not output_path:
        safe_name = re.sub(r'[/<>:"|?*\\]', "_", title)
        output_path = os.path.expanduser(f"~/Desktop/{safe_name}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已保存: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════
#  模式一：免凭证 SSR 抓取（从嵌入 JSON 提取完整 block 数据）
# ══════════════════════════════════════════════════════

def fetch_ssr(url):
    """用 Googlebot UA 抓取飞书公开文档的 SSR HTML。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Accept": "text/html",
    })
    with urllib.request.urlopen(req) as resp:
        if resp.url and "accounts" in resp.url and "login" in resp.url:
            raise RuntimeError("文档需要登录，无法免凭证访问。请使用 --api 模式。")
        return resp.read().decode("utf-8", errors="replace")


def extract_block_map(html):
    """从 SSR HTML 中提取嵌入的 block_map JSON 数据。"""
    marker = '"block_map":{'
    pos = html.find(marker)
    if pos < 0:
        raise RuntimeError("未找到文档数据，该页面可能不支持免凭证访问。")
    colon_pos = html.find(':', pos + len('"block_map"'))
    json_start = html.find('{', colon_pos)
    depth = 0
    end = json_start
    for end in range(json_start, min(json_start + 500000, len(html))):
        if html[end] == '{':
            depth += 1
        elif html[end] == '}':
            depth -= 1
            if depth == 0:
                break
    return json.loads(html[json_start:end + 1])


def block_text(bdata):
    """从 block data 的 initialAttributedTexts 中提取纯文本。"""
    iat = bdata.get("text", {}).get("initialAttributedTexts", {}).get("text", {})
    return "".join(iat.get(str(i), "") for i in range(len(iat)))


def blocks_to_md(block_map):
    """将 block_map 转换为 Markdown。"""
    # 找到 page block（根节点）
    page_block = None
    for bid, block in block_map.items():
        if block.get("data", {}).get("type") == "page":
            page_block = block
            break
    if not page_block:
        raise RuntimeError("未找到文档根节点。")

    pdata = page_block["data"]
    title = block_text(pdata) or "untitled"
    children = pdata.get("children", [])

    lines = [f"# {title}\n"]
    ordered_seq = 0
    prev_type = ""

    for child_id in children:
        block = block_map.get(child_id, {})
        bdata = block.get("data", {})
        btype = bdata.get("type", "")
        text = block_text(bdata)

        if btype == "ordered":
            ordered_seq = ordered_seq + 1 if prev_type == "ordered" else 1
        prev_type = btype

        if btype == "text":
            lines.append(text)
        elif btype.startswith("heading"):
            level = int(btype[-1]) if btype[-1].isdigit() else 2
            lines.append(f"\n{'#' * level} {text}\n")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "bullet":
            lines.append(f"- {text}")
        elif btype == "ordered":
            lines.append(f"{ordered_seq}. {text}")
        elif btype == "code":
            lines.append(f"\n```\n{text}\n```\n")
        elif btype == "todo":
            done = bdata.get("done", False)
            mark = "[x]" if done else "[ ]"
            lines.append(f"- {mark} {text}")
        elif btype == "image":
            lines.append(f"\n![image]()\n")
        elif btype == "divider":
            lines.append("\n---\n")
        elif text:
            lines.append(text)

    return "\n".join(lines), title


def convert_via_ssr(url, output_path=None):
    """免凭证模式：抓取 SSR → 从嵌入 JSON 提取 block 数据 → Markdown。"""
    print("模式: 免凭证 SSR 抓取")
    html = fetch_ssr(url)
    print(f"获取到 {len(html)} 字节 HTML")

    block_map = extract_block_map(html)
    print(f"提取到 {len(block_map)} 个内容块")

    md, title = blocks_to_md(block_map)
    print(f"文档标题: {title}")

    return save_md(md, title, output_path)


# ══════════════════════════════════════════════════════
#  模式二：API 模式（需凭证）
# ══════════════════════════════════════════════════════

# 运行时由 _set_api_base() 设置，默认飞书公有云
BASE = "https://open.feishu.cn/open-apis"


def _detect_api_base(url):
    """从文档 URL 推断 API 基址。

    标准飞书/Lark → open.feishu.cn / open.larksuite.com
    私有化部署    → 同域名 + /open-apis
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if host.endswith(".feishu.cn") or host == "feishu.cn":
        return "https://open.feishu.cn/open-apis"
    if host.endswith(".larksuite.com") or host == "larksuite.com":
        return "https://open.larksuite.com/open-apis"
    # 私有化部署
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}/open-apis"


def _detect_domain_key(url):
    """从文档 URL 提取域名标识，用于按域名查找凭证。"""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if host.endswith(".feishu.cn"):
        return "feishu"
    if host.endswith(".larksuite.com"):
        return "lark"
    # 私有化：去掉租户子域名前缀，取主域名
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else host


def _set_api_base(url):
    """根据文档 URL 设置全局 API 基址，返回域名标识。"""
    global BASE
    BASE = _detect_api_base(url)
    return _detect_domain_key(url)


def api_request(method, path, token=None, data=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"API 请求失败 [{e.code}]: {err_body}")


def load_config(domain_key=None):
    """加载凭证。优先级：环境变量 > 按域名配置 > 默认配置。

    ~/.feishu_config 支持 domains 字段存放私有化部署凭证：
    {
      "app_id": "默认",
      "app_secret": "默认",
      "domains": {
        "xfchat.iflytek.com": {"app_id": "xxx", "app_secret": "xxx"}
      }
    }
    """
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if app_id and app_secret:
        return app_id, app_secret
    config_path = os.path.expanduser("~/.feishu_config")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        # 私有化部署：只用域名专属凭证，不回退到默认
        if domain_key and domain_key not in ("feishu", "lark"):
            dcfg = cfg.get("domains", {}).get(domain_key, {})
            return dcfg.get("app_id", ""), dcfg.get("app_secret", "")
        return cfg.get("app_id", ""), cfg.get("app_secret", "")
    return "", ""


def get_tenant_token(app_id, app_secret):
    r = api_request("POST", "/auth/v3/tenant_access_token/internal",
                    data={"app_id": app_id, "app_secret": app_secret})
    if r.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {r.get('msg', r)}")
    return r["tenant_access_token"]


def resolve_wiki(wiki_token, token):
    r = api_request("GET", "/wiki/v2/spaces/get_node", token,
                    params={"token": wiki_token})
    if r.get("code") != 0:
        raise RuntimeError(f"解析知识库失败: {r.get('msg', r)}")
    node = r["data"]["node"]
    return node["obj_token"], node.get("obj_type", "docx")


def get_doc_info(doc_id, token):
    r = api_request("GET", f"/docx/v1/documents/{doc_id}", token)
    if r.get("code") != 0:
        raise RuntimeError(f"获取文档信息失败: {r.get('msg', r)}")
    return r.get("data", {}).get("document", {})


def get_all_blocks(doc_id, token):
    blocks = []
    page_token = None
    while True:
        params = {"page_size": "500"}
        if page_token:
            params["page_token"] = page_token
        r = api_request("GET", f"/docx/v1/documents/{doc_id}/blocks",
                        token, params=params)
        if r.get("code") != 0:
            raise RuntimeError(f"获取文档内容失败: {r.get('msg', r)}")
        blocks.extend(r.get("data", {}).get("items", []))
        if not r.get("data", {}).get("has_more"):
            break
        page_token = r["data"].get("page_token")
    return blocks


CODE_LANG = {
    0: "", 1: "plaintext", 7: "bash", 8: "c", 10: "cpp",
    13: "css", 16: "dockerfile", 20: "go", 24: "html", 25: "java",
    26: "javascript", 27: "json", 29: "kotlin", 34: "markdown",
    41: "php", 45: "python", 47: "ruby", 48: "rust", 54: "sql",
    55: "swift", 57: "typescript", 60: "xml", 61: "yaml",
}


def render_text(elements):
    if not elements:
        return ""
    parts = []
    for el in elements:
        if "text_run" in el:
            tr = el["text_run"]
            text = tr.get("content", "")
            style = tr.get("text_element_style", {})
            if style.get("inline_code"):
                text = f"`{text}`"
            else:
                if style.get("bold"):
                    text = f"**{text}**"
                if style.get("italic"):
                    text = f"*{text}*"
                if style.get("strikethrough"):
                    text = f"~~{text}~~"
            if style.get("link"):
                href = style["link"].get("url", "")
                try:
                    href = urllib.parse.unquote(href)
                except Exception:
                    pass
                text = f"[{text}]({href})"
            parts.append(text)
        elif "equation" in el:
            parts.append(f"${el['equation'].get('content', '')}$")
    return "".join(parts)


def get_block_text(block, key):
    return render_text(block.get(key, {}).get("elements", []))


def convert_blocks(blocks, title=""):
    block_map = {b["block_id"]: b for b in blocks}
    lines = []
    if title:
        lines.append(f"# {title}\n")

    ordered_seq = 0
    prev_type = 0

    for block in blocks:
        bt = block.get("block_type", 0)
        if bt == 13:
            ordered_seq = ordered_seq + 1 if prev_type == 13 else 1
        prev_type = bt

        if bt == 1:
            continue
        elif bt == 2:
            lines.append(get_block_text(block, "text"))
        elif 3 <= bt <= 11:
            level = bt - 2
            key_map = {3: "heading1", 4: "heading2", 5: "heading3",
                       6: "heading4", 7: "heading5", 8: "heading6",
                       9: "heading7", 10: "heading8", 11: "heading9"}
            lines.append(f"\n{'#' * level} {get_block_text(block, key_map[bt])}\n")
        elif bt == 12:
            lines.append(f"- {get_block_text(block, 'bullet')}")
        elif bt == 13:
            lines.append(f"{ordered_seq}. {get_block_text(block, 'ordered')}")
        elif bt == 14:
            code_block = block.get("code", {})
            text = render_text(code_block.get("elements", []))
            lang_id = code_block.get("style", {}).get("language", 0)
            lang = CODE_LANG.get(lang_id, "") if isinstance(lang_id, int) else str(lang_id)
            lines.append(f"\n```{lang}\n{text}\n```\n")
        elif bt == 15:
            lines.append(f"> {get_block_text(block, 'quote')}")
        elif bt == 17:
            todo = block.get("todo", {})
            text = render_text(todo.get("elements", []))
            mark = "[x]" if todo.get("style", {}).get("done") else "[ ]"
            lines.append(f"- {mark} {text}")
        elif bt == 19:
            lines.append("\n---\n")
        elif bt == 20:
            token = block.get("image", {}).get("token", "")
            lines.append(f"\n![image](feishu-image:{token})\n")
        elif bt == 22:
            table = block.get("table", {})
            prop = table.get("property", {})
            rows, cols = prop.get("row_size", 0), prop.get("column_size", 0)
            cells = table.get("cells", [])
            if rows > 0 and cols > 0 and cells:
                lines.append("")
                for r_idx in range(rows):
                    row_texts = []
                    for c_idx in range(cols):
                        cid = cells[r_idx][c_idx] if r_idx < len(cells) and c_idx < len(cells[r_idx]) else ""
                        cell_content = ""
                        if cid and cid in block_map:
                            parts = []
                            for child_id in block_map[cid].get("children", []):
                                if child_id in block_map:
                                    cb = block_map[child_id]
                                    for key in ["text", "heading1", "heading2", "heading3", "bullet", "ordered"]:
                                        if key in cb:
                                            parts.append(render_text(cb[key].get("elements", [])))
                                            break
                            cell_content = " ".join(parts)
                        row_texts.append(cell_content.replace("|", "\\|"))
                    lines.append("| " + " | ".join(row_texts) + " |")
                    if r_idx == 0:
                        lines.append("| " + " | ".join(["---"] * cols) + " |")
                lines.append("")
        elif bt == 23:
            continue
        elif bt == 26:
            lines.append("> **Note**")
            for cid in block.get("children", []):
                if cid in block_map:
                    cb = block_map[cid]
                    for key in ["text", "heading1", "heading2", "heading3"]:
                        if key in cb:
                            lines.append(f"> {render_text(cb[key].get('elements', []))}")
                            break
        else:
            for key, val in block.items():
                if isinstance(val, dict) and "elements" in val:
                    text = render_text(val["elements"])
                    if text:
                        lines.append(text)
                    break

    return "\n".join(lines)


def convert_via_api(url, output_path=None):
    """API 模式：需要飞书凭证。自动检测私有化部署域名。"""
    domain_key = _set_api_base(url)
    print(f"API 基址: {BASE}")

    app_id, app_secret = load_config(domain_key)
    if not app_id or not app_secret:
        print("错误: API 模式需要凭证。请创建 ~/.feishu_config 或设置环境变量。")
        sys.exit(1)

    doc_type, doc_token = parse_url(url)
    print(f"模式: API | 文档类型: {doc_type}, token: {doc_token}")

    access_token = get_tenant_token(app_id, app_secret)
    print("已获取访问令牌")

    doc_id = doc_token
    if doc_type == "wiki":
        doc_id, _ = resolve_wiki(doc_token, access_token)
        print(f"知识库文档实际 ID: {doc_id}")

    doc_info = get_doc_info(doc_id, access_token)
    title = doc_info.get("title", "untitled")
    print(f"文档标题: {title}")

    blocks = get_all_blocks(doc_id, access_token)
    print(f"共获取 {len(blocks)} 个内容块")

    md = convert_blocks(blocks, title)
    return save_md(md, title, output_path)


# ══════════════════════════════════════════════════════
#  模式三：Device Flow 扫码配置（逆向自 @larksuite/openclaw-lark-tools）
# ══════════════════════════════════════════════════════

FEISHU_ACCOUNTS_BASE = "https://accounts.feishu.cn"
LARK_ACCOUNTS_BASE = "https://accounts.larksuite.com"
_DEVICE_FLOW_PATH = "/oauth/v1/app/registration"
_CONFIG_PATH = os.path.expanduser("~/.feishu_config")


def _device_flow_post(domain, **fields):
    """向 Device Flow 端点发送 form-urlencoded POST。

    注意：poll 阶段，authorization_pending 等状态通过 HTTP 400 + JSON body 返回，
    需要解析响应体而非直接抛异常。
    """
    base = LARK_ACCOUNTS_BASE if domain == "lark" else FEISHU_ACCOUNTS_BASE
    url = base + _DEVICE_FLOW_PATH
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError(f"Device Flow 请求失败 [{e.code}]: {body}")


def setup_via_qr(domain="feishu"):
    """Device Flow 扫码创建飞书应用并保存凭证到 ~/.feishu_config。

    三步流程：
      1. init  → 握手
      2. begin → 获取二维码 URL + device_code
      3. poll  → 轮询直到用户扫码完成
    """
    print(f"=== 飞书扫码配置 (domain: {domain}) ===\n")

    # Step 1: init
    _device_flow_post(domain, action="init")

    # Step 2: begin → 获取二维码
    begin_resp = _device_flow_post(
        domain,
        action="begin",
        archetype="PersonalAgent",
        auth_method="client_secret",
        request_user_info="open_id",
    )
    device_code = begin_resp.get("device_code")
    qr_url = begin_resp.get("verification_uri_complete", "")
    interval = begin_resp.get("interval", 5)
    expire_in = begin_resp.get("expire_in", 600)

    if not device_code:
        raise RuntimeError(f"begin 未返回 device_code: {begin_resp}")

    print("请用飞书扫描以下链接中的二维码（或在浏览器中打开）：")
    print(f"\n  {qr_url}\n")
    print(f"等待扫码授权（{expire_in}s 内有效）...\n")

    # Step 3: poll
    max_attempts = expire_in // interval + 1
    for attempt in range(1, max_attempts + 1):
        result = _device_flow_post(domain, action="poll", device_code=device_code)

        client_id = result.get("client_id", "")
        client_secret = result.get("client_secret", "")
        if client_id and client_secret:
            # 保存凭证
            config = {"app_id": client_id, "app_secret": client_secret}
            user_info = result.get("user_info", {})
            if isinstance(user_info, dict):
                brand = user_info.get("tenant_brand", "")
                if brand:
                    config["domain"] = brand
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"授权成功！凭证已保存到 {_CONFIG_PATH}")
            print(f"  app_id: {client_id}")
            print(f"\n现在可以使用 --api 模式转换私有文档了。")
            return config

        error = result.get("error", "")
        if error in ("expired_token", "access_denied"):
            raise RuntimeError(f"授权失败: {error}")
        if error == "slow_down":
            interval += 5

        time.sleep(interval)

    raise RuntimeError("扫码超时，请重试。")


# ══════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════

def _ensure_credentials(domain, domain_key=None):
    """确保凭证可用，无凭证时自动触发扫码配置。

    私有化部署不支持 Device Flow 扫码，需手动配置。
    """
    app_id, app_secret = load_config(domain_key)
    if app_id and app_secret:
        return
    is_private = domain_key and domain_key not in ("feishu", "lark")
    if is_private:
        print(f"错误: 私有化部署 ({domain_key}) 需要手动配置凭证。")
        print(f"请在 ~/.feishu_config 中添加:")
        print(f'  {{"domains": {{"{domain_key}": {{"app_id": "xxx", "app_secret": "xxx"}}}}}}')
        sys.exit(1)
    print("未找到凭证，启动扫码配置...\n")
    setup_via_qr(domain)
    print()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("用法: python3 feishu2md.py <飞书文档链接> [输出路径] [--api] [--setup]")
        print()
        print("默认自动降级: 先尝试免凭证抓取，失败则自动切换 API 模式（无凭证时引导扫码）")
        print()
        print("选项:")
        print("  --api    强制 API 模式（跳过免凭证尝试）")
        print("  --setup  仅扫码配置，不转换文档")
        print("  --lark   使用 Lark 国际版")
        print()
        print("示例:")
        print("  python3 feishu2md.py https://xxx.feishu.cn/wiki/abc123")
        print("  python3 feishu2md.py https://xxx.feishu.cn/docx/abc123 ./out.md --api")
        print("  python3 feishu2md.py --setup")
        sys.exit(0)

    use_api = "--api" in sys.argv
    use_setup = "--setup" in sys.argv
    use_lark = "--lark" in sys.argv
    domain = "lark" if use_lark else "feishu"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    try:
        # --setup: 仅配置凭证
        if use_setup:
            setup_via_qr(domain)
            return

        url = args[0] if args else None
        if not url:
            print("错误: 请提供飞书文档链接", file=sys.stderr)
            sys.exit(1)

        output_path = args[1] if len(args) > 1 else None

        # 从 URL 预检测域名信息
        domain_key = _detect_domain_key(url)
        if domain_key not in ("feishu", "lark"):
            domain = domain_key  # 私有化部署

        # --api: 强制 API 模式
        if use_api:
            _ensure_credentials(domain, domain_key)
            convert_via_api(url, output_path)
            return

        # 默认: SSR → API 自动降级
        try:
            convert_via_ssr(url, output_path)
        except (RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"\n免凭证模式失败（{e}），自动切换 API 模式...\n")
            _ensure_credentials(domain, domain_key)
            convert_via_api(url, output_path)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
