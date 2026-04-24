import sqlite3
import webbrowser
import threading
import os
import logging
import time
import re
import hashlib
from flask import Flask, render_template, request, jsonify, session
import uuid
import db_manager
from stock_utils import StockExtractor

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("chat_web.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "line_analyzer_secret_web_cloud_v5"

# 確保存放資料庫的目錄存在
DBS_DIR = "dbs"
os.makedirs(DBS_DIR, exist_ok=True)

# 定期清理超過 2 小時沒動過的資料庫檔案 (背景執行)
def cleanup_old_dbs():
    while True:
        try:
            now = time.time()
            for f in os.listdir(DBS_DIR):
                if not f.endswith('.db'): continue
                p = os.path.join(DBS_DIR, f)
                if os.path.isfile(p) and now - os.path.getmtime(p) > 3600 * 2:
                    os.remove(p)
        except Exception as e:
            logger.error(f"清理過期資料庫失敗: {e}")
        time.sleep(3600)

threading.Thread(target=cleanup_old_dbs, daemon=True).start()

stock_extractor = StockExtractor()

@app.before_request
def ensure_session():
    if 'uid' not in session:
        session['uid'] = str(uuid.uuid4())

def get_db_path():
    uid = session.get('uid', 'default')
    return os.path.join(DBS_DIR, f"chat_{uid}.db")

# Media skip set
MEDIA_SKIP_LIST = {
    "[貼圖]", "[影片]", "[照片]", "[相片]", "[圖片]", 
    "[影像]", "[影音]", "[檔案]", "[語音訊息]", 
    "[位置訊息]", "已收回訊息", "[聯絡資訊]"
}

def get_db():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        db_manager.init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/api/chats')
def list_chats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM messages WHERE chat_id = c.id) as message_count,
               (SELECT date || ' ' || time FROM messages WHERE chat_id = c.id ORDER BY timestamp DESC LIMIT 1) as last_message_at
        FROM chats c
        ORDER BY imported_at DESC
    """)
    chats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"ok": True, "items": chats})

@app.route('/api/chats/<int:chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM chats WHERE id = ?", (chat_id,))
        if not cursor.fetchone():
            return jsonify({"ok": False, "error": "聊天室不存在"}), 404
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM stock_mentions WHERE message_id IN (SELECT id FROM messages WHERE chat_id = ?)", (chat_id,))
        cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        cursor.execute("INSERT INTO msg_fts(msg_fts) VALUES('rebuild')")
        conn.commit()
        return jsonify({"ok": True, "deleted_chat_id": chat_id})
    except Exception as e:
        conn.rollback(); logger.error(f"刪除失敗: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally: conn.close()

@app.route('/api/chats/<int:chat_id>/rename', methods=['POST'])
def rename_chat(chat_id):
    new_name = request.json.get('name', '').strip()
    if not new_name: return jsonify({"ok": False, "error": "名稱不能為空"}), 400
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE chats SET name = ? WHERE id = ?", (new_name, chat_id))
    if cursor.rowcount == 0: conn.close(); return jsonify({"ok": False, "error": "不存在"}), 404
    conn.commit(); conn.close()
    return jsonify({"ok": True, "chat_id": chat_id, "name": new_name})

@app.route('/api/import', methods=['POST'])
def import_chat():
    if 'file' not in request.files: return jsonify({"ok": False, "error": "無檔案"}), 400
    file = request.files['file']
    cleanup = request.form.get('cleanup') == 'true'
    if file.filename == '': return jsonify({"ok": False, "error": "檔名為空"}), 400

    content = file.read().decode('utf-8-sig')
    file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

    chat_name_from_file = os.path.splitext(file.filename)[0]
    for line in content.splitlines()[:5]:
        if "的聊天記錄" in line:
            chat_name_from_file = line.split("的聊天記錄")[0].replace("[LINE] ", "").strip()
            break

    conn = get_db(); cursor = conn.cursor()

    if cleanup:
        cursor.execute("SELECT id FROM chats WHERE file_hash = ? OR name = ?", (file_hash, chat_name_from_file))
        for row in cursor.fetchall():
            cursor.execute("DELETE FROM stock_mentions WHERE message_id IN (SELECT id FROM messages WHERE chat_id = ?)", (row['id'],))
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (row['id'],))
            cursor.execute("DELETE FROM chats WHERE id = ?", (row['id'],))
        conn.commit()

    cursor.execute("SELECT id, name FROM chats WHERE file_hash = ?", (file_hash,))
    existing = cursor.fetchone()
    if existing:
        chat_id = existing['id']
        if existing['name'] != chat_name_from_file: 
            cursor.execute("UPDATE chats SET name = ? WHERE id = ?", (chat_name_from_file, chat_id)); conn.commit()
        conn.close(); return jsonify({"ok": True, "duplicate_file": True, "chat_id": chat_id, "chat_name": chat_name_from_file})

    cursor.execute("INSERT INTO chats (name, file_name, file_hash, imported_at) VALUES (?, ?, ?, ?)", (chat_name_from_file, file.filename, file_hash, time.strftime("%Y-%m-%d %H:%M:%S")))
    chat_id = cursor.lastrowid

    date_p = re.compile(r"^(\d{4}\.\d{2}\.\d{2}) 星期[一二三四五六日]$")
    msg_p = re.compile(r"^(\d{2}:\d{2})\t([^\t]+)\t(.*)$")
    msg_p_a = re.compile(r"^(\d{2}:\d{2}) ([^ ]+) (.*)$")

    cur_d, ins, skp = "0000.00.00", 0, 0
    
    # 批次寫入緩存
    msg_batch = []
    stock_mentions_batch = []
    
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        dm = date_p.match(line)
        if dm: cur_d = dm.group(1); continue
        mm = msg_p.match(line) or msg_p_a.match(line)
        if mm:
            ts_str, snd, msg = mm.groups()
            if msg in MEDIA_SKIP_LIST: skp += 1; continue # Skip media placeholders
            try: ts = int(time.mktime(time.strptime(f"{cur_d} {ts_str}", "%Y.%m.%d %H:%M")))
            except: ts = 0
            
            codes = stock_extractor.extract(msg)
            h_stock = 1 if codes else 0
            h_link = 1 if "http" in msg.lower() else 0
            
            # 使用 UUID 作為這筆 message 的臨時識別碼，以便在同一批次建立關聯
            temp_msg_id = str(uuid.uuid4())
            msg_batch.append((chat_id, cur_d, ts_str, snd, msg, ts, h_stock, h_link, temp_msg_id))
            
            if codes:
                for c in codes:
                    stock_mentions_batch.append((temp_msg_id, c))
            
            # 滿 5000 筆寫入一次
            if len(msg_batch) >= 5000:
                _flush_import_batches(cursor, msg_batch, stock_mentions_batch)
                ins += len(msg_batch)
                msg_batch.clear()
                stock_mentions_batch.clear()
                
    # 寫入剩餘資料
    if msg_batch:
        _flush_import_batches(cursor, msg_batch, stock_mentions_batch)
        ins += len(msg_batch)
        
    conn.commit(); conn.close()
    return jsonify({"ok": True, "chat_id": chat_id, "chat_name": chat_name_from_file, "inserted": ins, "skipped": skp, "duplicate_file": False})

def _flush_import_batches(cursor, msg_batch, stock_mentions_batch):
    # 先建一個暫存表來存放這次批次的訊息
    cursor.execute("CREATE TEMPORARY TABLE temp_msgs (temp_id TEXT, chat_id INTEGER, date TEXT, time TEXT, name TEXT, message TEXT, timestamp INTEGER, has_stock_code INTEGER, has_link INTEGER)")
    cursor.executemany("INSERT INTO temp_msgs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [(m[8], m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7]) for m in msg_batch])
    
    # 將暫存表的資料 INSERT OR IGNORE 到正式表
    cursor.execute("INSERT OR IGNORE INTO messages (chat_id, date, time, name, message, timestamp, has_stock_code, has_link) SELECT chat_id, date, time, name, message, timestamp, has_stock_code, has_link FROM temp_msgs")
    
    # 取得剛插入的真實 ID (利用 SQLite rowid 對應條件)
    # 這部分為了效能，我們直接回撈 temp_id 對應的 id
    # 建立一個 mapping
    cursor.execute("SELECT m.id, t.temp_id FROM messages m JOIN temp_msgs t ON m.chat_id = t.chat_id AND m.timestamp = t.timestamp AND m.name = t.name AND m.message = t.message")
    id_map = {row['temp_id']: row['id'] for row in cursor.fetchall()}
    
    # 處理股票關聯
    if stock_mentions_batch:
        final_mentions = []
        for temp_id, code in stock_mentions_batch:
            if temp_id in id_map:
                final_mentions.append((id_map[temp_id], code))
        if final_mentions:
            cursor.executemany("INSERT OR IGNORE INTO stock_mentions (message_id, stock_code) VALUES (?, ?)", final_mentions)
            
    cursor.execute("DROP TABLE temp_msgs")

@app.route('/api/stocks/top')
def top_stocks():
    chat_ids_raw = request.args.get('chat_id', '').strip()
    chat_ids = [c.strip() for c in chat_ids_raw.split(',') if c.strip()] if chat_ids_raw else []
    conn = get_db(); cur = conn.cursor()
    sql = "SELECT sm.stock_code, COUNT(*) as count FROM stock_mentions sm JOIN messages m ON m.id = sm.message_id"
    params = []
    if chat_ids:
        placeholders = ",".join(["?"] * len(chat_ids))
        sql += f" WHERE m.chat_id IN ({placeholders})"
        params.extend(chat_ids)
    sql += " GROUP BY sm.stock_code ORDER BY count DESC LIMIT 20"
    cur.execute(sql, params); items = []
    for r in cur.fetchall():
        d = dict(r); d['stock_name'] = stock_extractor.get_name(d['stock_code']); items.append(d)
    conn.close(); return jsonify({"ok": True, "items": items})

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    # Support multiple chat_ids: comma-separated string, e.g. "1,3"
    chat_ids_raw = request.args.get('chat_id', '').strip()
    chat_ids = [c.strip() for c in chat_ids_raw.split(',') if c.strip()] if chat_ids_raw else []
    name = request.args.get('name', '').strip()
    stock_code = request.args.get('stock_code', '').strip()
    has_stock = request.args.get('has_stock', '').strip()
    has_link = request.args.get('has_link', '').strip()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    conn = get_db(); cur = conn.cursor()

    def build_chat_filter(alias='m'):
        """Return (clause, params) for multi/single chat_id filter."""
        if not chat_ids:
            return "", []
        if len(chat_ids) == 1:
            return f" AND {alias}.chat_id = ?", [chat_ids[0]]
        placeholders = ",".join(["?"] * len(chat_ids))
        return f" AND {alias}.chat_id IN ({placeholders})", chat_ids

    try:
        items = []
        chat_clause, chat_params = build_chat_filter()
        if q:
            sq = " ".join([f'"{p}"' for p in q.replace('"', '').replace("'", "").split()])
            sql = "SELECT m.*, c.name as chat_name FROM msg_fts f JOIN messages m ON m.id = f.rowid JOIN chats c ON c.id = m.chat_id WHERE msg_fts MATCH ?"
            params = [sq]
            sql += chat_clause; params += chat_params
            if name: sql += " AND m.name = ?"; params.append(name)
            if stock_code: sql += " AND m.id IN (SELECT message_id FROM stock_mentions WHERE stock_code = ?)"; params.append(stock_code)
            if has_stock == '1': sql += " AND m.has_stock_code = 1"
            if has_link == '1': sql += " AND m.has_link = 1"
            cur.execute(sql + " ORDER BY m.timestamp DESC LIMIT ? OFFSET ?", params + [limit, offset])
            rows = cur.fetchall()
            if not rows and offset == 0:
                sql = "SELECT m.*, c.name as chat_name FROM messages m JOIN chats c ON c.id = m.chat_id WHERE (m.message LIKE ? OR m.name LIKE ?)"
                params = [f"%{q}%", f"%{q}%"]
                sql += chat_clause; params += chat_params
                if name: sql += " AND m.name = ?"; params.append(name)
                if stock_code: sql += " AND m.id IN (SELECT message_id FROM stock_mentions WHERE stock_code = ?)"; params.append(stock_code)
                if has_stock == '1': sql += " AND m.has_stock_code = 1"
                if has_link == '1': sql += " AND m.has_link = 1"
                cur.execute(sql + " ORDER BY timestamp DESC LIMIT ? OFFSET ?", params + [limit, offset])
                rows = cur.fetchall()
            items = [dict(row) for row in rows]
        else:
            sql = "SELECT m.*, c.name as chat_name FROM messages m JOIN chats c ON c.id = m.chat_id"
            ws, params = [], []
            if chat_ids:
                if len(chat_ids) == 1:
                    ws.append("m.chat_id = ?"); params.append(chat_ids[0])
                else:
                    placeholders = ",".join(["?"] * len(chat_ids))
                    ws.append(f"m.chat_id IN ({placeholders})"); params += chat_ids
            if name: ws.append("m.name = ?"); params.append(name)
            if stock_code: ws.append("m.id IN (SELECT message_id FROM stock_mentions WHERE stock_code = ?)"); params.append(stock_code)
            if has_stock == '1': ws.append("m.has_stock_code = 1")
            if has_link == '1': ws.append("m.has_link = 1")
            if ws: sql += " WHERE " + " AND ".join(ws)
            cur.execute(sql + " ORDER BY timestamp DESC LIMIT ? OFFSET ?", params + [limit, offset])
            items = [dict(r) for r in cur.fetchall()]
        return jsonify({"ok": True, "count": len(items), "items": items})
    except Exception as e:
        logger.error(f"搜尋出錯: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/stats')
def stats():
    chat_ids_raw = request.args.get('chat_id', '').strip()
    chat_ids = [c.strip() for c in chat_ids_raw.split(',') if c.strip()] if chat_ids_raw else []
    conn = get_db(); cur = conn.cursor()
    w = ""; p = []
    if chat_ids:
        placeholders = ",".join(["?"] * len(chat_ids))
        w = f"WHERE chat_id IN ({placeholders})"
        p.extend(chat_ids)
    cur.execute(f"SELECT name, COUNT(*) as count FROM messages {w} GROUP BY name ORDER BY count DESC LIMIT 20", p); snd = [dict(r) for r in cur.fetchall()]
    cur.execute(f"SELECT COUNT(*) FROM messages {w}", p); tot = cur.fetchone()[0]; conn.close()
    return jsonify({"ok": True, "senders": snd, "total": tot})

if __name__ == '__main__':
    # 雲端版本不需要自動開啟瀏覽器，且必須綁定 0.0.0.0
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
