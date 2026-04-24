"""
fetch_stocks.py - 從 TWSE/TPEx API 抓取完整台股清單，更新 stock_codes.json
用法：python fetch_stocks.py
只需執行一次，之後 stock_codes.json 就有完整代號+中文名對照表
"""
import json
import urllib.request
import urllib.error
import ssl
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "stock_codes.json")

def fetch_json(url):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"無法取得 {url}: {e}")
        return []

def main():
    # 先載入既有資料，避免單一來源失敗時丟失資料
    codes = {}
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                codes = json.load(f)
            logger.info(f"載入既有 {len(codes)} 筆資料")
        except Exception:
            pass

    # 1. 上市 (TWSE)
    logger.info("正在抓取上市股票清單 (TWSE)...")
    twse_data = fetch_json(TWSE_URL)
    for item in twse_data:
        code = item.get("Code", "").strip()
        name = item.get("Name", "").strip()
        # 只保留純數字代號（一般股票），跳過 ETF/期貨/特別股等
        if code and name and code.isdigit() and len(code) == 4:
            codes[code] = name
    logger.info(f"上市股票: 取得 {len(codes)} 筆")

    # 2. 上櫃 (TPEx)
    logger.info("正在抓取上櫃股票清單 (TPEx)...")
    tpex_data = fetch_json(TPEX_URL)
    tpex_count = 0
    for item in tpex_data:
        # TPEx daily_close_quotes 欄位: SecuritiesCompanyCode, CompanyName
        code = item.get("SecuritiesCompanyCode", "").strip()
        name = item.get("CompanyName", "").strip()
        # 移除公司名稱中的特殊標記（如 *、-KY 等）
        name = name.replace("*", "").strip()
        if code and name and code.isdigit() and len(code) == 4:
            if code not in codes:
                codes[code] = name
                tpex_count += 1
    logger.info(f"上櫃股票: 新增 {tpex_count} 筆")

    if not codes:
        logger.error("❌ 抓取失敗，stock_codes.json 未更新")
        return

    # 寫入 JSON
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2, sort_keys=True)

    logger.info(f"✅ 完成！共 {len(codes)} 筆股票資料已寫入 stock_codes.json")

if __name__ == "__main__":
    main()
