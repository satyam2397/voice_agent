"""
Generates synthetic funds, distributors, and distributor conversation
history for local dev/demo. No real fund, distributor, or employer data --
everything here is fabricated or derived from public factsheet formats.

Usage:
    python generate_data.py --funds 50 --distributors 20
    python generate_data.py --funds 20000 --distributors 5000   # for the
                                                                   # section 8b
                                                                   # scale test
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta

FUND_CATEGORIES = ["Large Cap", "Mid Cap", "Small Cap", "Debt", "Hybrid", "Index"]
RISK_RATINGS = ["Low", "Moderate", "High", "Very High"]


def generate_funds(n: int) -> list[dict]:
    funds = []
    for i in range(n):
        funds.append({
            "id": str(uuid.uuid4()),
            "name": f"Synthetic {random.choice(FUND_CATEGORIES)} Fund {i}",
            "category": random.choice(FUND_CATEGORIES),
            "aum": round(random.uniform(50, 50000), 2),
            "expense_ratio": round(random.uniform(0.1, 2.5), 2),
            "return_1y": round(random.uniform(-10, 35), 2),
            "return_3y": round(random.uniform(-5, 25), 2),
            "return_5y": round(random.uniform(0, 20), 2),
            "benchmark_name": "Synthetic Benchmark Index",
            "risk_rating": random.choice(RISK_RATINGS),
            "manager_name": f"Manager {i % 30}",
            "inception_date": (datetime.utcnow() - timedelta(days=random.randint(365, 3650))).isoformat(),
        })
    return funds


def generate_distributors(n: int) -> list[dict]:
    distributors = []
    for i in range(n):
        distributors.append({
            "id": str(uuid.uuid4()),
            "name": f"Synthetic Distributor {i}",
            "region": random.choice(["North", "South", "East", "West"]),
            "aum_tier": random.choice(["Tier 1", "Tier 2", "Tier 3"]),
            "risk_appetite": random.choice(RISK_RATINGS),
            "preferred_asset_classes": random.sample(FUND_CATEGORIES, k=2),
            "relationship_start_date": (datetime.utcnow() - timedelta(days=random.randint(30, 2000))).isoformat(),
        })
    return distributors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--funds", type=int, default=50)
    parser.add_argument("--distributors", type=int, default=20)
    args = parser.parse_args()

    funds = generate_funds(args.funds)
    distributors = generate_distributors(args.distributors)

    print(f"Generated {len(funds)} funds, {len(distributors)} distributors.")
    # TODO: bulk insert into Postgres via SQLAlchemy session, and generate
    # embeddings for a matching set of fund_documents chunks.
