"""Minimal Turso (hosted SQLite) client over its HTTP API, shaped like the sqlite3 connection we use.

Supports: con.execute(sql, params) -> cursor (fetchone/fetchall/lastrowid), con.executescript(sql),
con.commit(), con.close(), and rows readable as r["col"], r[0] or dict(r).
Writes (INSERT/UPDATE/DELETE) are buffered and sent in batches on commit() or before the next read,
so bulk inserts take a few HTTP requests instead of thousands.
Docs: https://docs.turso.tech/sdk/http/reference
"""
import base64
import json
import sqlite3

import requests

BATCHED = ("INSERT", "UPDATE", "DELETE", "REPLACE")
MAX_BATCH_BYTES = 2_000_000
_session = requests.Session()


class Row:
    def __init__(self, cols, values):
        self._cols, self._values = cols, values

    def keys(self):
        return self._cols

    def __getitem__(self, k):
        return self._values[k] if isinstance(k, int) else self._values[self._cols.index(k)]


class Cursor:
    def __init__(self, rows=None, lastrowid=None):
        self.rows, self.lastrowid = rows or [], lastrowid

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, (bool, int)):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, bytes):
        return {"type": "blob", "base64": base64.b64encode(v).decode()}
    return {"type": "text", "value": str(v)}


def _value(v):
    t = v.get("type")
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "blob":
        return base64.b64decode(v["base64"])
    return None if t == "null" else v.get("value")


class Connection:
    def __init__(self, url, token):
        self.endpoint = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.pending = []   # (sql, params, cursor) waiting to be sent

    def _send(self, stmts):
        """Run statements in one HTTP request. Returns one result per statement; raises on the first error."""
        body = {"requests": [{"type": "execute", "stmt": {"sql": s, "args": [_arg(a) for a in p]}} for s, p in stmts]
                + [{"type": "close"}]}
        r = _session.post(self.endpoint, headers=self.headers, data=json.dumps(body), timeout=60)
        r.raise_for_status()
        out = []
        for (sql, _), res in zip(stmts, r.json()["results"]):
            if res["type"] == "error":
                raise sqlite3.OperationalError(f"{res['error'].get('message')} (in: {sql[:80]})")
            out.append(res["response"]["result"])
        return out

    def _flush(self):
        batch, size = [], 0
        for item in self.pending + [None]:
            if item is None or (batch and (size > MAX_BATCH_BYTES or len(batch) >= 1000)):
                if batch:   # one transaction per batch: much faster than committing every statement
                    results = self._send([("BEGIN", ())] + [(s, p) for s, p, _ in batch] + [("COMMIT", ())])[1:-1]
                    for (_, _, cur), res in zip(batch, results):
                        cur.lastrowid = int(res["last_insert_rowid"]) if res.get("last_insert_rowid") else None
                batch, size = [], 0
            if item is not None:
                batch.append(item)
                size += len(item[0]) + sum(len(str(a)) for a in item[1])
        self.pending = []

    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith(BATCHED):
            cur = Cursor()
            self.pending.append((sql, tuple(params), cur))
            return cur
        self._flush()   # reads/DDL see all earlier writes
        res = self._send([(sql, tuple(params))])[0]
        cols = [c["name"] for c in res["cols"]]
        return Cursor([Row(cols, [_value(v) for v in row]) for row in res["rows"]],
                      int(res["last_insert_rowid"]) if res.get("last_insert_rowid") else None)

    def executescript(self, script):
        self._flush()
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        self._send([(s, ()) for s in stmts])

    def commit(self):
        self._flush()

    def close(self):
        self._flush()
