# 07_LINE_Chat_Analyzer — AI 開發規則 (AI_RULES.md)

> ⚠️ **所有 AI 模型（Gemini、Claude、GPT 等）在接手此專案時，必須先讀完本文件，才可執行任何程式碼修改。**

---

## 📍 專案基本資訊

- **專案路徑**：`F:\01.Mycoding\2026-04-21 Antigravity mystock\07_LINE_Chat_Analyzer\`
- **主程式**：`chat_web.py`（Flask Web App）
- **資料庫**：`chat.db`（SQLite，本機，勿上傳）
- **啟動方式**：雙擊 `run_web.bat`（一鍵啟動，無需打指令）
- **主要功能**：上傳 LINE 聊天記錄 `.txt`，解析後可搜尋、篩選個股訊息

---

## ⚙️ 核心開發流程（6 階段紀律）

**嚴禁在未經規劃的情況下直接撰寫程式碼。** 每次接到任務，必須依序執行以下階段：

1. **Define (/spec)**：釐清需求，寫下假設並確認
2. **Plan (/plan)**：拆解成可執行的小任務，排定順序
3. **Build (/build)**：漸進實作，一次只解決一個任務
4. **Verify (/verify)**：主動檢查錯誤，重現→定位→修復
5. **Review (/review)**：奧卡姆剃刀，刪除複雜度，確認無安全漏洞
6. **Ship (/ship)**：更新本文件的 `[HANDOFF_LOG]` 區塊

---

## 🚫 絕對禁止的行為

- 收到需求後直接輸出數百行程式碼，不先確認
- 在沒有驗證方法的情況下修改核心邏輯
- 找藉口跳過規格確認（「這很簡單」不是理由）
- 在回應中印出大量未修改的程式碼（浪費 Token）
- 建立 `.bat` 檔時使用 Unix 換行（`LF`），**必須使用 Windows CRLF**
- 將 `chat.db`、`.log`、`.txt` 聊天記錄等個人資料寫入 Git

---

## 🛠️ 程式碼守則

| 規則 | 說明 |
|---|---|
| **編碼** | `.bat` 開頭必須 `chcp 65001 > nul`，Python 統一 UTF-8 |
| **換行** | `.bat` 檔必須 CRLF，建立後用 PowerShell 強制轉換 |
| **路徑** | 含中文或空格的路徑必須用引號包覆 |
| **日誌** | 所有功能必須內建 Log，發生錯誤時才能追蹤 |
| **路徑讀取** | 禁止寫死路徑，路徑從 `config.json` 或環境變數讀取 |
| **啟動** | 所有程式必須有 `.bat` 一鍵啟動檔 |

---

## 📁 重要檔案說明

| 檔案 | 用途 |
|---|---|
| `chat_web.py` | Flask 主程式，所有 API 路由 |
| `db_manager.py` | SQLite 初始化與 Migration |
| `stock_utils.py` | 股票代號萃取（4碼數字 + 中文名稱） |
| `stock_codes.json` | 股票白名單（代號 → 中文名，從 TWSE API 抓取） |
| `templates/chat.html` | 前端 SPA 介面 |
| `static/style.css` | 全域 CSS |
| `static/script.js` | 前端互動邏輯 |
| `run_web.bat` | 一鍵啟動腳本（Windows CRLF） |
| `fetch_stocks.py` | 一次性工具：從 TWSE API 抓取完整股票清單並更新 `stock_codes.json` |

---

## 📝 [HANDOFF_LOG] 交接日誌

*(每次 Ship 後更新此區塊，舊紀錄直接覆蓋)*

- **最後更新**：2026-04-24
- **完成進度**：
  1. 建立 `AI_RULES.md`（本檔）作為跨 AI 模型統一規範
  2. 修正 `run_web.bat` CMD 亂碼問題（CRLF + PYTHONIOENCODING）
  3. 實作啟動自動清空 DB（`--reset` flag 或 startup 邏輯）
  4. 建立 `fetch_stocks.py`，從 TWSE API 抓取完整上市股票清單（代號+中文名）並更新 `stock_codes.json`
  5. 升級 `stock_utils.py` 支援中文股票名稱識別
  6. 前端支援多選聊天室搜尋（checkbox 多選 + API 接受多個 chat_id）
- **下一步**：測試所有功能是否正常，確認中文名稱識別精準度

---

## 🔗 相關資源

- **TWSE 上市股票 API**：`https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL`
- **TPEx 上櫃股票 API**：`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perday_statistics`（備用）
- **AgentSkills 開發規範**：`F:\01.Mycoding\2026-04-21 Antigravity mystock\AgentSkills\GEMINI.md`
