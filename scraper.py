# -*- coding: utf-8 -*-
"""
Seeed Studio SKU 认证信息抓取脚本
===================================
功能：
  1. 从 seeedstudio.com/sitemap.xml 获取所有产品页面 URL
  2. 逐个抓取产品页面，提取 SKU 号、产品名称、认证信息（CE/FCC/RoHS/KC 等）
  3. 提取认证 PDF 文件链接（Seeed_Certificate 证书 + Wiki 测试报告 + 产品规格书）
  4. 保存到 SQLite 数据库（cert_data.db）

用法：
  python scraper.py                    # 全量抓取（跳过 24 小时内已更新的）
  python scraper.py --force            # 强制全量重新抓取
  python scraper.py --sku 114993117    # 只抓取指定 SKU（在线查询模式）
"""

import argparse
import json
import os
import re
import sqlite3
import time
import html as htmllib
from datetime import datetime, timezone

import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# 配置
# ============================================================
SITEMAP_URL = "https://www.seeedstudio.com/sitemap.xml"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cert_data.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 25
REQUEST_DELAY = 1.2
CACHE_HOURS = 168  # 7 ????????????????????/????

CERT_TYPE_NAMES = {
    "CE": "CE 认证（欧盟符合性）",
    "EUDOC": "欧盟符合性声明书（EU DoC）",
    "FCC": "FCC 认证（美国联邦通信委员会）",
    "ROHS": "RoHS 认证（有害物质限制）",
    "UKDOC": "UKCA 认证（英国符合性声明）",
    "TELEC": "TELEC 认证（日本无线电法）",
    "KC": "KC 认证（韩国）",
    "UL": "UL 认证（美国安全认证）",
    "UKCA": "UKCA 认证（英国）",
    "DOC": "符合性声明书（DoC）",
    "EMC": "EMC 电磁兼容测试",
    "VOC": "符合性验证书（VoC）",
}

WIKI_EXCLUDE_KEYWORDS = ["warranty", "success-case", "tutorial", "guide", "manual"]

from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:
    from requests.packages.urllib3.util.retry import Retry

# ?????? Session????? 429 / 5xx ??
SESSION = requests.Session()
_retry = Retry(total=4, backoff_factor=0.6,
               status_forcelist=[429, 500, 502, 503, 504],
               allowed_methods=["GET", "HEAD"])
SESSION.mount("https://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=10))
SESSION.mount("http://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=10))
SESSION.headers.update(HEADERS)


# ============================================================
# 数据库
# ============================================================
def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku           TEXT PRIMARY KEY,
            product_id    TEXT,
            name          TEXT,
            url           TEXT,
            cert_text     TEXT,
            certifications TEXT,
            datasheet_url TEXT,
            last_updated  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


def save_product(conn, product):
    conn.execute("""
        INSERT OR REPLACE INTO products
            (sku, product_id, name, url, cert_text, certifications, datasheet_url, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product["sku"],
        product.get("product_id", ""),
        product.get("name", ""),
        product.get("url", ""),
        product.get("cert_text", ""),
        json.dumps(product.get("certifications", []), ensure_ascii=False),
        product.get("datasheet_url", ""),
        product.get("last_updated", ""),
    ))
    conn.commit()


def get_product(conn, sku):
    row = conn.execute(
        "SELECT * FROM products WHERE sku = ?", (sku,)
    ).fetchone()
    if not row:
        return None
    return {
        "sku": row[0],
        "product_id": row[1],
        "name": row[2],
        "url": row[3],
        "cert_text": row[4],
        "certifications": json.loads(row[5]) if row[5] else [],
        "datasheet_url": row[6],
        "last_updated": row[7],
    }


def is_fresh(conn, sku, max_age_hours=CACHE_HOURS):
    row = conn.execute(
        "SELECT last_updated FROM products WHERE sku = ?", (sku,)
    ).fetchone()
    if not row or not row[0]:
        return False
    try:
        updated = datetime.fromisoformat(row[0])
        age = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
        return age < max_age_hours
    except Exception:
        return False


# ============================================================
# 网页抓取
# ============================================================
def fetch_sitemap_products():
    print("正在获取 sitemap.xml ...")
    resp = SESSION.get(SITEMAP_URL, timeout=30)
    resp.raise_for_status()
    urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
    products = []
    for u in urls:
        m = re.search(r"-p-(\d+)\.html$", u)
        if m:
            products.append({"product_id": m.group(1), "url": u})
    print(f"  共找到 {len(products)} 个产品页面")
    return products


def fetch_page(url):
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def extract_product_data(html_text, url):
    if not html_text:
        return None

    decoded = htmllib.unescape(html_text)
    decoded = decoded.replace("\\/", "/")

    # SKU
    sku_m = re.search(r'"sku"\s*:\s*"([^"]+)"', html_text)
    if not sku_m:
        return None
    sku = sku_m.group(1).strip()

    # 产品名称
    name_m = re.search(r'"name"\s*:\s*"([^"]{1,200})', html_text)
    name = name_m.group(1).strip() if name_m else ""

    # product_id
    pid_m = re.search(r"-p-(\d+)\.html", url)
    product_id = pid_m.group(1) if pid_m else ""

    # 认证 PDF：Seeed_Certificate 模式
    cert_pdfs = re.findall(
        r"https://files\.seeedstudio\.com/Seeed_Certificate/documents_certificate/(\d+)-(\w+)\.pdf",
        decoded,
    )
    seen_certs = set()
    certifications = []
    for cert_sku, cert_type in cert_pdfs:
        ct = cert_type.upper()
        if ct in seen_certs:
            continue
        seen_certs.add(ct)
        certifications.append({
            "type": ct,
            "name": CERT_TYPE_NAMES.get(ct, ct),
            "pdf_url": f"https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/{cert_sku}-{cert_type}.pdf",
            "source": "certificate",
        })

    # 认证 PDF：Wiki 测试报告模式
    wiki_pdfs = re.findall(
        r'(https://files\.seeedstudio\.com/wiki/[^"\s<>]+\.pdf)',
        decoded,
        re.IGNORECASE,
    )
    cert_keywords = ["voc", "sdoc", "doc", "fcc", "emc", "rohs", "telec", "kc", "ul", "ukca", "ce-"]
    for wpdf in wiki_pdfs:
        wpdf_lower = wpdf.lower()
        if any(k in wpdf_lower for k in WIKI_EXCLUDE_KEYWORDS):
            continue
        if any(k in wpdf_lower for k in cert_keywords):
            certifications.append({
                "type": "TEST_REPORT",
                "name": "测试报告 / 符合性文件",
                "pdf_url": wpdf,
                "source": "wiki",
            })

    # 产品规格书 PDF
    datasheet_url = f"https://files.seeedstudio.com/Bazaar/product_pdf/{sku}.pdf"

    # 认证文字描述
    cert_text = ""
    ct_m = re.search(
        r"Certification</span></p>\s*</td>\s*<td[^>]*>\s*<p><span[^>]*>([^<]+)</span>",
        decoded,
    )
    if ct_m:
        cert_text = ct_m.group(1).strip()
    else:
        ct_m2 = re.search(r">RoHS[^<]{0,100}", decoded)
        if ct_m2:
            cert_text = ct_m2.group(0).lstrip(">")
    cert_text = cert_text.replace("\u00a0", " ").strip()

    return {
        "sku": sku,
        "product_id": product_id,
        "name": name,
        "url": url,
        "cert_text": cert_text,
        "certifications": certifications,
        "datasheet_url": datasheet_url,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# 批量抓取
# ============================================================
def scrape_all(force=False, delay=REQUEST_DELAY, workers=1):
    conn = init_db()
    products = fetch_sitemap_products()
    total = len(products)

    # Pre-filter fresh entries (fast single-threaded DB read)
    todo, skipped = [], 0
    for p in products:
        if not force:
            existing = conn.execute(
                "SELECT sku FROM products WHERE product_id = ? AND "
                "datetime(last_updated) > datetime('now', ?)",
                (p["product_id"], f"-{CACHE_HOURS} hours"),
            ).fetchone()
            if existing:
                skipped += 1
                continue
        todo.append(p)

    success, failed, done = 0, 0, 0

    def worker(p):
        try:
            html_text = fetch_page(p["url"])
            if html_text is None:
                return None
            return extract_product_data(html_text, p["url"])
        except Exception:
            return None

    def report(done, todo_n):
        if done % 100 == 0 or done <= 5 or done == todo_n:
            print(f"  [{done}/{todo_n}] ??:{success} ??:{skipped} ??:{failed}")

    if workers and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(worker, p): p for p in todo}
            for fut in as_completed(futs):
                done += 1
                try:
                    product = fut.result()
                except Exception:
                    product = None
                if product:
                    save_product(conn, product)
                    success += 1
                else:
                    failed += 1
                report(done, len(todo))
    else:
        for p in todo:
            product = worker(p)
            done += 1
            if product:
                save_product(conn, product)
                success += 1
            else:
                failed += 1
            report(done, len(todo))
            if delay:
                time.sleep(delay)

    conn.close()
    print(f"\n???????:{success} ??:{skipped} ??:{failed} ??:{total}")
    return success
def scrape_single(sku):
    conn = init_db()

    if is_fresh(conn, sku):
        product = get_product(conn, sku)
        if product:
            conn.close()
            return product

    cert_types = ["CE", "EUDOC", "FCC", "ROHS", "UKDOC", "TELEC", "KC", "UL"]
    certifications = []
    for ct in cert_types:
        pdf_url = f"https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/{sku}-{ct}.pdf"
        try:
            resp = requests.head(pdf_url, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                certifications.append({
                    "type": ct,
                    "name": CERT_TYPE_NAMES.get(ct, ct),
                    "pdf_url": pdf_url,
                    "source": "certificate",
                })
        except Exception:
            pass
        time.sleep(0.3)

    product = {
        "sku": sku,
        "product_id": "",
        "name": "",
        "url": "",
        "cert_text": ", ".join(c["type"] for c in certifications),
        "certifications": certifications,
        "datasheet_url": f"https://files.seeedstudio.com/Bazaar/product_pdf/{sku}.pdf",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    if certifications:
        save_product(conn, product)
    conn.close()
    return product


def main():
    parser = argparse.ArgumentParser(description="Seeed Studio 认证信息抓取")
    parser.add_argument("--force", action="store_true", help="强制重新抓取所有产品")
    parser.add_argument("--sku", type=str, help="只查询单个 SKU")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="请求间隔秒数")
    parser.add_argument("--workers", type=int, default=1, help="并发线程数（建议 6-10）")
    args = parser.parse_args()

    if args.sku:
        print(f"在线查询 SKU: {args.sku}")
        product = scrape_single(args.sku)
        print(json.dumps(product, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("Seeed Studio 认证信息全量抓取")
        print("=" * 60)
        scrape_all(force=args.force, delay=args.delay, workers=args.workers)


if __name__ == "__main__":
    main()
