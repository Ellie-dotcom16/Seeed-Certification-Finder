# -*- coding: utf-8 -*-
"""
Seeed Studio 认证查询服务
===========================
提供 Web 界面 + REST API + 飞书机器人集成 + Excel 导出。

启动：
  python app.py                    # 默认 0.0.0.0:5000（内网可访问）
  python app.py --port 8080        # 指定端口
  python app.py --host 0.0.0.0 --port 5000

API：
  GET /api/query?sku=114993117        -> JSON 认证信息
  GET /api/search?name=XIAO           -> 按名称模糊搜索
  GET /api/stats                       -> 数据库统计
  GET /api/export                      -> 下载 Excel 认证映射表
  POST /feishu/webhook                 -> 飞书事件回调
"""

import argparse
import io
import json
import os
import socket
import sqlite3
import tempfile
import requests as http_requests
from flask import Flask, request, jsonify, render_template, send_file

from scraper import (
    init_db, get_product, is_fresh, scrape_single,
    extract_product_data, fetch_page, DB_PATH,
    CERT_TYPE_NAMES, CACHE_HOURS, HEADERS,
)
from export import generate_excel

app = Flask(__name__)

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")


# ============================================================
# 工具函数
# ============================================================
def get_local_ip():
    """获取本机内网 IP 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def query_sku(sku):
    """查询 SKU 认证信息：先查数据库，没有则在线抓取"""
    conn = init_db()
    sku = sku.strip()

    if is_fresh(conn, sku):
        product = get_product(conn, sku)
        if product:
            conn.close()
            return product

    conn.close()
    product = scrape_single(sku)
    return product


def format_text(product):
    """将认证信息格式化为纯文本（供飞书消息使用）"""
    if not product:
        return "未找到该 SKU 的信息。"
    lines = []
    lines.append(f"SKU: {product['sku']}")
    if product.get("name"):
        lines.append(f"产品: {product['name']}")
    if product.get("cert_text"):
        lines.append(f"认证: {product['cert_text']}")
    certs = product.get("certifications", [])
    if certs:
        lines.append("")
        lines.append("认证文件：")
        for c in certs:
            lines.append(f"  [{c['name']}]")
            lines.append(f"  {c['pdf_url']}")
    else:
        lines.append("未找到认证 PDF 文件。")
    if product.get("datasheet_url"):
        lines.append(f"\n产品规格书: {product['datasheet_url']}")
    if product.get("url"):
        lines.append(f"产品页面: {product['url']}")
    return "\n".join(lines)


# ============================================================
# Web 界面
# ============================================================
# ============================================================
# 访问统计（埋点）
@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# REST API
# ============================================================
@app.route("/api/query")
def api_query():
    sku = request.args.get("sku", "").strip()
    if not sku:
        return jsonify({"error": "请提供 sku 参数"}), 400
    product = query_sku(sku)
    if not product or (not product.get("certifications") and not product.get("cert_text")):
        return jsonify({
            "sku": sku,
            "found": False,
            "message": "未找到该 SKU 的认证信息。请确认 SKU 号是否正确。",
        }), 404
    product["found"] = True
    return jsonify(product)


@app.route("/api/query/batch")
def api_query_batch():
    """批量查询多个 SKU（逗号/空格/换行分隔，上限 8 个）"""
    import re
    raw = request.args.get("skus", "").strip()
    if not raw:
        return jsonify({"error": "请提供 skus 参数"}), 400
    skus = [s.strip() for s in re.split(r"[,\s;]+", raw) if s.strip()]
    skus = skus[:8]
    results = []
    for sku in skus:
        product = query_sku(sku)
        if product and (product.get("certifications") or product.get("cert_text")):
            product["found"] = True
            results.append(product)
        else:
            results.append({"sku": sku, "found": False, "message": "未找到该 SKU 的认证信息。请确认 SKU 号是否正确。"})
    return jsonify({"count": len(results), "results": results})

@app.route("/api/search")
def api_search():
    keyword = request.args.get("name", "").strip()
    if not keyword:
        return jsonify({"error": "请提供 name 参数"}), 400

    words = [w for w in keyword.split() if w]
    if not words:
        return jsonify({"keyword": keyword, "count": 0, "results": []})

    conn = init_db()

    def _search(op):
        conds = (" " + op + " ").join(["LOWER(name) LIKE ?" for _ in words])
        params = tuple("%" + w.lower() + "%" for w in words)
        return conn.execute(
            "SELECT sku, name, cert_text, url, certifications, datasheet_url "
            "FROM products WHERE name != '' AND (" + conds + ") "
            "ORDER BY (certifications != '[]') DESC, name LIMIT 50",
            params,
        ).fetchall()

    rows = _search("AND")
    if not rows and len(words) > 1:
        rows = _search("OR")

    conn.close()

    results = []
    for r in rows:
        certs = []
        try:
            certs = json.loads(r[4]) if r[4] else []
        except Exception:
            certs = []
        results.append({
            "sku": r[0],
            "name": r[1],
            "cert_text": r[2],
            "url": r[3],
            "certifications": certs,
            "datasheet_url": r[5],
            "found": True,
        })

    return jsonify({"keyword": keyword, "count": len(results), "results": results})

@app.route("/api/stats")
def api_stats():
    conn = init_db()
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    with_certs = conn.execute(
        "SELECT COUNT(*) FROM products WHERE certifications != '[]'"
    ).fetchone()[0]
    latest = conn.execute(
        "SELECT MAX(last_updated) FROM products"
    ).fetchone()[0]
    conn.close()
    return jsonify({
        "total_products": total,
        "products_with_certs": with_certs,
        "latest_update": latest,
    })

@app.route("/api/export")
def api_export():
    """生成并下载 Excel 认证映射表"""
    try:
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(
            tmpdir,
            f"Seeed_Cert_Map_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        generate_excel(output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=os.path.basename(output_path),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 飞书机器人集成
# ============================================================
def feishu_get_token():
    """获取飞书 app_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    resp = http_requests.post(url, json=data, timeout=10)
    return resp.json().get("tenant_access_token", "")


def feishu_reply_message(token, message_id, text):
    """回复飞书消息"""
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }
    http_requests.post(url, headers=headers, json=payload, timeout=10)


@app.route("/feishu/webhook", methods=["POST"])
def feishu_webhook():
    """飞书事件回调入口"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400

    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    if FEISHU_VERIFICATION_TOKEN:
        header_token = data.get("header", {}).get("token", "")
        if header_token != FEISHU_VERIFICATION_TOKEN:
            return jsonify({"error": "invalid token"}), 403

    event = data.get("event", {})
    msg_type = event.get("message", {}).get("message_type", "")

    if msg_type == "text":
        msg_data = json.loads(event["message"]["content"])
        text_content = msg_data.get("text", "").strip()
        message_id = event.get("message", {}).get("message_id", "")

        import re
        sku_match = re.search(r"\b(\d{6,12})\b", text_content)
        if sku_match:
            sku = sku_match.group(1)
            product = query_sku(sku)
            reply_text = format_text(product)
        else:
            reply_text = (
                "请发送 SKU 号（纯数字）进行查询。\n"
                "例如发送：114993117\n\n"
                "也可访问网页版查询：" + request.host_url.rstrip("/")
            )

        if FEISHU_APP_ID and FEISHU_APP_SECRET:
            token = feishu_get_token()
            if token and message_id:
                feishu_reply_message(token, message_id, reply_text)
        else:
            return jsonify({"reply": reply_text})

    return jsonify({"code": 0})


# ============================================================
# 启动
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Seeed Studio 认证查询服务")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    local_ip = get_local_ip()
    print("=" * 55)
    print("  Seeed Studio 认证查询服务已启动")
    print(f"  本机访问:   http://localhost:{args.port}")
    print(f"  内网访问:   http://{local_ip}:{args.port}")
    print(f"  数据库:     {DB_PATH}")
    print("=" * 55)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
