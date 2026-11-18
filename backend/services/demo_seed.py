"""Seed data for the recruiter demo inbox.

Everything here is fictional: people, companies and addresses all use the
reserved `.example` TLD so nothing can ever be delivered anywhere real.
Ages are minutes before the demo session starts, so the inbox always looks
fresh (and Gmail-style queries like `newer_than:7d` behave sensibly).
"""

from __future__ import annotations

DEMO_ADDRESS = "demo@mailmind-demo.example"
DEMO_FROM = f"Demo User <{DEMO_ADDRESS}>"

_H = 60
_D = 24 * _H

# Each entry: id, thread, from, to, subject, age (minutes), labels, unread, body.
# Labels mirror Gmail: "inbox"/"sent" folders plus categories and user labels.
SEED_MESSAGES: list[dict] = [
    {
        "id": "m01",
        "thread": "t-order",
        "from": "Hannah Okafor <hannah.okafor@brightmail.example>",
        "to": DEMO_FROM,
        "subject": "Order #4821 arrived damaged",
        "age": 14,
        "labels": {"inbox", "support"},
        "unread": True,
        "body": (
            "Hi,\n\n"
            "My order #4821 (the ceramic pour-over set) arrived this morning and the "
            "carafe was cracked straight down the side. The outer box looked fine, so "
            "I think it was packed loosely.\n\n"
            "I was planning to give this as a gift on Saturday. Can you send a "
            "replacement in time, or should I just ask for a refund?\n\n"
            "Photos attached in my next email if you need them.\n\n"
            "Thanks,\nHannah"
        ),
    },
    {
        "id": "m02",
        "thread": "t-recruiter",
        "from": "Priya Shah <priya.shah@northwind-talent.example>",
        "to": DEMO_FROM,
        "subject": "Senior Full-Stack Engineer role at Lumen Health",
        "age": 52,
        "labels": {"inbox", "work"},
        "unread": True,
        "body": (
            "Hi there,\n\n"
            "I came across your MCP + AI email assistant project and was really "
            "impressed. I'm recruiting for a Senior Full-Stack Engineer at Lumen "
            "Health - Python/FastAPI backend, React/Next.js frontend, and a growing "
            "LLM features team.\n\n"
            "The role is remote-friendly (US/EU time zones), and the range is "
            "competitive with equity. Would you be open to a 20-minute intro call "
            "this week? Tuesday or Thursday afternoon both work on my side.\n\n"
            "Best,\nPriya Shah\nTechnical Recruiter, Northwind Talent"
        ),
    },
    {
        "id": "m03",
        "thread": "t-launch",
        "from": "Marcus Chen <marcus.chen@lumacorp.example>",
        "to": DEMO_FROM,
        "subject": "Project Atlas launch plan",
        "age": 2 * _D + 3 * _H,
        "labels": {"inbox", "work"},
        "unread": False,
        "body": (
            "Hey,\n\n"
            "Kicking off the launch planning for Project Atlas. Rough plan:\n"
            "1. Feature freeze on the 14th\n"
            "2. Two weeks of beta with the design partners\n"
            "3. Public launch + blog post at the end of the month\n\n"
            "Can you own the API docs and the migration guide? Let me know if the "
            "dates look realistic from the backend side.\n\n"
            "Marcus"
        ),
    },
    {
        "id": "m04",
        "thread": "t-launch",
        "from": DEMO_FROM,
        "to": "Marcus Chen <marcus.chen@lumacorp.example>",
        "subject": "Re: Project Atlas launch plan",
        "age": 2 * _D,
        "labels": {"sent"},
        "unread": False,
        "body": (
            "Hi Marcus,\n\n"
            "Happy to own the API docs and migration guide. The freeze date works, "
            "but the beta might need an extra few days - the rate-limiting changes "
            "aren't merged yet. I'll confirm once that PR lands.\n\n"
            "Thanks"
        ),
    },
    {
        "id": "m05",
        "thread": "t-launch",
        "from": "Marcus Chen <marcus.chen@lumacorp.example>",
        "to": DEMO_FROM,
        "subject": "Re: Project Atlas launch plan",
        "age": 3 * _H,
        "labels": {"inbox", "work"},
        "unread": True,
        "body": (
            "Thanks! Leadership is asking for a firm date by Friday. Did the "
            "rate-limiting PR land? If we need the extra days for beta, I'd rather "
            "tell them now than slip later.\n\n"
            "Marcus"
        ),
    },
    {
        "id": "m06",
        "thread": "t-interview",
        "from": "Jordan Lee <jordan.lee@acme-robotics.example>",
        "to": DEMO_FROM,
        "subject": "Interview availability - Platform Engineer",
        "age": 5 * _H,
        "labels": {"inbox", "work"},
        "unread": True,
        "body": (
            "Hello,\n\n"
            "Thanks for applying to the Platform Engineer position at Acme Robotics. "
            "We'd love to schedule a 45-minute technical interview with the team.\n\n"
            "Could you share two or three time slots that work for you next week? "
            "We're flexible between 9am and 4pm Pacific.\n\n"
            "Kind regards,\nJordan Lee\nEngineering Manager, Acme Robotics"
        ),
    },
    {
        "id": "m07",
        "thread": "t-ci",
        "from": "BuildBot <ci@devhub.example>",
        "to": DEMO_FROM,
        "subject": "[mailmind] Build failed on main (#318)",
        "age": 7 * _H,
        "labels": {"inbox", "updates"},
        "unread": True,
        "body": (
            "Workflow: CI\nBranch: main\nCommit: a41f9c2 \"refactor email parser\"\n"
            "Status: FAILED (backend job)\n\n"
            "tests/test_email_parsing.py::test_parse_list_blob - AssertionError\n\n"
            "View the full log in DevHub Actions."
        ),
    },
    {
        "id": "m08",
        "thread": "t-roadmap",
        "from": "Elena Rossi <elena.rossi@lumacorp.example>",
        "to": DEMO_FROM,
        "subject": "Q3 roadmap feedback needed by Friday",
        "age": 1 * _D + 2 * _H,
        "labels": {"inbox", "work"},
        "unread": True,
        "body": (
            "Hi team,\n\n"
            "The Q3 roadmap draft is in the shared folder. Please leave comments by "
            "Friday EOD - especially on the search revamp and the mobile offline "
            "mode, since those two compete for the same engineers.\n\n"
            "If you think something big is missing, flag it now rather than at "
            "planning.\n\n"
            "Thanks,\nElena"
        ),
    },
    {
        "id": "m09",
        "thread": "t-hike",
        "from": "Alex Rivera <alex.rivera@brightmail.example>",
        "to": DEMO_FROM,
        "subject": "Hiking this weekend?",
        "age": 1 * _D + 6 * _H,
        "labels": {"inbox", "personal"},
        "unread": False,
        "body": (
            "Hey! Weather looks great on Saturday. Thinking of doing the ridge trail "
            "- about 12 km, start around 8am. Want to join? I can drive.\n\n"
            "Alex"
        ),
    },
    {
        "id": "m10",
        "thread": "t-cloudly",
        "from": "Cloudly Billing <billing@cloudly.example>",
        "to": DEMO_FROM,
        "subject": "Your Cloudly receipt - $24.00",
        "age": 3 * _D,
        "labels": {"inbox", "receipts", "updates"},
        "unread": False,
        "body": (
            "Thanks for your payment.\n\n"
            "Plan: Hobby (monthly)\nAmount: $24.00\nInvoice: CL-2026-10-0931\n"
            "Payment method: Visa ending 4242\n\n"
            "You can download a PDF invoice from your billing dashboard."
        ),
    },
    {
        "id": "m11",
        "thread": "t-talk",
        "from": "DevConf Program Committee <program@devconf.example>",
        "to": DEMO_FROM,
        "subject": "Your talk proposal was accepted!",
        "age": 4 * _D,
        "labels": {"inbox"},
        "unread": True,
        "body": (
            "Congratulations! Your talk \"Giving LLMs safe hands: tool calling with "
            "MCP\" has been accepted for DevConf.\n\n"
            "Please confirm your attendance and send a speaker bio (under 80 words) "
            "and headshot within 7 days.\n\n"
            "- DevConf Program Committee"
        ),
    },
    {
        "id": "m12",
        "thread": "t-flight",
        "from": "SkyJet <bookings@skyjet.example>",
        "to": DEMO_FROM,
        "subject": "Booking confirmed: SFO to SEA, Nov 28",
        "age": 6 * _D,
        "labels": {"inbox", "receipts", "travel"},
        "unread": False,
        "body": (
            "Your booking is confirmed.\n\n"
            "Confirmation code: QX7P2L\nFlight SJ 418, departs SFO 7:15am, "
            "arrives SEA 9:20am\nSeat: 14C\n\n"
            "Online check-in opens 24 hours before departure."
        ),
    },
    {
        "id": "m13",
        "thread": "t-security",
        "from": "Account Security <no-reply@accounts.example>",
        "to": DEMO_FROM,
        "subject": "New sign-in from Chrome on macOS",
        "age": 8 * _D,
        "labels": {"inbox", "updates"},
        "unread": False,
        "body": (
            "We noticed a new sign-in to your account from Chrome on macOS "
            "(San Francisco, CA).\n\n"
            "If this was you, no action is needed. If not, reset your password "
            "right away."
        ),
    },
    {
        "id": "m14",
        "thread": "t-newsletter",
        "from": "The Weekly Byte <hello@weeklybyte.example>",
        "to": DEMO_FROM,
        "subject": "This week: vector DBs, edge functions, and a Rust rewrite",
        "age": 9 * _D,
        "labels": {"inbox", "promotions", "newsletters"},
        "unread": False,
        "body": (
            "In this issue:\n"
            "- Do you actually need a vector database?\n"
            "- Edge functions vs. regional servers: a latency deep-dive\n"
            "- One team's honest Rust rewrite retrospective\n\n"
            "Read online or unsubscribe anytime."
        ),
    },
    {
        "id": "m15",
        "thread": "t-coffee",
        "from": DEMO_FROM,
        "to": "Sam Patel <sam.patel@brightmail.example>",
        "subject": "Coffee next week?",
        "age": 12 * _D,
        "labels": {"sent"},
        "unread": False,
        "body": (
            "Hey Sam,\n\nIt's been a while! Free for coffee next Wednesday morning? "
            "The place by the station is still my favourite.\n\nCheers"
        ),
    },
    {
        "id": "m16",
        "thread": "t-invoice",
        "from": DEMO_FROM,
        "to": "Accounts Payable <ap@quillstudio.example>",
        "subject": "Invoice for October consulting",
        "age": 20 * _D,
        "labels": {"sent", "work"},
        "unread": False,
        "body": (
            "Hello,\n\nPlease find my invoice for October consulting attached "
            "(16 hours, $1,920.00). Payment terms are net 30.\n\nThank you!"
        ),
    },
    {
        "id": "m17",
        "thread": "t-sale",
        "from": "GearHaus <deals@gearhaus.example>",
        "to": DEMO_FROM,
        "subject": "48 hours only: 40% off standing desks",
        "age": 25 * _D,
        "labels": {"inbox", "promotions"},
        "unread": False,
        "body": (
            "Our biggest sale of the season is here. Standing desks, monitor arms "
            "and ergonomic chairs - up to 40% off for the next 48 hours.\n\n"
            "Shop now. Unsubscribe anytime."
        ),
    },
]
