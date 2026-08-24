"""
Compositional templates for expanding the seed corpus.

Each template is a sentence frame with {slots}. Filling slots from varied
vocabularies produces volume without the mode collapse an LLM tends toward
when asked for "200 more examples like this".

IMPORTANT: these frames are used for train/val ONLY. The test_natural split is
hand-written with different frames, so test accuracy measures generalisation
rather than template memorisation. build_dataset.py enforces that with an
n-gram overlap check.
"""

from __future__ import annotations

# --- slot vocabularies ------------------------------------------------------

FUND = [
    "the large cap fund", "your mid cap one", "the small cap fund",
    "this debt fund", "the hybrid option", "your index fund",
    "the flexi cap", "that focused fund", "the one you mentioned",
    "your equity fund", "this scheme", "the growth fund",
]

RIVAL = [
    "the index option", "a passive fund", "what i already recommend",
    "the category average", "your competitor's fund", "the benchmark",
    "the other one you showed me", "a plain nifty fund",
    "the fund my clients already hold",
]

METRIC = [
    "expense ratio", "three year return", "five year number",
    "one year performance", "risk rating", "aum", "exit load",
    "turnover", "sharpe ratio", "standard deviation", "ter",
    "minimum sip", "track record",
]

CLIENT = [
    "my retiree clients", "first time investors", "conservative clients",
    "salaried professionals", "my hni book", "small ticket investors",
    "someone nearing retirement", "clients with a short horizon",
    "people who panic in a drawdown", "my regular sip clients",
]

HEDGE_OPEN = [
    "", "", "", "so ", "okay so ", "right, ", "hmm, ", "look, ",
    "honestly ", "i mean ", "just ", "quick one, ", "and ", "but ",
]

HEDGE_CLOSE = [
    "", "", "", "", " though", " really", " actually", " if you don't mind",
    " out of curiosity", " for my understanding",
]

CONCERN = [
    "worries me", "is a problem for my book", "would put my clients off",
    "is the sticking point", "makes me hesitate", "is hard to defend",
    "doesn't sit right with me", "is what'll stop this",
]

PAST = [
    "last quarter", "last time we met", "in our last conversation",
    "a few months back", "earlier this year", "the previous meeting",
    "when you came by last", "last time",
]

# --- templates --------------------------------------------------------------
# {slot} names must exist in SLOTS below.

TEMPLATES: dict[str, list[str]] = {
    "fund_factual": [
        "{open}what's the {metric} on {fund}{close}",
        "{open}tell me the {metric} for {fund}",
        "{open}i need the {metric} on {fund}",
        "{open}what's {fund}'s {metric}{close}",
        "{open}can you give me the {metric}{close}",
        "{open}remind me what the {metric} is on {fund}",
        "{open}how much is the {metric} for {fund}",
        "{open}do you have the {metric} handy",
        "{open}what does {fund} show for {metric}",
    ],
    "fund_comparison": [
        "{open}how does {fund} compare to {rival}{close}",
        "{open}{fund} versus {rival}, which is better",
        "{open}put {fund} next to {rival} for me",
        "{open}is {fund} better than {rival} on {metric}",
        "{open}how does the {metric} compare against {rival}",
        "{open}between {fund} and {rival} which would you pick",
        "{open}i want to see {fund} against {rival}",
        "{open}where does {fund} sit relative to {rival}",
    ],
    "objection_performance": [
        "{open}the returns on {fund} {concern}",
        "{open}{fund} hasn't kept up with {rival}",
        "{open}the track record on {fund} {concern}",
        "{open}i've seen better numbers than {fund}",
        "{open}{fund} underperformed {rival} didn't it",
        "{open}the performance {concern}{close}",
        "{open}not convinced by what {fund} has delivered",
    ],
    "objection_cost": [
        "{open}the {metric} on {fund} {concern}",
        "{open}{fund} costs more than {rival}",
        "{open}that fee {concern}{close}",
        "{open}why pay that when {rival} costs less",
        "{open}the cost of {fund} {concern}",
        "{open}hard to justify that expense next to {rival}",
    ],
    "objection_risk": [
        "{open}{fund} is too volatile for {client}",
        "{open}the risk on {fund} {concern}",
        "{open}how does {fund} hold up in a downturn",
        "{open}i'd need to see the drawdown on {fund}",
        "{open}{client} couldn't handle those swings",
        "{open}the volatility {concern} for {client}",
    ],
    "suitability_match": [
        "{open}would {fund} work for {client}",
        "{open}is {fund} right for {client}",
        "{open}does {fund} suit {client}{close}",
        "{open}not sure {fund} fits {client}",
        "{open}who is {fund} actually meant for",
        "{open}would you put {client} in {fund}",
    ],
    "historical_reference": [
        "{open}is {fund} the one you mentioned {past}",
        "{open}what happened to the fund we discussed {past}",
        "{open}didn't we look at {fund} {past}",
        "{open}you said something about {fund} {past}",
        "{open}how's the one from {past} doing now",
        "{open}we covered this {past}, refresh me",
    ],
    "process_operational": [
        "{open}what's the minimum for {fund}",
        "{open}is there a lock in on {fund}",
        "{open}how does onboarding work for {fund}",
        "{open}what's the exit load on {fund}",
        "{open}how long do redemptions take",
        "{open}what paperwork do you need for {fund}",
    ],
    "small_talk": [
        "{open}how's everything going{close}",
        "{open}been a busy week hasn't it",
        "{open}good to see you again{close}",
        "{open}how's the family",
        "{open}traffic was bad coming over",
        "{open}nice place you have here",
    ],
    "logistics": [
        "{open}can you send me the details on {fund}",
        "{open}email me whatever you have on {fund}",
        "{open}let's pick this up next week",
        "{open}share the factsheet for {fund}",
        "{open}put that in writing for me",
        "{open}can we schedule another call",
    ],
    "soft_close": [
        "{open}let me think about {fund}",
        "{open}i'll run {fund} past my team",
        "{open}leave it with me{close}",
        "{open}i'll see which clients {fund} suits",
        "{open}give me some time on this",
    ],
    "backchannel": [
        "{ack}",
        "{ack} {ack2}",
        "{ack}, {ack2}",
        "{ack} {ack} ",
        "{filler} {ack}",
        "{ack} {filler}",
    ],
    "unintelligible": [
        "{filler} the {filler}",
        "sorry {filler} what",
        "{filler} i didn't {filler}",
        "wait {filler} back up",
        "no i meant the {filler}",
        "{filler} you cut out there",
        "hold on {filler}",
        "can you {filler} again",
    ],
    "rep_turn": [
        "let me pull up the {metric} for you",
        "the {metric} on {fund} is competitive",
        "i can send you details on {fund} after this",
        "what's your usual ticket size for {client}",
        "{fund} would suit {client} well i think",
        "let me walk you through how {fund} works",
        "how many of {client} are you working with",
    ],
}

ACK = [
    "mhm", "right", "okay", "sure", "yeah", "got it", "i see", "understood",
    "fair enough", "of course", "true", "alright", "yes", "hmm", "uh huh",
    "noted", "gotcha", "makes sense",
]

FILLER = ["uh", "um", "er", "sorry", "the", "hang on", "wait", "hmm"]

SLOTS = {
    "fund": FUND,
    "rival": RIVAL,
    "metric": METRIC,
    "client": CLIENT,
    "open": HEDGE_OPEN,
    "close": HEDGE_CLOSE,
    "concern": CONCERN,
    "past": PAST,
    "ack": ACK,
    "ack2": ACK,
    "filler": FILLER,
}

# --- conversation context ---------------------------------------------------
# Preceding turns, so the model learns to read a window rather than one line.

REP_CONTEXT = [
    "so this fund has been running about four years now",
    "the strategy is bottom up, mostly large cap",
    "happy to walk you through the numbers",
    "we've seen good inflows this year",
    "let me tell you about the portfolio construction",
    "the manager has been with us since launch",
    "i think this could fit your book nicely",
    "here's how it performed through the last cycle",
    "we recently reduced the expense ratio",
    "this one sits in the mid cap category",
    "let me pull up the factsheet",
    "the benchmark for this is a total return index",
]

DIST_CONTEXT = [
    "okay",
    "right",
    "mhm",
    "go on",
    "interesting",
    "i see",
    "sure",
    "and then",
    "makes sense so far",
    "alright",
]
