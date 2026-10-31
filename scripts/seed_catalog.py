"""CLI: seed only the synthetic catalogue, never attendance cases."""

from app.db.session import SessionLocal
from app.demo.catalog import seed

if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("Synthetic catalogue ready: 5 departments, 40 employees, 2 periods; no cases inserted.")
