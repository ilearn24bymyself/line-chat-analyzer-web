import sqlite3
import re
import os
import pathlib
import sys
import time
import logging

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("chat_analyzer.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ChatAnalyzer:
    def __init__(self, db_path="chat.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._setup_db()

    def _setup_db(self):
        # Create standard table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            name TEXT,
            message TEXT,
            timestamp INTEGER,
            url TEXT
        )
        """)
        # Create FTS5 table with trigram tokenizer
        try:
            self.cursor.execute("DROP TABLE IF EXISTS msg_fts")
            self.cursor.execute("""
            CREATE VIRTUAL TABLE msg_fts USING fts5(
                name, message, url,
                content='messages',
                content_rowid='id',
                tokenize = 'trigram'
            )
            """)
            # Trigger to keep FTS in sync
            self.cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO msg_fts(rowid, name, message, url) VALUES (new.id, new.name, new.message, new.url);
            END;
            """)
        except sqlite3.OperationalError as e:
            if "fts5" in str(e).lower():
                print("❌ 錯誤: 您的 SQLite 不支援 FTS5。搜尋功能將受限。")
            else:
                raise e
        self.conn.commit()

    def parse_file(self, file_path):
        if not os.path.exists(file_path):
            error_msg = f"❌ 找不到檔案，請確認路徑: {file_path}"
            print(error_msg)
            logger.error(error_msg)
            return

        logger.info(f"開始解析檔案: {file_path}")
        print(f"🔍 正在解析檔案: {file_path}...")
        start_time = time.time()
        
        # Regex patterns
        date_pattern = re.compile(r"^(\d{4}\.\d{2}\.\d{2}) 星期[一二三四五六日]$")
        msg_pattern = re.compile(r"^(\d{2}:\d{2}) ([^\t ]+) (.*)$")
        url_pattern = re.compile(r"https?://[^\s]+")

        current_date = "0000.00.00"
        records = []
        count = 0
        
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue

                    # Check for date header
                    date_match = date_pattern.match(line)
                    if date_match:
                        current_date = date_match.group(1)
                        continue

                    # Check for message
                    msg_match = msg_pattern.match(line)
                    if msg_match:
                        time_str = msg_match.group(1)
                        sender = msg_match.group(2)
                        content = msg_match.group(3)

                        # Filter stickers/retractions
                        if content in ["[貼圖]", "[影片]", "[照片]", "[檔案]", "已收回訊息"]:
                            continue

                        urls = url_pattern.findall(content)
                        url_str = ",".join(urls) if urls else ""
                        
                        # Timestamp calculation (approximate for sorting)
                        try:
                            ts_str = f"{current_date} {time_str}"
                            ts = int(time.mktime(time.strptime(ts_str, "%Y.%m.%d %H:%M")))
                        except:
                            ts = 0

                        records.append((current_date, time_str, sender, content, ts, url_str))
                        count += 1

                        if len(records) >= 50000:
                            self.cursor.executemany(
                                "INSERT INTO messages (date, time, name, message, timestamp, url) VALUES (?, ?, ?, ?, ?, ?)",
                                records
                            )
                            self.conn.commit()
                            records = []
                            msg = f"   已解析 {count} 筆..."
                            print(msg)
                            logger.info(msg)

            if records:
                self.cursor.executemany(
                    "INSERT INTO messages (date, time, name, message, timestamp, url) VALUES (?, ?, ?, ?, ?, ?)",
                    records
                )
                self.conn.commit()

        except UnicodeDecodeError:
            print("❌ 檔案編碼錯誤，請確保檔案為 UTF-8 格式。")
            return
        except Exception as e:
            print(f"❌ 解析發生錯誤: {e}")
            return

        duration = time.time() - start_time
        msg = f"✅ 解析完成，共建立 {count} 筆索引 ({duration:.1f}秒)"
        print(msg)
        logger.info(msg)

    def search(self, query):
        if not query: return
        
        # Check if query is name-only or keyword
        # FTS5 query
        try:
            # Simple handling for multiple keywords
            safe_query = " ".join([f'"{q}"' for q in query.split()])
            self.cursor.execute("""
                SELECT name, date, time, message 
                FROM msg_fts 
                JOIN messages ON messages.id = msg_fts.rowid
                WHERE msg_fts MATCH ?
                ORDER BY timestamp DESC LIMIT 100
            """, (safe_query,))
        except sqlite3.OperationalError:
            # Fallback to LIKE if FTS fails
            self.cursor.execute("""
                SELECT name, date, time, message FROM messages 
                WHERE message LIKE ? OR name LIKE ? 
                ORDER BY timestamp DESC LIMIT 100
            """, (f"%{query}%", f"%{query}%"))

        rows = self.cursor.fetchall()
        
        if not rows:
            print("💡 找不到相關訊息，試試其他關鍵字")
            return

        print("\n" + "╔" + "═" * 60 + "╗")
        for name, date, time_str, message in rows:
            header = f" ║ {name} {date} {time_str}"
            print(f"{header:<61}║")
            
            # Wrap message text
            wrapped_msg = [message[i:i+55] for i in range(0, len(message), 55)]
            for line in wrapped_msg:
                print(f" ║ > {line:<57}║")
            print(" ║" + " " * 59 + "║")
        print("╚" + "═" * 60 + "╝")

def main():
    print("===================================================")
    print("   LINE Chat Analyzer for Windows (v1.0)")
    print("===================================================\n")
    
    analyzer = ChatAnalyzer()
    
    # Simple check to see if database is already populated
    analyzer.cursor.execute("SELECT COUNT(*) FROM messages")
    if analyzer.cursor.fetchone()[0] == 0:
        raw_path = input("> 輸入檔案路徑 (或直接拖放檔案): ").strip().strip('"').strip("'")
        if raw_path:
            analyzer.parse_file(raw_path)
    
    while True:
        try:
            query = input("\n> 搜尋關鍵字 (直接Enter結束, Ctrl+C停止): ").strip()
            if not query:
                break
            analyzer.search(query)
        except KeyboardInterrupt:
            print("\n👋 程式結束")
            break

if __name__ == "__main__":
    main()
