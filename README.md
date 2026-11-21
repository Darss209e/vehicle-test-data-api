# Vehicle Test Data API

A REST API built with **FastAPI** and **SQLite** for recording and querying vehicle test results (emission, braking, durability, noise, safety). Inspired by the kind of data handled in automotive testing and certification work.

## Features
- Create, read, update and delete test records (full CRUD)
- Automatic **pass/fail** result: a test passes when `measured_value <= limit_value`
- Filter by vehicle model, vehicle type, test type, result and date range, with pagination
- Summary statistics: overall and per-test-type pass rate
- Export matching records as a **CSV** file
- Input validation with Pydantic and automatic interactive docs at `/docs`
- Automated tests with pytest

## Tech Stack
Python, FastAPI, Pydantic, SQLite (`sqlite3`), Uvicorn, pytest

## Setup
```bash
git clone https://github.com/Darss209e/Vehicle-test-data.git
cd Vehicle-test-data
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000/docs to try the API in your browser.

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/tests` | Add a test record |
| GET | `/tests` | List records (filters: `vehicle_model`, `vehicle_type`, `test_type`, `result`, `date_from`, `date_to`, `skip`, `limit`) |
| GET | `/tests/{id}` | Get one record |
| PUT | `/tests/{id}` | Update a record |
| DELETE | `/tests/{id}` | Delete a record |
| GET | `/tests/stats/summary` | Pass/fail statistics |
| GET | `/tests/export` | Download records as CSV |

## Example
```bash
curl -X POST http://127.0.0.1:8000/tests \
  -H "Content-Type: application/json" \
  -d '{
    "vehicle_model": "Maruti Swift",
    "vehicle_type": "passenger",
    "test_type": "emission",
    "test_date": "2026-11-01",
    "measured_value": 0.85,
    "unit": "g/km",
    "limit_value": 1.0,
    "remarks": "CO emission test"
  }'
```
Response includes the generated `id` and `"result": "pass"`.

## Run tests
```bash
pytest
```

## Possible Improvements
- Authentication (JWT)
- Switch to SQLAlchemy / PostgreSQL
- Charts for test trends
- Docker support
