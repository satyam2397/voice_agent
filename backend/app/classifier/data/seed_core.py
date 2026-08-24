"""
Hand-written seed examples, one list per category.

These are the semantic backbone. Templates in templates.py expand around them
for volume, but the discriminating signal comes from here.

Rules followed while writing these:
  - Label on INTENT, not syntax (LABEL_SCHEMA R1). Plenty of triggers here are
    not questions; plenty of questions here are not triggers.
  - Hard negatives are written as PAIRS with their positive, so the model sees
    minimally-different examples on both sides of the boundary.
  - Distributor speech only, except `rep_turn`, which is rep speech appearing
    as a target because diarization sometimes mislabels it.
  - No real fund names, firms, or people.

Style is deliberately uneven — clipped, verbose, hedged, blunt — because real
speech is, and a corpus of uniformly well-formed sentences teaches the model
that well-formedness is the signal.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TRIGGER CATEGORIES
# ---------------------------------------------------------------------------

FUND_FACTUAL = [
    "what's the expense ratio on that one",
    "how much has it returned over three years",
    "who manages the fund",
    "what's the aum on this",
    "when was it launched",
    "is there an exit load on it",
    "what's the current portfolio turnover",
    "how many stocks does it hold",
    "what's the one year number looking like",
    "give me the five year cagr on that",
    "what's the benchmark for it",
    "what's the risk rating on this one",
    "how big is the fund now",
    "and the expense on the direct plan",
    "what's the minimum sip amount",
    "how long has the current manager been running it",
    "tell me the three year returns again",
    "what category does this fall under",
    "i want to know the standard deviation on it",
    "what's the top holding",
    "is it large cap or flexi cap",
    "what were the returns last financial year",
    "how much of it is in cash right now",
    "what's the sharpe on that fund",
    "remind me what the ter is",
    "does it have a lock in",
    "i'd like the actual numbers on that fund",
    "can you tell me the inception date",
    "what's the fund size these days",
    "i need the trailing returns for that one",
]

FUND_COMPARISON = [
    "how does it compare to the category average",
    "which of the two has done better over five years",
    "is it cheaper than the index option",
    "how's it stacked up against the benchmark",
    "compare that to your mid cap fund for me",
    "your fund versus the passive one, what's the difference",
    "which one would you say has been more consistent",
    "how does that expense ratio compare to peers",
    "between those two which has lower drawdown",
    "is the large cap doing better than the flexi cap",
    "put those side by side for me",
    "how does this stack up next to what the competition offers",
    "same category, how do you rank against others",
    "i want to see this against the nifty",
    "which has the better three year record",
    "is your hybrid better than just doing debt plus equity myself",
    "how different are the returns really between the two",
    "show me both funds together",
    "against a plain index fund does this justify the cost",
    "who's ahead over five years, yours or theirs",
    "the two mid caps you mentioned, which is stronger",
    "i'd want to see how it measures up to the category",
    "relative to peers where does it sit",
    "is one of them clearly better or is it a wash",
    "how do the risk numbers compare between those",
]

OBJECTION_PERFORMANCE = [
    "your three year numbers lagged the index though",
    "honestly the returns haven't been great",
    "it underperformed last year didn't it",
    "i've seen better from other funds in that space",
    "that track record isn't very convincing",
    "the fund's been flat for a while now",
    "my clients would look at that and ask why bother",
    "you had a bad run in twenty two, what changed",
    "returns look mediocre next to what else is out there",
    "i'd need to see better numbers before i push this",
    "the performance just hasn't kept up",
    "one good year doesn't make a track record",
    "it's been a laggard in that category for a while",
    "not sure the numbers justify the pitch",
    "how do you explain the dip in performance",
    "your fund missed the whole rally last year",
    "the consistency isn't there frankly",
    "compared to what my clients already hold this looks weak",
    "i remember this fund doing poorly a couple years back",
    "the recent numbers are fine but the longer record isn't",
    "i'd want to understand why it fell behind",
    "that's underwhelming for a fund of that size",
]

OBJECTION_COST = [
    "that expense ratio is steep",
    "you're not exactly cheap compared to the index option",
    "two percent is a lot to justify to a client",
    "the fees eat into what my clients actually get",
    "why should they pay that much when passive costs a fraction",
    "the commission structure isn't great for us either",
    "cost is the first thing my clients ask about",
    "that's on the higher side for the category",
    "i've got cheaper options on my shelf already",
    "hard to defend that ter honestly",
    "the total cost adds up over a long holding period",
    "your fees are higher than the two i currently recommend",
    "for that price i'd expect more outperformance",
    "clients are getting fee conscious these days",
    "the expense is what'll stop this from moving",
    "i can't sell something that costs that much without a story",
    "cheaper funds in the same category have done just as well",
    "what am i paying that expense ratio for exactly",
    "the pricing is the sticking point for me",
    "that's a rich fee for a large cap fund",
]

OBJECTION_RISK = [
    "my clients can't stomach that kind of drawdown",
    "that's too volatile for the people i deal with",
    "small caps make my retirees nervous",
    "what happens to this in a bad market",
    "the swings on that would scare my clients off",
    "i'd need to see how it handles a downturn",
    "that risk rating is going to be a problem for my book",
    "how far did it fall in the last correction",
    "too much concentration risk for my comfort",
    "my clients are conservative, this feels aggressive",
    "downside protection matters more to them than upside",
    "i'm not comfortable putting retirement money in that",
    "the volatility is higher than what i usually recommend",
    "what's the worst drawdown it's seen",
    "that category has burned my clients before",
    "sounds risky for someone five years from retiring",
    "i worry about how it behaves when things turn",
    "the risk profile doesn't match most of my book",
    "is there anything with a smoother ride",
    "i'd be nervous recommending that to older clients",
]

SUITABILITY_MATCH = [
    "would this work for conservative retirees",
    "does this fit a client with a five year horizon",
    "most of my book is salaried professionals, is this right for them",
    "i'm not sure that fits the kind of clients i have",
    "who is this actually meant for",
    "would you put a first time investor in this",
    "my clients mostly do sip, does that work here",
    "is this suitable for someone in their sixties",
    "i deal with a lot of small ticket investors, does that matter",
    "does this make sense for a ten year goal",
    "not sure my clients would go for something like this",
    "what kind of investor is the right fit",
    "i mostly sell debt, would this even land with my clients",
    "would this suit someone saving for a child's education",
    "for a client who wants steady income is this appropriate",
    "my book skews conservative so i'm unsure about this one",
    "is this a core holding or a satellite",
    "would this be too aggressive for a first portfolio",
    "does this fit people who panic when markets drop",
    "i'd need to know if this matches my client profile",
]

HISTORICAL_REFERENCE = [
    "is this the one you mentioned last quarter",
    "what happened to the fund we discussed last time",
    "you brought something similar to me a few months back",
    "didn't we look at this one before",
    "last time you said the manager was changing, did that happen",
    "we talked about a mid cap option earlier this year, what was that",
    "is this different from what you pitched in the last meeting",
    "you'd promised to get back to me on the expense numbers",
    "the fund from our last conversation, how's it doing now",
    "i think we covered this one already, refresh me",
    "what was the other option you showed me previously",
    "you mentioned a change in strategy last time we met",
    "how has the one i invested in after our last meeting performed",
    "wasn't there an issue with this fund when we last spoke",
    "you said you'd check the drawdown numbers for me",
    "i recall discussing something in this category before",
]

PROCESS_OPERATIONAL = [
    "what's the minimum ticket size",
    "how long does onboarding take",
    "what documents do you need from the client",
    "is there an exit load if they redeem early",
    "how does the commission get paid out",
    "can clients start a sip mid month",
    "what's the process for switching between plans",
    "is the folio setup online now",
    "how quickly do redemptions settle",
    "what's the cut off time for same day nav",
    "do you support systematic transfer plans",
    "is there a lock in period on this",
    "what's the paperwork like for a corporate client",
    "how do i track my clients' holdings",
    "can they do a partial withdrawal",
    "what's the trail commission on this",
    "is there a minimum for additional purchases",
    "how does the kyc process work for new clients",
]

# ---------------------------------------------------------------------------
# NO-TRIGGER CATEGORIES
# ---------------------------------------------------------------------------

SMALL_TALK = [
    "how's the family doing",
    "traffic was terrible getting here",
    "did you catch the match last night",
    "nice office you've got",
    "how's business been treating you",
    "long week already isn't it",
    "the weather's been unbearable",
    "have you been travelling much lately",
    "good to finally meet in person",
    "how was your holiday",
    "coffee's decent here actually",
    "you've redecorated since last time",
    "who wouldn't want fifteen percent returns",
    "everyone's an expert these days aren't they",
    "my son just started college, time flies",
    "been meaning to catch up for months",
    "monsoon's been rough this year",
    "how's the new place working out",
    "i mostly sell debt funds",
    "we've been in this business twenty years now",
    "the industry's changed a lot",
    "that's a nice view from up here",
]

BACKCHANNEL = [
    "mhm",
    "right",
    "got it",
    "sure",
    "okay",
    "yeah",
    "i see",
    "understood",
    "makes sense",
    "fair enough",
    "ah okay",
    "hmm",
    "yes yes",
    "right right",
    "of course",
    "true",
    "okay okay",
    "go on",
    "uh huh",
    "alright",
]

LOGISTICS = [
    "can you email that over after this",
    "send me the factsheet when you get a chance",
    "let's set up another call next week",
    "do you have a deck you can share",
    "put that in writing for me",
    "i'll need something i can forward to my team",
    "share the one we just discussed",
    "can we pick this up on friday",
    "drop me the numbers on whatsapp",
    "who do i contact if i have questions later",
    "send across the application forms",
    "let me get my colleague on the next call",
    "can you come by again next month",
    "forward me whatever you have on that",
    "i'll review it and get back to you",
    "book something for after the quarter end",
]

SOFT_CLOSE = [
    "makes sense, let me think on it",
    "i'll run it past my team",
    "leave it with me",
    "sounds reasonable",
    "let me see how it fits",
    "i'll consider it for a few clients",
    "we'll see how it goes",
    "noted, thanks",
    "that's helpful, i'll come back to you",
    "alright let me sit with this",
    "i'm not saying no",
    "give me some time on this one",
    "fair, i'll take a look",
    "okay i'll keep it in mind",
    "i'll think about which clients it suits",
]

UNINTELLIGIBLE = [
    "the the uh",
    "sorry what was",
    "i mean the thing with",
    "yeah but the",
    "can you say that",
    "hold on the line's",
    "wait i didn't catch",
    "uh sorry go ahead",
    "no no i meant",
    "hmm the what now",
    "sorry you cut out",
    "come again",
    "what was that last",
    "didn't hear you there",
]

# Rep speech. These reach the classifier only when diarization mislabels them,
# and they must never fire a card — including when phrased as questions.
REP_TURN = [
    "let me pull that up for you",
    "so the three year numbers are ahead of the benchmark",
    "i can send you the factsheet after this",
    "what's your usual ticket size for these",
    "how many clients are you managing right now",
    "we launched this one about four years ago",
    "the expense ratio is one point two percent",
    "happy to walk you through the portfolio",
    "let me explain how the strategy works",
    "our manager has been with the fund since inception",
    "what kind of clients are you seeing most of",
    "i think this would suit your book well",
    "give me a second to find those numbers",
    "as i was saying the allocation is mostly large cap",
    "would you like me to compare it with something specific",
    "that's a fair point, let me address it",
    "we've seen strong inflows this year",
    "how has your book grown over the last year",
    "i'll be honest, last year was tough for us",
    "the fund follows a bottom up approach",
]

# ---------------------------------------------------------------------------
# HARD NEGATIVE PAIRS
# ---------------------------------------------------------------------------
# (trigger_text, trigger_category, negative_text, negative_category)
#
# Minimally different surface, opposite label. Without these the task collapses
# into keyword matching and the encoder buys nothing over the rules layer.

HARD_NEGATIVE_PAIRS = [
    ("how's the fund been doing", "fund_factual",
     "how's business been treating you", "small_talk"),

    ("that expense ratio is high", "objection_cost",
     "that fund did well for me personally", "small_talk"),

    ("is this the one from last quarter", "historical_reference",
     "send me the one we just discussed", "logistics"),

    ("not sure that fits my book", "suitability_match",
     "not sure, let me think about it", "soft_close"),

    ("what's the minimum investment", "process_operational",
     "what's the minimum you'd expect from a meeting like this", "small_talk"),

    ("i'd need to see the drawdown numbers", "objection_risk",
     "i'd need to see you again next month", "logistics"),

    ("how does it compare to the index", "fund_comparison",
     "how does it compare to meeting in person", "small_talk"),

    ("the returns concern me", "objection_performance",
     "the traffic concerns me, i should head out", "logistics"),

    ("what did the fund return last year", "fund_factual",
     "what did you do last year for the holidays", "small_talk"),

    ("would this suit my retiree clients", "suitability_match",
     "would this suit a friday afternoon call", "logistics"),

    ("your fees are higher than the alternative", "objection_cost",
     "your office is further than the alternative", "small_talk"),

    ("we discussed a mid cap fund last time", "historical_reference",
     "we discussed lunch last time, still owe you one", "small_talk"),

    ("is there a lock in on this", "process_operational",
     "is there a rush on this, can it wait", "logistics"),

    ("that's too volatile for my clients", "objection_risk",
     "that's too far for my clients to travel", "small_talk"),

    ("which of the two performed better", "fund_comparison",
     "which of the two days works better for you", "logistics"),

    ("i'm not convinced by the track record", "objection_performance",
     "i'm not convinced we need another meeting", "logistics"),

    ("what's the risk rating", "fund_factual",
     "what's the parking situation like here", "small_talk"),

    ("does this work for conservative clients", "suitability_match",
     "does thursday work for you", "logistics"),
]


CORE_BY_CATEGORY: dict[str, list[str]] = {
    "fund_factual": FUND_FACTUAL,
    "fund_comparison": FUND_COMPARISON,
    "objection_performance": OBJECTION_PERFORMANCE,
    "objection_cost": OBJECTION_COST,
    "objection_risk": OBJECTION_RISK,
    "suitability_match": SUITABILITY_MATCH,
    "historical_reference": HISTORICAL_REFERENCE,
    "process_operational": PROCESS_OPERATIONAL,
    "small_talk": SMALL_TALK,
    "backchannel": BACKCHANNEL,
    "logistics": LOGISTICS,
    "soft_close": SOFT_CLOSE,
    "unintelligible": UNINTELLIGIBLE,
    "rep_turn": REP_TURN,
}
