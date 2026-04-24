import sqlite3
import os
import hashlib
import time
import logging
import shutil
from stock_utils import StockExtractor

logger = logging.getLogger(__name__)

def migrate_db(db_path):
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("PRAGMA table_info(messages)")
    columns = [col[1] for col in cur.fetchall()]
    
    # 1. Standard Migration (chat_id)
    if 'chat_id' not in columns:
        _perform_first_migration(conn, db_path)
        cur.execute("PRAGMA table_info(messages)")
        columns = [col[1] for col in cur.fetchall()]

    # 2. Stock Ticker Migration (has_stock_code)
    if 'has_stock_code' not in columns:
        logger.info("增加股票標註欄位...")
        cur.execute("ALTER TABLE messages ADD COLUMN has_stock_code INTEGER DEFAULT 0")
        conn.commit()

    # 3. Link Migration (has_link)
    if 'has_link' not in columns:
        logger.info("增加連結標註欄位...")
        cur.execute("ALTER TABLE messages ADD COLUMN has_link INTEGER DEFAULT 0")
        conn.commit()
        # Backfill links
        _perform_link_backfill(conn)

    # 4. Tables Initialization
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_mentions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        stock_code TEXT NOT NULL,
        UNIQUE(message_id, stock_code),
        FOREIGN KEY(message_id) REFERENCES messages(id)
    )
    """)
    conn.commit()

    # 5. Backfill stock mentions if empty
    cur.execute("SELECT COUNT(*) FROM stock_mentions")
    if cur.fetchone()[0] == 0:
        _perform_stock_backfill(conn)
    
    conn.close()

def _perform_link_backfill(conn):
    logger.info("正在執行連結標註掃描 (Backfill)...")
    cur = conn.cursor()
    cur.execute("SELECT id, message FROM messages WHERE message LIKE '%http%'")
    rows = cur.fetchall()
    updated_ids = [(r[0],) for r in rows]
    if updated_ids:
        cur.executemany("UPDATE messages SET has_link = 1 WHERE id = ?", updated_ids)
        conn.commit()
    logger.info(f"連結掃描完成，更新了 {len(updated_ids)} 筆。")

def _perform_first_migration(conn, db_path):
    cur = conn.cursor()
    # Manual backup
    backup_path = f"chat_backup_{int(time.time())}.db"
    shutil.copy2(db_path, backup_path)
    
    cur.execute("BEGIN TRANSACTION")
    cur.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source_type TEXT DEFAULT 'LINE', file_name TEXT, file_hash TEXT, created_at TEXT, imported_at TEXT)")
    cur.execute("INSERT INTO chats (name, source_type, imported_at) VALUES (?, ?, ?)", ("預設聊天室", "LINE", time.strftime("%Y-%m-%d %H:%M:%S")))
    default_chat_id = cur.lastrowid
    
    cur.execute(f"""
    CREATE TABLE messages_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        date TEXT,
        time TEXT,
        name TEXT,
        message TEXT,
        timestamp INTEGER,
        url TEXT,
        raw_line TEXT,
        has_stock_code INTEGER DEFAULT 0,
        has_link INTEGER DEFAULT 0,
        UNIQUE(chat_id, timestamp, name, message),
        FOREIGN KEY(chat_id) REFERENCES chats(id)
    )
    """)
    cur.execute(f"INSERT OR IGNORE INTO messages_new (chat_id, date, time, name, message, timestamp, url) SELECT DISTINCT {default_chat_id}, date, time, name, message, timestamp, url FROM messages")
    cur.execute("DROP TABLE messages")
    cur.execute("ALTER TABLE messages_new RENAME TO messages")
    cur.execute("DROP TABLE IF EXISTS msg_fts")
    cur.execute("CREATE VIRTUAL TABLE msg_fts USING fts5(name, message, url, content='messages', content_rowid='id', tokenize='trigram')")
    cur.execute("INSERT INTO msg_fts(rowid, name, message, url) SELECT id, name, message, url FROM messages")
    conn.commit()

def _perform_stock_backfill(conn):
    logger.info("正在執行舊訊息股票代號掃描 (Backfill)...")
    cur = conn.cursor()
    extractor = StockExtractor()
    cur.execute("SELECT id, message FROM messages")
    rows = cur.fetchall()
    mentions, ids = [], []
    for mid, msg in rows:
        codes = extractor.extract(msg)
        if codes:
            for c in codes: mentions.append((mid, c))
            ids.append((mid,))
        if len(mentions) >= 5000:
            cur.executemany("INSERT OR IGNORE INTO stock_mentions (message_id, stock_code) VALUES (?, ?)", mentions)
            cur.executemany("UPDATE messages SET has_stock_code = 1 WHERE id = ?", ids)
            conn.commit(); mentions, ids = [], []
    if mentions:
        cur.executemany("INSERT OR IGNORE INTO stock_mentions (message_id, stock_code) VALUES (?, ?)", mentions)
        cur.executemany("UPDATE messages SET has_stock_code = 1 WHERE id = ?", ids)
        conn.commit()
    logger.info("股票代號掃描完成。")

def init_db(db_path):
    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source_type TEXT DEFAULT 'LINE', file_name TEXT, file_hash TEXT, created_at TEXT, imported_at TEXT)")
        cur.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, date TEXT, time TEXT, name TEXT, message TEXT, timestamp INTEGER, url TEXT, raw_line TEXT, has_stock_code INTEGER DEFAULT 0, has_link INTEGER DEFAULT 0, UNIQUE(chat_id, timestamp, name, message), FOREIGN KEY(chat_id) REFERENCES chats(id))")
        cur.execute("CREATE TABLE stock_mentions (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL, stock_code TEXT NOT NULL, UNIQUE(message_id, stock_code), FOREIGN KEY(message_id) REFERENCES messages(id))")
        cur.execute("CREATE VIRTUAL TABLE msg_fts USING fts5(name, message, url, content='messages', content_rowid='id', tokenize='trigram')")
        conn.commit(); conn.close()
    else:
        migrate_db(db_path)
