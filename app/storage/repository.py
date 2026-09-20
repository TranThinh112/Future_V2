import json
import sqlite3
import time


class AuditRepository:
    def __init__(self,path="crypto.db"): self.db=sqlite3.connect(path); self.db.execute("CREATE TABLE IF NOT EXISTS audit(kind TEXT,payload TEXT,ts REAL)"); self.db.commit()
    def append(self,kind,payload): self.db.execute("INSERT INTO audit VALUES(?,?,?)",(kind,json.dumps(payload),time.time())); self.db.commit()
    def recent(self, limit=20):
        return [{"kind":kind,"payload":json.loads(payload),"timestamp":ts} for kind,payload,ts in self.db.execute("SELECT kind,payload,ts FROM audit ORDER BY ts DESC LIMIT ?",(limit,))]
    def close(self): self.db.close()
    def latest_by_symbol(self, kind):
        result={}
        for row in self.recent(1000):
            symbol=row["payload"].get("symbol")
            if row["kind"]==kind and symbol and symbol not in result: result[symbol]=row
        return result
