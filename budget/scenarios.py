"""Pre-built scenarios from the iOS library, plus a real job-loss overlay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import uuid4

from .engine import Frequency, SimulationStatus, StateSnapshot, TemplateSnapshot
from .spendable import income_stop_states


@dataclass(frozen=True)
class ScenarioChange:
    name: str
    suggested_amount: float
    is_income: bool
    frequency: Frequency
    delay_days: int = 0


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    category: str
    changes: list[ScenarioChange]
    stop_income: bool = False


LIBRARY: list[Scenario] = [
    Scenario(
        "job-loss",
        "Job Loss",
        "Stop every income template and see how long the cash lasts.",
        "Emergencies",
        [],
        stop_income=True,
    ),
    Scenario(
        "medical",
        "Medical Emergency",
        "Unexpected $5,000 medical bill hitting in a week.",
        "Emergencies",
        [ScenarioChange("Medical Bill", 5000, False, Frequency.ONE_TIME, 7)],
    ),
    Scenario(
        "car-breakdown",
        "Car Breakdown",
        "Your car dies. $3,000 repair in three days.",
        "Emergencies",
        [ScenarioChange("Car Repair/Replacement", 3000, False, Frequency.ONE_TIME, 3)],
    ),
    Scenario(
        "hours-cut",
        "Hours Cut",
        "Smaller paycheck. Models $300 less every two weeks.",
        "Income Changes",
        [ScenarioChange("Reduced Pay", 300, False, Frequency.BIWEEKLY)],
    ),
    Scenario(
        "raise",
        "Get a Raise",
        "Extra $200 every two weeks, starting in 30 days.",
        "Income Changes",
        [ScenarioChange("Raise Increase", 200, True, Frequency.BIWEEKLY, 30)],
    ),
    Scenario(
        "side-hustle",
        "Start Side Hustle",
        "Extra $500/month from gig work, starting in 14 days.",
        "Income Changes",
        [ScenarioChange("Side Hustle Income", 500, True, Frequency.MONTHLY, 14)],
    ),
    Scenario(
        "bonus",
        "Bonus Coming",
        "Year-end bonus hitting in 30 days.",
        "Income Changes",
        [ScenarioChange("Annual Bonus", 3000, True, Frequency.ONE_TIME, 30)],
    ),
    Scenario(
        "tax-refund",
        "Tax Refund",
        "IRS sending money back in 60 days.",
        "Income Changes",
        [ScenarioChange("Tax Refund", 2500, True, Frequency.ONE_TIME, 60)],
    ),
    Scenario(
        "cut-subs",
        "Cut Subscriptions",
        "Cancel Netflix, Spotify, gym.",
        "Lifestyle",
        [
            ScenarioChange("Netflix (cut)", 15, True, Frequency.MONTHLY),
            ScenarioChange("Spotify (cut)", 11, True, Frequency.MONTHLY),
            ScenarioChange("Gym (cut)", 50, True, Frequency.MONTHLY),
        ],
    ),
    Scenario(
        "eat-out-less",
        "Eat Out Less",
        "Cook at home. $200/month back.",
        "Lifestyle",
        [ScenarioChange("Restaurant Savings", 200, True, Frequency.MONTHLY)],
    ),
    Scenario(
        "new-car",
        "New Car Payment",
        "Finance a vehicle at $450/month plus $50 insurance.",
        "Lifestyle",
        [
            ScenarioChange("Car Payment", 450, False, Frequency.MONTHLY, 30),
            ScenarioChange("Higher Insurance", 50, False, Frequency.MONTHLY, 30),
        ],
    ),
    Scenario(
        "vacation",
        "Vacation",
        "A $3,000 trip in 60 days.",
        "Big Purchases",
        [ScenarioChange("Vacation Expense", 3000, False, Frequency.ONE_TIME, 60)],
    ),
    Scenario(
        "new-phone",
        "New Phone",
        "$1,200 upgrade in two weeks.",
        "Big Purchases",
        [ScenarioChange("New Phone", 1200, False, Frequency.ONE_TIME, 14)],
    ),
    Scenario(
        "furniture",
        "Furniture",
        "$2,000 furnishing hit in 30 days.",
        "Big Purchases",
        [ScenarioChange("Furniture Purchase", 2000, False, Frequency.ONE_TIME, 30)],
    ),
    Scenario(
        "baby",
        "Having a Baby",
        "Daycare, supplies, insurance increase.",
        "Family",
        [
            ScenarioChange("Daycare", 1500, False, Frequency.MONTHLY, 90),
            ScenarioChange("Diapers & Supplies", 200, False, Frequency.MONTHLY, 90),
            ScenarioChange("Health Insurance Increase", 150, False, Frequency.MONTHLY, 30),
        ],
    ),
    Scenario(
        "married",
        "Getting Married",
        "Wedding costs plus spouse income.",
        "Family",
        [
            ScenarioChange("Wedding Costs", 10000, False, Frequency.ONE_TIME, 180),
            ScenarioChange("Spouse Income", 2000, True, Frequency.BIWEEKLY, 30),
        ],
    ),
    Scenario(
        "pet",
        "Pet Adoption",
        "Adoption fee plus monthly care.",
        "Family",
        [
            ScenarioChange("Adoption Fee", 300, False, Frequency.ONE_TIME, 14),
            ScenarioChange("Pet Food & Care", 100, False, Frequency.MONTHLY, 14),
            ScenarioChange("Pet Insurance", 40, False, Frequency.MONTHLY, 14),
        ],
    ),
    Scenario(
        "rent-increase",
        "Rent Increase",
        "Landlord raising rent $200/month in 60 days.",
        "Housing",
        [ScenarioChange("Rent Increase", 200, False, Frequency.MONTHLY, 60)],
    ),
    Scenario(
        "cheaper-place",
        "Move to Cheaper Place",
        "Downsize. Moving costs then $300/month savings.",
        "Housing",
        [
            ScenarioChange("Rent Savings", 300, True, Frequency.MONTHLY, 60),
            ScenarioChange("Moving Costs", 1500, False, Frequency.ONE_TIME, 45),
        ],
    ),
    Scenario(
        "buy-house",
        "Buy a House",
        "Down payment, mortgage, tax, stop rent.",
        "Housing",
        [
            ScenarioChange("Down Payment", 40000, False, Frequency.ONE_TIME, 90),
            ScenarioChange("Mortgage", 2200, False, Frequency.MONTHLY, 90),
            ScenarioChange("Property Tax", 400, False, Frequency.MONTHLY, 90),
            ScenarioChange("Stop Paying Rent", 1800, True, Frequency.MONTHLY, 90),
        ],
    ),
    Scenario(
        "freelance",
        "Go Freelance",
        "Stop salary. Variable freelance income plus SE tax and insurance.",
        "Career",
        [
            ScenarioChange("Freelance Income", 4000, True, Frequency.MONTHLY, 30),
            ScenarioChange("Self-Employment Tax", 600, False, Frequency.MONTHLY, 30),
            ScenarioChange("Health Insurance", 400, False, Frequency.MONTHLY, 30),
        ],
        stop_income=True,
    ),
    Scenario(
        "student-loans",
        "Pay Off Student Loans",
        "Extra $300/month toward debt.",
        "Lifestyle",
        [ScenarioChange("Extra Loan Payment", 300, False, Frequency.MONTHLY)],
    ),
    Scenario(
        "roommate-out",
        "Roommate Moves Out",
        "You cover their $700 share.",
        "Housing",
        [ScenarioChange("Roommate's Share (Lost)", 700, False, Frequency.MONTHLY, 30)],
    ),
    Scenario(
        "emergency-fund",
        "Build Emergency Fund",
        "Park $500/month as a planned outflow.",
        "Lifestyle",
        [ScenarioChange("Emergency Fund Contribution", 500, False, Frequency.MONTHLY)],
    ),
    Scenario(
        "get-roommate",
        "Get a Roommate",
        "Split rent. Slightly higher utilities.",
        "Housing",
        [
            ScenarioChange("Roommate's Rent Share", 600, True, Frequency.MONTHLY, 30),
            ScenarioChange("Higher Utilities", 50, False, Frequency.MONTHLY, 30),
        ],
    ),
]


def get_scenario(scenario_id: str) -> Scenario:
    for item in LIBRARY:
        if item.id == scenario_id:
            return item
    raise KeyError(scenario_id)


def overlay(
    scenario: Scenario, templates: list[TemplateSnapshot], start_date: date
) -> tuple[list[TemplateSnapshot], list[StateSnapshot]]:
    extras: list[TemplateSnapshot] = []
    extra_states: list[StateSnapshot] = []
    if scenario.stop_income:
        extra_states.extend(income_stop_states(templates, start_date))
    for change in scenario.changes:
        signed = abs(change.suggested_amount)
        amount = signed if change.is_income else -signed
        extras.append(
            TemplateSnapshot(
                id=uuid4(),
                name=change.name,
                amount=amount,
                frequency=change.frequency,
                anchor_date=start_date + timedelta(days=change.delay_days),
            )
        )
    return extras, extra_states


def skip_forever(template_id, start_date: date) -> StateSnapshot:
    return StateSnapshot(
        template_id=template_id, date=start_date, status=SimulationStatus.SKIP_FOREVER
    )
