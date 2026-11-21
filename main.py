"""Vehicle Test Data API
A small FastAPI + SQLite service for recording and querying vehicle test results
(emissions, braking, durability, etc.).
"""
import csv
import io
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

DB_PATH = os.getenv("VEHICLE_DB_PATH", "vehicle_tests.db")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Vehicle Test Data API",
    description="Record, search and summarise vehicle test results.",
    version="1.0.0",
)


# ---------- Models ----------
class TestType(str, Enum):
    emission = "emission"
    braking = "braking"
    durability = "durability"
    noise = "noise"
    safety = "safety"


class Result(str, Enum):
    pass_ = "pass"
    fail = "fail"


class TestRecordIn(BaseModel):
    vehicle_model: str = Field(..., min_length=1, examples=["Maruti Swift"])
    vehicle_type: str = Field(..., min_length=1, examples=["passenger"])
    test_type: TestType
    test_date: date
    measured_value: float = Field(..., examples=[0.85])
    unit: str = Field(..., examples=["g/km"])
    limit_value: float = Field(..., examples=[1.0])
    remarks: Optional[str] = None


class TestRecord(TestRecordIn):
    id: int
    result: Result


# ---------- Database ----------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_model TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                test_type TEXT NOT NULL,
                test_date TEXT NOT NULL,
                measured_value REAL NOT NULL,
                unit TEXT NOT NULL,
                limit_value REAL NOT NULL,
                result TEXT NOT NULL,
                remarks TEXT
            )
            """
        )


def compute_result(measured: float, limit: float) -> str:
    """A test passes when the measured value is within the limit."""
    return "pass" if measured <= limit else "fail"


def row_to_record(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------- Endpoints ----------
@app.get("/", tags=["health"])
def root():
    return {"service": "Vehicle Test Data API", "docs": "/docs"}


@app.post("/tests", response_model=TestRecord, status_code=201, tags=["tests"])
def create_test(record: TestRecordIn):
    result = compute_result(record.measured_value, record.limit_value)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO tests (vehicle_model, vehicle_type, test_type, test_date,
               measured_value, unit, limit_value, result, remarks)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.vehicle_model,
                record.vehicle_type,
                record.test_type.value,
                record.test_date.isoformat(),
                record.measured_value,
                record.unit,
                record.limit_value,
                result,
                record.remarks,
            ),
        )
        row = conn.execute("SELECT * FROM tests WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_record(row)


def build_filters(vehicle_model, vehicle_type, test_type, result, date_from, date_to):
    clauses, params = [], []
    if vehicle_model:
        clauses.append("vehicle_model LIKE ?")
        params.append(f"%{vehicle_model}%")
    if vehicle_type:
        clauses.append("vehicle_type = ?")
        params.append(vehicle_type)
    if test_type:
        clauses.append("test_type = ?")
        params.append(test_type.value)
    if result:
        clauses.append("result = ?")
        params.append(result.value)
    if date_from:
        clauses.append("test_date >= ?")
        params.append(date_from.isoformat())
    if date_to:
        clauses.append("test_date <= ?")
        params.append(date_to.isoformat())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@app.get("/tests", response_model=list[TestRecord], tags=["tests"])
def list_tests(
    vehicle_model: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    test_type: Optional[TestType] = None,
    result: Optional[Result] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    where, params = build_filters(vehicle_model, vehicle_type, test_type, result, date_from, date_to)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM tests {where} ORDER BY test_date DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, skip),
        ).fetchall()
    return [row_to_record(r) for r in rows]


@app.get("/tests/export", tags=["tests"])
def export_csv(
    vehicle_model: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    test_type: Optional[TestType] = None,
    result: Optional[Result] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    """Download matching test records as a CSV file."""
    where, params = build_filters(vehicle_model, vehicle_type, test_type, result, date_from, date_to)
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM tests {where} ORDER BY id", params).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "vehicle_model", "vehicle_type", "test_type", "test_date",
         "measured_value", "unit", "limit_value", "result", "remarks"]
    )
    for r in rows:
        writer.writerow([r[k] for k in r.keys()])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vehicle_tests.csv"},
    )


@app.get("/tests/stats/summary", tags=["stats"])
def stats_summary():
    """Pass/fail counts overall and per test type."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
        passed = conn.execute("SELECT COUNT(*) FROM tests WHERE result = 'pass'").fetchone()[0]
        by_type = conn.execute(
            """SELECT test_type,
                      COUNT(*) AS total,
                      SUM(CASE WHEN result = 'pass' THEN 1 ELSE 0 END) AS passed
               FROM tests GROUP BY test_type"""
        ).fetchall()
    return {
        "total_tests": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate_percent": round(passed / total * 100, 2) if total else 0.0,
        "by_test_type": [
            {
                "test_type": r["test_type"],
                "total": r["total"],
                "passed": r["passed"],
                "failed": r["total"] - r["passed"],
            }
            for r in by_type
        ],
    }


@app.get("/tests/{test_id}", response_model=TestRecord, tags=["tests"])
def get_test(test_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Test record not found")
    return row_to_record(row)


@app.put("/tests/{test_id}", response_model=TestRecord, tags=["tests"])
def update_test(test_id: int, record: TestRecordIn):
    result = compute_result(record.measured_value, record.limit_value)
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE tests SET vehicle_model=?, vehicle_type=?, test_type=?, test_date=?,
               measured_value=?, unit=?, limit_value=?, result=?, remarks=? WHERE id=?""",
            (
                record.vehicle_model,
                record.vehicle_type,
                record.test_type.value,
                record.test_date.isoformat(),
                record.measured_value,
                record.unit,
                record.limit_value,
                result,
                record.remarks,
                test_id,
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Test record not found")
        row = conn.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
    return row_to_record(row)


@app.delete("/tests/{test_id}", status_code=204, tags=["tests"])
def delete_test(test_id: int):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Test record not found")
