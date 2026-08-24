"""
Create tables and seed synthetic data.

All fabricated. No real fund names, AMCs, distributors, or performance figures.

    ./.venv/bin/python scripts/seed_data.py

Uses create_all rather than Alembic — there is one schema and no migration
history worth preserving yet. Switch to Alembic once the schema stops moving.
"""

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.models import (  # noqa: E402
    Base,
    Distributor,
    DistributorMemory,
    Fund,
)
from app.db.session import SessionLocal, engine  # noqa: E402

random.seed(7)  # reproducible demo data

CATEGORIES = ["Large Cap", "Mid Cap", "Small Cap", "Debt", "Hybrid", "Index"]
RISK = ["Low", "Moderate", "High", "Very High"]
REGIONS = ["North", "South", "East", "West"]
AUM_TIERS = ["Tier 1", "Tier 2", "Tier 3"]

FUND_PREFIXES = ["Meridian", "Northwind", "Cobalt", "Silverpine", "Kestrel", "Lantern"]
FUND_SUFFIXES = ["Growth Fund", "Advantage Fund", "Opportunities Fund", "Focused Fund"]

# Deliberately varied so comparisons are interesting rather than uniform noise.
DISTRIBUTOR_NAMES = [
    "Anand Wealth Advisors",
    "Bluestone Financial",
    "Crestview Investment Services",
    "Dhanvantari Capital",
    "Everline Advisory",
]

SUMMARIES = [
    "Sells mostly to salaried professionals in their 30s and 40s. Historically "
    "cautious about small caps after a bad 2018 experience. Responds well to "
    "downside-protection framing and rolling-return charts rather than "
    "point-to-point numbers.",
    "Large book, heavily debt-oriented. Has been asking about equity exposure "
    "for clients nearing retirement. Fee-sensitive — pushed back twice on "
    "expense ratios above 1.5%.",
    "Younger practice, growing fast, comfortable with volatility. Interested in "
    "thematic and small-cap ideas. Wants marketing collateral more than "
    "performance data.",
    "Conservative, long relationship. Prefers funds with a track record longer "
    "than five years and a stable fund manager. Dislikes frequent strategy "
    "changes.",
    "Mixed book across equity and hybrid. Recently lost two clients to a "
    "competitor on cost. Very responsive to peer-comparison data.",
]


def make_funds(n: int) -> list[Fund]:
    funds = []
    for i in range(n):
        category = CATEGORIES[i % len(CATEGORIES)]
        # Debt funds get lower returns and risk; equity gets the spread.
        if category == "Debt":
            r1, r3, r5 = (
                round(random.uniform(5, 8), 2),
                round(random.uniform(5, 7.5), 2),
                round(random.uniform(5, 7), 2),
            )
            risk, expense = "Low", round(random.uniform(0.2, 0.9), 2)
        elif category == "Index":
            r1, r3, r5 = (
                round(random.uniform(8, 22), 2),
                round(random.uniform(10, 16), 2),
                round(random.uniform(9, 14), 2),
            )
            risk, expense = "Moderate", round(random.uniform(0.1, 0.4), 2)
        else:
            r1, r3, r5 = (
                round(random.uniform(-6, 34), 2),
                round(random.uniform(4, 26), 2),
                round(random.uniform(6, 21), 2),
            )
            risk = random.choice(RISK[1:])
            expense = round(random.uniform(0.8, 2.900), 2)

        funds.append(
            Fund(
                id=uuid.uuid4(),
                name=f"{FUND_PREFIXES[i % len(FUND_PREFIXES)]} "
                f"{category} {FUND_SUFFIXES[i % len(FUND_SUFFIXES)]}",
                category=category,
                aum=round(random.uniform(250, 42000), 2),
                expense_ratio=expense,
                return_1y=r1,
                return_3y=r3,
                return_5y=r5,
                benchmark_name=f"Synthetic {category} TRI",
                risk_rating=risk,
                manager_name=f"Manager {chr(65 + (i % 12))}",
                inception_date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=random.randint(800, 4200)),
            )
        )
    return funds


def make_distributors() -> list[tuple[Distributor, DistributorMemory]]:
    rows = []
    for i, name in enumerate(DISTRIBUTOR_NAMES):
        dist_id = uuid.uuid4()
        distributor = Distributor(
            id=dist_id,
            name=name,
            region=REGIONS[i % len(REGIONS)],
            aum_tier=AUM_TIERS[i % len(AUM_TIERS)],
            risk_appetite=RISK[i % len(RISK)],
            preferred_asset_classes=random.sample(CATEGORIES, k=2),
            relationship_start_date=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=random.randint(120, 2200)),
        )
        memory = DistributorMemory(
            id=uuid.uuid4(),
            distributor_id=dist_id,
            structured_fields={
                "aum_tier": distributor.aum_tier,
                "risk_appetite": distributor.risk_appetite,
                "preferred_asset_classes": distributor.preferred_asset_classes,
                "recent_topics": random.sample(
                    [
                        "expense ratios",
                        "small cap volatility",
                        "SIP flows",
                        "debt fund duration",
                        "exit loads",
                        "fund manager tenure",
                    ],
                    k=3,
                ),
                "known_objections": random.sample(
                    [
                        "fees too high versus index options",
                        "worried about drawdowns for retiree clients",
                        "wants longer track record",
                        "competitor offering better commission",
                    ],
                    k=2,
                ),
            },
            rolling_summary=SUMMARIES[i % len(SUMMARIES)],
            last_updated=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        rows.append((distributor, memory))
    return rows


def main() -> int:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)
    print("tables created")

    session = SessionLocal()
    try:
        if session.query(Distributor).count() > 0:
            print("data already present — dropping and reseeding")
            session.query(DistributorMemory).delete()
            session.query(Distributor).delete()
            session.query(Fund).delete()
            session.commit()

        funds = make_funds(24)
        session.add_all(funds)

        pairs = make_distributors()
        for distributor, memory in pairs:
            session.add(distributor)
            session.add(memory)

        session.commit()

        print(f"\nseeded {len(funds)} funds, {len(pairs)} distributors\n")
        print("distributor IDs (use one in the frontend):")
        for distributor, _ in pairs:
            print(f"  {distributor.id}  {distributor.name}")
        print("\nsample funds:")
        for fund in funds[:5]:
            print(
                f"  {fund.name:<52} 1y {fund.return_1y:>6}%  "
                f"ER {fund.expense_ratio}%"
            )
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
