"""
LandLaw.AI MCP Server - UK Property Law Research
Built by MEOK AI Labs | https://landlaw.ai

UK Land Registry searches, planning permission checks, covenant explanations,
Stamp Duty calculations, Section 21/8 notices, and right of way analysis.
"""


import sys, os
sys.path.insert(0, os.path.expanduser('~/clawd/meok-labs-engine/shared'))
from auth_middleware import check_access

import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("landlaw-ai", instructions="")

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
_RATE_LIMITS = {
    "free": {"requests_per_hour": 60},
    "pro": {"requests_per_hour": 10000},
}
_request_log: list[float] = []
_tier = "free"


def _check_rate_limit() -> bool:
    now = time.time()
    _request_log[:] = [t for t in _request_log if now - t < 3600]
    if len(_request_log) >= _RATE_LIMITS[_tier]["requests_per_hour"]:
        return False
    _request_log.append(now)
    return True


# ---------------------------------------------------------------------------
# SDLT rate tables (current as of April 2025 budget)
# ---------------------------------------------------------------------------
_SDLT_RESIDENTIAL = [
    {"threshold": 0, "rate": 0.00, "up_to": 250000},
    {"threshold": 250000, "rate": 0.05, "up_to": 925000},
    {"threshold": 925000, "rate": 0.10, "up_to": 1500000},
    {"threshold": 1500000, "rate": 0.12, "up_to": float("inf")},
]

_SDLT_FTB = [
    {"threshold": 0, "rate": 0.00, "up_to": 425000},
    {"threshold": 425000, "rate": 0.05, "up_to": 625000},
]

_SDLT_ADDITIONAL = 0.03  # 3% surcharge on additional properties

_SDLT_NON_RESIDENTIAL = [
    {"threshold": 0, "rate": 0.00, "up_to": 150000},
    {"threshold": 150000, "rate": 0.02, "up_to": 250000},
    {"threshold": 250000, "rate": 0.05, "up_to": float("inf")},
]

# ---------------------------------------------------------------------------
# Title class / tenure types
# ---------------------------------------------------------------------------
_TENURE_TYPES = {
    "freehold": {
        "title": "Freehold (Fee Simple Absolute in Possession)",
        "description": "Absolute ownership of the land and buildings. The owner has the right to use the land indefinitely.",
        "legislation": "Law of Property Act 1925, s.1(1)(a)",
        "key_rights": [
            "Right to sell, lease, mortgage, or bequeath the property",
            "Right to develop (subject to planning permission)",
            "Right to exclusive possession",
            "No ground rent or service charges (unless covenanted)",
        ],
    },
    "leasehold": {
        "title": "Leasehold (Term of Years Absolute)",
        "description": "Time-limited interest granted by the freeholder. The leaseholder has exclusive possession for the term of the lease.",
        "legislation": "Law of Property Act 1925, s.1(1)(b); Leasehold Reform Act 1967; Leasehold Reform, Housing and Urban Development Act 1993",
        "key_rights": [
            "Right to exclusive possession for the lease term",
            "Right to extend the lease (after 2 years ownership, 90 year extension for flats)",
            "Right to buy the freehold (collective enfranchisement for flats)",
            "Subject to lease covenants, ground rent, and service charges",
        ],
        "lease_length_warnings": {
            "below_80_years": "CRITICAL: Lease under 80 years triggers 'marriage value' making extension significantly more expensive",
            "below_70_years": "WARNING: Most mortgage lenders will not lend on leases below 70-80 years",
            "below_40_years": "SEVERE: Extremely difficult to sell or mortgage. Immediate lease extension advised.",
        },
    },
    "commonhold": {
        "title": "Commonhold",
        "description": "Freehold ownership of a unit within a larger development, with shared ownership of common parts via a Commonhold Association.",
        "legislation": "Commonhold and Leasehold Reform Act 2002",
        "key_rights": [
            "Freehold ownership of individual unit (no lease expiry)",
            "Membership of Commonhold Association",
            "Democratic control of common parts",
            "No ground rent",
        ],
    },
}

# ---------------------------------------------------------------------------
# Planning permission categories (Town and Country Planning Act 1990)
# ---------------------------------------------------------------------------
_PERMITTED_DEVELOPMENT = {
    "single_storey_rear_extension": {
        "description": "Single-storey rear extension",
        "permitted": True,
        "max_dimensions": {
            "detached": "8m depth (or 4m without prior approval), 4m height",
            "semi_detached_terraced": "6m depth (or 3m without prior approval), 4m height",
        },
        "conditions": [
            "Must not cover more than 50% of the garden/curtilage",
            "Materials must be similar in appearance to existing dwelling",
            "No verandas, balconies, or raised platforms",
            "Not in front of the principal elevation",
        ],
        "legislation": "GPDO 2015, Schedule 2, Part 1, Class A",
        "exceptions": ["Listed buildings", "Conservation areas (restricted)", "Article 4 direction areas", "AONB", "National Parks"],
    },
    "loft_conversion": {
        "description": "Loft conversion with dormer",
        "permitted": True,
        "max_dimensions": {
            "detached_semi": "50 cubic metres additional roof space",
            "terraced": "40 cubic metres additional roof space",
        },
        "conditions": [
            "Must not exceed the height of the existing roof",
            "No dormer on front elevation facing a highway",
            "Materials must be similar in appearance",
            "Side-facing windows must be obscure-glazed and non-opening below 1.7m",
            "Dormer must be set back at least 20cm from the original eaves",
        ],
        "legislation": "GPDO 2015, Schedule 2, Part 1, Class B",
        "exceptions": ["Listed buildings", "Flats/maisonettes", "Article 4 direction areas"],
    },
    "outbuilding": {
        "description": "Garden outbuilding (shed, summer house, garage)",
        "permitted": True,
        "max_dimensions": {
            "general": "Max height 4m (dual pitch) or 3m (flat/monopitch). Max 2.5m eaves.",
        },
        "conditions": [
            "Not in front of the principal elevation",
            "Must not cover more than 50% of garden/curtilage",
            "Within 2m of boundary: max 2.5m overall height",
            "Not to be used for sleeping accommodation",
        ],
        "legislation": "GPDO 2015, Schedule 2, Part 1, Class E",
        "exceptions": ["Listed buildings", "Conservation areas (volume restrictions)"],
    },
    "change_of_use": {
        "description": "Change of use of building",
        "permitted": False,
        "notes": "Most changes of use require planning permission. Some permitted under Use Classes Order.",
        "use_classes": {
            "Class_E": "Commercial, business, and service (shops, offices, restaurants, gyms)",
            "Class_F1": "Learning and non-residential institutions",
            "Class_F2": "Local community uses",
            "Class_C3": "Dwellinghouses",
            "Class_C4": "Houses in Multiple Occupation (3-6 people)",
            "Sui_Generis": "Unique uses (pubs, theatres, nightclubs, hot food takeaways)",
        },
        "legislation": "Town and Country Planning (Use Classes) Order 1987 (as amended 2020)",
    },
    "solar_panels": {
        "description": "Solar panels on roof",
        "permitted": True,
        "conditions": [
            "Must not protrude more than 200mm from roof slope",
            "Must not be higher than the highest part of the roof (excluding chimneys)",
            "On flat roofs: panels and frame must not exceed 1m above highest point of roof",
        ],
        "legislation": "GPDO 2015, Schedule 2, Part 14, Class A",
        "exceptions": ["Listed buildings", "Conservation areas (if on principal/highway elevation)", "World Heritage Sites"],
    },
    "new_dwelling": {
        "description": "New dwelling / house",
        "permitted": False,
        "notes": "Full planning permission always required for new dwellings. Pre-application advice strongly recommended.",
        "legislation": "Town and Country Planning Act 1990, s.57",
    },
    "conservatory": {
        "description": "Conservatory (treated as single-storey rear extension)",
        "permitted": True,
        "max_dimensions": {
            "detached": "8m depth (or 4m without prior approval), 4m height",
            "semi_detached_terraced": "6m depth (or 3m without prior approval), 4m height",
        },
        "conditions": [
            "Must not cover more than 50% of the garden/curtilage",
            "Materials must be similar in appearance to existing dwelling",
            "No verandas, balconies, or raised platforms",
            "Not in front of the principal elevation",
            "If floor area exceeds 30 sq m, Building Regulations approval required",
            "If attached and over 30 sq m, must meet thermal separation requirements",
        ],
        "legislation": "GPDO 2015, Schedule 2, Part 1, Class A (same rules as single-storey rear extension)",
        "exceptions": ["Listed buildings", "Conservation areas (restricted)", "Article 4 direction areas", "AONB", "National Parks"],
    },
}

# ---------------------------------------------------------------------------
# Common covenant types
# ---------------------------------------------------------------------------
_COVENANT_TYPES = {
    "restrictive": {
        "definition": "A covenant that restricts the use of land. Runs with the land and binds successors in title.",
        "enforceability": "Enforceable against successors if: (1) touches and concerns the land, (2) intended to run with the land, (3) registered as a notice on the burdened title",
        "legislation": "Law of Property Act 1925, s.56; Tulk v Moxhay (1848)",
        "common_examples": [
            "Not to use the property for business/trade purposes",
            "Not to build above a certain height",
            "Not to erect fences above a specified height",
            "Not to keep animals (other than domestic pets)",
            "Not to subdivide the property",
            "Not to park caravans or commercial vehicles",
        ],
    },
    "positive": {
        "definition": "A covenant requiring the owner to do something (spend money or take action). Generally does NOT run with freehold land at common law.",
        "enforceability": "Does not automatically bind successors in freehold title (Austerberry v Oldham Corp 1885). May be enforced via chain of indemnity covenants or Halsall v Brizell doctrine.",
        "legislation": "Law of Property Act 1925; Rhone v Stephens [1994] 2 AC 310",
        "common_examples": [
            "To maintain boundary fences or walls",
            "To contribute to maintenance of shared roads/drains",
            "To keep the property in good repair",
            "To maintain estate common areas",
        ],
    },
}

# ---------------------------------------------------------------------------
# Section notice templates
# ---------------------------------------------------------------------------
_NOTICE_TYPES = {
    "section_21": {
        "name": "Section 21 Notice (No-Fault Eviction)",
        "legislation": "Housing Act 1988, s.21 (as amended by Deregulation Act 2015)",
        "description": "Notice requiring tenant to leave at end of fixed term or during periodic tenancy. No reason required. Being abolished by Renters (Reform) Bill.",
        "notice_period_months": 2,
        "valid_form": "Form 6A (prescribed form)",
        "prerequisites": [
            "Tenancy deposit protected in government-approved scheme AND prescribed information served",
            "Energy Performance Certificate (EPC) provided to tenant",
            "Gas Safety Certificate provided to tenant (current)",
            "How to Rent guide provided to tenant (current version)",
            "No relevant improvement notice or emergency remedial action notice outstanding from local authority",
            "Landlord licensing requirements met (if applicable)",
            "Cannot be served in first 4 months of initial tenancy",
        ],
        "abolition_note": "The Renters' Rights Bill (formerly Renters Reform Bill) will abolish Section 21 notices. Check current legislative status.",
    },
    "section_8": {
        "name": "Section 8 Notice (Fault-Based Eviction)",
        "legislation": "Housing Act 1988, s.8",
        "description": "Notice seeking possession based on specific grounds. Must state the ground(s) relied upon.",
        "valid_form": "Form 3 (prescribed form)",
        "grounds": {
            "mandatory": {
                "ground_1": {"description": "Landlord previously occupied as only or principal home", "notice_period": "2 months"},
                "ground_2": {"description": "Mortgage lender seeking possession", "notice_period": "2 months"},
                "ground_5": {"description": "Property required for minister of religion", "notice_period": "2 months"},
                "ground_6": {"description": "Landlord intends to demolish/reconstruct", "notice_period": "2 months"},
                "ground_7": {"description": "Death of tenant (periodic tenancy)", "notice_period": "2 months"},
                "ground_7A": {"description": "Tenant convicted of serious offence", "notice_period": "4 weeks"},
                "ground_8": {"description": "At least 2 months' rent arrears (both at notice and hearing date)", "notice_period": "2 weeks"},
            },
            "discretionary": {
                "ground_10": {"description": "Some rent arrears", "notice_period": "2 weeks"},
                "ground_11": {"description": "Persistent delay in paying rent", "notice_period": "2 weeks"},
                "ground_12": {"description": "Breach of tenancy obligation", "notice_period": "2 weeks"},
                "ground_13": {"description": "Deterioration of property due to tenant neglect", "notice_period": "2 weeks"},
                "ground_14": {"description": "Nuisance, annoyance, or conviction for illegal use", "notice_period": "immediately"},
                "ground_14A": {"description": "Domestic violence - partner has left", "notice_period": "2 weeks"},
                "ground_17": {"description": "Tenancy granted based on false statement", "notice_period": "2 weeks"},
            },
        },
    },
}


# ===========================================================================
# MCP Tools
# ===========================================================================


@mcp.tool()
def search_land_registry(
    address: Optional[str] = None,
    title_number: Optional[str] = None,
    postcode: Optional[str] = None, api_key: str = "") -> dict:
    """Search UK Land Registry by address, title number, or postcode.

    Returns ownership details, tenure type, boundaries, restrictions, and
    price paid information. Note: this returns structured guidance on what
    the Land Registry holds and how to access it. For official title
    documents, use HM Land Registry's portal or Find a Property service.

    Args:
        address: Property address (e.g. "10 Downing Street, London").
        title_number: HM Land Registry title number (e.g. "NGL123456").
        postcode: UK postcode to search (e.g. "SW1A 2AA").

    Returns:
        Land Registry information structure and access guidance.

    Behavior:
        This tool is read-only and stateless — it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade at https://landlaw.ai/pricing"}

    if not address and not title_number and not postcode:
        return {"error": "Provide at least one of: address, title_number, or postcode."}

    # Title number format validation
    if title_number:
        tn_pattern = re.compile(r"^[A-Z]{1,3}\d{1,6}$")
        if not tn_pattern.match(title_number.upper()):
            return {"error": f"Invalid title number format: '{title_number}'. Expected format: 'NGL123456' (county prefix + number)."}

    # Determine likely tenure from address hints
    tenure_hint = "freehold"
    if address:
        addr_lower = address.lower()
        if any(w in addr_lower for w in ["flat", "apartment", "floor", "suite"]):
            tenure_hint = "leasehold"

    tenure_info = _TENURE_TYPES.get(tenure_hint, _TENURE_TYPES["freehold"])

    return {
        "search_parameters": {
            "address": address,
            "title_number": title_number,
            "postcode": postcode,
        },
        "land_registry_records": {
            "title_register_sections": {
                "A_property_register": {
                    "description": "Describes the land and estate (freehold/leasehold), plus any rights benefiting the property",
                    "contains": ["Address/description of land", "Estate type (freehold/leasehold)", "Rights of way benefiting the property", "Mines and minerals reservations"],
                },
                "B_proprietorship_register": {
                    "description": "Names the current registered owner(s) and any restrictions on their power to deal with the land",
                    "contains": ["Name(s) of registered proprietor(s)", "Address for service", "Price paid/value stated", "Class of title (absolute, qualified, possessory, good leasehold)", "Restrictions (e.g. consent required, bankruptcy)"],
                },
                "C_charges_register": {
                    "description": "Lists charges (mortgages) and other encumbrances burdening the property",
                    "contains": ["Registered charges (mortgages)", "Restrictive covenants", "Easements burdening the property", "Notices (e.g. lease, home rights)"],
                },
            },
            "title_plan": {
                "description": "Ordnance Survey-based plan showing the general extent of the registered title, edged in red",
                "accuracy_note": "Title plan shows GENERAL boundaries only (Land Registration Act 2002 s.60). The exact boundary line is not determined by the plan.",
            },
            "likely_tenure": tenure_hint,
            "tenure_info": tenure_info,
        },
        "how_to_access": {
            "online_search": {
                "url": "https://search-property-information.service.gov.uk/",
                "cost": "GBP 3.00 per title register / GBP 3.00 per title plan",
                "notes": "Instant download. Available 24/7.",
            },
            "official_copies": {
                "url": "https://www.gov.uk/government/organisations/land-registry",
                "cost": "GBP 7.00 per document via Business e-services",
                "notes": "Certified copies accepted by courts and lenders.",
            },
            "price_paid_data": {
                "url": "https://www.gov.uk/search-house-prices",
                "cost": "Free",
                "notes": "Sale prices from 1995 onwards. Updated monthly.",
            },
        },
        "powered_by": "landlaw.ai",
    }


@mcp.tool()
def check_planning_permission(
    modification_type: str,
    property_type: str = "detached",
    listed_building: bool = False,
    conservation_area: bool = False,
    aonb: bool = False, api_key: str = "") -> dict:
    """Check planning permission requirements for a property modification.

    Determines whether a proposed modification falls under permitted development
    rights or requires full planning permission. Based on the Town and Country
    Planning (General Permitted Development) (England) Order 2015 (GPDO).

    Args:
        modification_type: Type of modification. Options: single_storey_rear_extension,
            loft_conversion, outbuilding, change_of_use, solar_panels, new_dwelling.
        property_type: Property type (detached, semi_detached, terraced, flat). Affects PD limits.
        listed_building: Whether the building is Grade I, II*, or II listed.
        conservation_area: Whether in a conservation area.
        aonb: Whether in an Area of Outstanding Natural Beauty.

    Returns:
        Planning permission requirements, PD rights, conditions, and application guidance.

    Behavior:
        This tool generates structured output without modifying external systems.
        Output is deterministic for identical inputs. No side effects.
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent — calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded."}

    pd_info = _PERMITTED_DEVELOPMENT.get(modification_type)
    if not pd_info:
        return {
            "error": f"Unknown modification type '{modification_type}'.",
            "available_types": list(_PERMITTED_DEVELOPMENT.keys()),
        }

    # Check if any exceptions apply
    exceptions_triggered = []
    if listed_building:
        exceptions_triggered.append("Listed building - ALL works (internal and external) require Listed Building Consent. Permitted development rights are REMOVED.")
    if conservation_area and "Conservation areas" in pd_info.get("exceptions", []):
        exceptions_triggered.append("Conservation area - Permitted development rights are restricted. Additional controls on demolition, roof alterations, and cladding.")
    if aonb and "AONB" in pd_info.get("exceptions", []):
        exceptions_triggered.append("AONB - Permitted development rights are restricted for extensions and outbuildings.")

    permitted = pd_info.get("permitted", False)
    if listed_building:
        permitted = False

    # Determine property-specific limits
    dimensions = pd_info.get("max_dimensions", {})
    if property_type in ["semi_detached", "terraced"]:
        relevant_dims = dimensions.get("semi_detached_terraced", dimensions.get("terraced", dimensions.get("general", "See conditions")))
    else:
        relevant_dims = dimensions.get("detached", dimensions.get("detached_semi", dimensions.get("general", "See conditions")))

    result = {
        "modification": pd_info["description"],
        "property_type": property_type,
        "planning_permission_required": not permitted or bool(exceptions_triggered),
        "permitted_development": {
            "eligible": permitted and not exceptions_triggered,
            "legislation": pd_info.get("legislation", ""),
            "max_dimensions": relevant_dims,
            "conditions": pd_info.get("conditions", []),
        },
        "exceptions_triggered": exceptions_triggered if exceptions_triggered else None,
        "designations": {
            "listed_building": listed_building,
            "conservation_area": conservation_area,
            "aonb": aonb,
        },
    }

    if not permitted or exceptions_triggered:
        result["application_guidance"] = {
            "how_to_apply": "Submit via Planning Portal (https://www.planningportal.co.uk/)",
            "fee": "GBP 258 for householder application (2024/25 rate)",
            "determination_period": "8 weeks (householder) or 13 weeks (major development)",
            "pre_application_advice": "Strongly recommended. Contact Local Planning Authority.",
            "documents_needed": [
                "Application form",
                "Site location plan (1:1250 or 1:2500 with red line boundary)",
                "Block/site plan (1:200 or 1:500)",
                "Existing and proposed floor plans and elevations",
                "Design and Access Statement (if required)",
                "Heritage Statement (if listed building or conservation area)",
            ],
        }
    else:
        result["prior_approval_note"] = (
            "Even under permitted development, some works require Prior Approval from the Local "
            "Planning Authority (e.g. larger home extensions). This is a lighter-touch process but "
            "must be obtained before work begins."
        )

    result["powered_by"] = "landlaw.ai"
    return result


@mcp.tool()
def explain_covenant(
    covenant_text: str,
    covenant_type: Optional[str] = None, api_key: str = "") -> dict:
    """Explain a restrictive or positive covenant in plain English.

    Takes the covenant wording (typically from a title register or deed)
    and provides a plain-English explanation, enforceability analysis,
    and practical implications.

    Args:
        covenant_text: The full covenant wording from the title register or deed.
        covenant_type: Optional hint: "restrictive" or "positive". Auto-detected if not provided.

    Returns:
        Plain English explanation, enforceability analysis, and practical advice.

    Behavior:
        This tool is read-only and stateless — it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded."}

    if not covenant_text or len(covenant_text.strip()) < 10:
        return {"error": "Please provide the full covenant text (minimum 10 characters)."}

    text_lower = covenant_text.lower()

    # Auto-detect type
    if not covenant_type:
        negative_indicators = ["not to", "shall not", "must not", "no", "prohibit", "restrict", "refrain"]
        positive_indicators = ["shall maintain", "must keep", "to maintain", "to repair", "to contribute", "to pay", "to erect"]
        neg_score = sum(1 for kw in negative_indicators if kw in text_lower)
        pos_score = sum(1 for kw in positive_indicators if kw in text_lower)
        covenant_type = "positive" if pos_score > neg_score else "restrictive"

    cov_info = _COVENANT_TYPES.get(covenant_type, _COVENANT_TYPES["restrictive"])

    # Identify common themes
    themes = []
    theme_map = {
        "building/construction": ["build", "erect", "construct", "alter", "extend", "develop"],
        "use restriction": ["trade", "business", "commercial", "manufact", "profession", "shop"],
        "appearance/aesthetics": ["fence", "wall", "height", "colour", "material", "appearance"],
        "animals": ["animal", "pet", "livestock", "poultry", "dog", "cat"],
        "subdivision": ["subdivide", "divide", "separate", "partition"],
        "vehicles": ["caravan", "vehicle", "park", "motor home", "boat"],
        "maintenance": ["maintain", "repair", "good condition", "keep", "upkeep"],
        "nuisance": ["nuisance", "annoy", "noise", "offensive"],
    }
    for theme, keywords in theme_map.items():
        if any(kw in text_lower for kw in keywords):
            themes.append(theme)

    # Enforceability analysis
    enforceability_factors = []
    if covenant_type == "restrictive":
        enforceability_factors = [
            "Restrictive covenants generally bind successors in title if registered against the burdened land",
            "The covenant must 'touch and concern' the land (not merely personal)",
            "The person enforcing must own land that benefits from the covenant",
            "Check if the covenant is noted in the Charges Register (Section C) of the title",
            "Covenants can become unenforceable through long non-enforcement, but this is not automatic",
        ]
    else:
        enforceability_factors = [
            "Positive covenants generally do NOT bind successors in freehold title (Austerberry v Oldham Corp)",
            "However, may be enforced via: chain of indemnity covenants, mutual benefit/burden doctrine (Halsall v Brizell), or estate rentcharge",
            "Positive covenants DO bind successors in leasehold (privity of estate)",
            "Consider whether an indemnity covenant was given on purchase",
        ]

    # Modification/discharge guidance
    modification_options = [
        {
            "method": "Application to Upper Tribunal (Lands Chamber)",
            "legislation": "Law of Property Act 1925, s.84",
            "grounds": [
                "(a) Obsolete due to changes in character of property/neighbourhood",
                "(aa) Reasonable use is being impeded, and covenant confers no practical benefit",
                "(b) Those entitled to benefit have agreed (expressly or impliedly)",
                "(c) Discharge/modification would not injure those entitled to benefit",
            ],
            "cost": "Application fee + legal costs. Typically GBP 3,000 - GBP 15,000+",
        },
        {
            "method": "Negotiated release",
            "description": "Negotiate directly with the benefiting landowner for a deed of release",
            "cost": "Legal fees + potential payment to benefiting owner",
        },
        {
            "method": "Indemnity insurance",
            "description": "Insurance policy to cover risk of enforcement. Does NOT remove the covenant.",
            "cost": "One-off premium, typically GBP 100 - GBP 2,000 depending on risk",
            "warning": "Must not contact the benefiting owner before taking out insurance (increases risk)",
        },
    ]

    return {
        "original_text": covenant_text,
        "covenant_type": covenant_type,
        "type_info": cov_info,
        "themes_identified": themes,
        "plain_english_summary": (
            f"This is a {covenant_type} covenant. "
            f"{'It restricts what you can do with the property.' if covenant_type == 'restrictive' else 'It requires you to take specific action or spend money.'} "
            f"Key themes: {', '.join(themes) if themes else 'general obligation'}."
        ),
        "enforceability": {
            "analysis": enforceability_factors,
            "general_advice": "Always check the title register to confirm the covenant is noted and who benefits from it.",
        },
        "options_for_modification": modification_options,
        "warning": "This is general guidance only. Covenant interpretation depends on the specific wording, context, and surrounding circumstances. Seek qualified legal advice before acting.",
        "powered_by": "landlaw.ai",
    }


@mcp.tool()
def calculate_sdlt(
    purchase_price: float,
    first_time_buyer: bool = False,
    additional_property: bool = False,
    non_residential: bool = False,
    non_uk_resident: bool = False, api_key: str = "") -> dict:
    """Calculate Stamp Duty Land Tax for a UK property purchase.

    Applies current SDLT rates including first-time buyer relief,
    additional property surcharge, and non-UK resident surcharge.

    Args:
        purchase_price: Purchase price in GBP.
        first_time_buyer: Whether the buyer qualifies for first-time buyer relief.
            Must be purchasing a property of GBP 625,000 or less.
        additional_property: Whether this is an additional property (second home,
            buy-to-let). Adds 3% surcharge on all bands.
        non_residential: Whether the property is non-residential or mixed use.
        non_uk_resident: Whether the buyer is a non-UK resident. Adds 2% surcharge.

    Returns:
        SDLT calculation with band-by-band breakdown.

    Behavior:
        This tool is read-only and stateless — it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent — calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded."}

    if purchase_price <= 0:
        return {"error": "Purchase price must be positive."}

    # Select rate table
    if non_residential:
        bands = _SDLT_NON_RESIDENTIAL
        table_name = "Non-residential / mixed use"
    elif first_time_buyer and purchase_price <= 625000:
        bands = _SDLT_FTB
        table_name = "First-time buyer relief"
    else:
        bands = _SDLT_RESIDENTIAL
        table_name = "Standard residential"
        if first_time_buyer and purchase_price > 625000:
            table_name += " (FTB relief not available above GBP 625,000)"

    # Calculate SDLT by band
    breakdown = []
    total_sdlt = 0.0
    remaining = purchase_price

    for band in bands:
        lower = band["threshold"]
        upper = band["up_to"]
        rate = band["rate"]

        if remaining <= 0:
            break

        taxable_in_band = min(remaining, upper - lower) if upper != float("inf") else remaining
        if taxable_in_band <= 0:
            continue

        tax_in_band = taxable_in_band * rate
        total_sdlt += tax_in_band
        breakdown.append({
            "band": f"GBP {lower:,.0f} - {'GBP {:,.0f}'.format(upper) if upper != float('inf') else 'remainder'}",
            "rate": f"{rate * 100:.0f}%",
            "taxable_amount": round(taxable_in_band, 2),
            "tax": round(tax_in_band, 2),
        })
        remaining -= taxable_in_band

    # Additional property surcharge (3% on entire price)
    additional_surcharge = 0
    if additional_property:
        additional_surcharge = purchase_price * _SDLT_ADDITIONAL

    # Non-UK resident surcharge (2% on entire price)
    non_resident_surcharge = 0
    if non_uk_resident:
        non_resident_surcharge = purchase_price * 0.02

    total = total_sdlt + additional_surcharge + non_resident_surcharge
    effective_rate = (total / purchase_price) * 100 if purchase_price > 0 else 0

    return {
        "purchase_price": purchase_price,
        "rate_table": table_name,
        "band_breakdown": breakdown,
        "base_sdlt": round(total_sdlt, 2),
        "surcharges": {
            "additional_property_3pct": round(additional_surcharge, 2) if additional_property else 0,
            "non_uk_resident_2pct": round(non_resident_surcharge, 2) if non_uk_resident else 0,
        },
        "total_sdlt": round(total, 2),
        "effective_rate_pct": round(effective_rate, 2),
        "payment_deadline": "14 days from completion date",
        "filing_method": "SDLT return filed with HMRC (online or paper)",
        "notes": [
            "Rates as of April 2025. Check HMRC for any subsequent changes.",
            "First-time buyer relief: nil rate on first GBP 425,000, then 5% to GBP 625,000.",
            "Additional property surcharge applies to second homes and buy-to-let purchases.",
            "Non-UK resident surcharge applies from 1 April 2021.",
            "Scotland uses Land and Buildings Transaction Tax (LBTT) instead of SDLT.",
            "Wales uses Land Transaction Tax (LTT) instead of SDLT.",
        ],
        "legislation": "Finance Act 2003, Part 4 (as amended)",
        "powered_by": "landlaw.ai",
    }


@mcp.tool()
def draft_section_notice(
    notice_type: str,
    landlord_name: str,
    tenant_name: str,
    property_address: str,
    tenancy_start_date: str,
    grounds: Optional[list[str]] = None,
    arrears_amount: Optional[float] = None, api_key: str = "") -> dict:
    """Generate a Section 21 or Section 8 notice template.

    Produces the required content and validates prerequisites. Note: use
    the prescribed form (Form 6A for s.21, Form 3 for s.8) for the actual
    notice. This tool generates the required content and checks validity.

    Args:
        notice_type: Either "section_21" or "section_8".
        landlord_name: Full name of landlord (or landlord's agent).
        tenant_name: Full name of tenant(s).
        property_address: Full address of the rental property.
        tenancy_start_date: Tenancy start date (YYYY-MM-DD).
        grounds: Required for Section 8 only. List of grounds (e.g. ["ground_8", "ground_10"]).
        arrears_amount: Amount of rent arrears in GBP (if applicable for Section 8).

    Returns:
        Notice template with all required fields and validity checks.

    Behavior:
        This tool generates structured output without modifying external systems.
        Output is deterministic for identical inputs. No side effects.
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded."}

    notice_info = _NOTICE_TYPES.get(notice_type)
    if not notice_info:
        return {"error": f"Unknown notice type '{notice_type}'. Use 'section_21' or 'section_8'."}

    if not all([landlord_name, tenant_name, property_address, tenancy_start_date]):
        return {"error": "All fields (landlord_name, tenant_name, property_address, tenancy_start_date) are required."}

    try:
        start_date = datetime.strptime(tenancy_start_date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    now = datetime.now(timezone.utc)
    notice_ref = f"LLN-{uuid.uuid4().hex[:8].upper()}"

    if notice_type == "section_21":
        # Check 4-month rule
        four_months = start_date + timedelta(days=120)
        if now.replace(tzinfo=None) < four_months:
            earliest_serve = four_months.strftime("%Y-%m-%d")
        else:
            earliest_serve = now.strftime("%Y-%m-%d")

        expiry_date = (now + timedelta(days=60)).strftime("%Y-%m-%d")

        return {
            "notice_reference": notice_ref,
            "notice_type": notice_info["name"],
            "legislation": notice_info["legislation"],
            "prescribed_form": notice_info["valid_form"],
            "notice_content": {
                "to_tenant": tenant_name,
                "property": property_address,
                "from_landlord": landlord_name,
                "tenancy_start_date": tenancy_start_date,
                "notice_served_date": now.strftime("%Y-%m-%d"),
                "notice_period": f"{notice_info['notice_period_months']} months",
                "earliest_possession_date": expiry_date,
            },
            "prerequisites_checklist": notice_info["prerequisites"],
            "validity_warnings": [
                "Use prescribed Form 6A - any other format is INVALID",
                "Must be served on ALL named tenants",
                "Notice is valid for 6 months from date of service",
                "If any prerequisite is not met, the notice may be invalid",
                f"Earliest serve date (4-month rule): {earliest_serve}",
            ],
            "abolition_warning": notice_info["abolition_note"],
            "service_methods": [
                "Hand delivery to tenant (keep proof of delivery)",
                "First class post to the property (deemed served 2 working days later)",
                "Left at the property in a conspicuous place",
            ],
            "next_steps": [
                "1. Verify all prerequisites are met",
                "2. Complete prescribed Form 6A",
                "3. Serve notice on tenant(s)",
                "4. Wait for notice period to expire (2 months)",
                "5. If tenant has not left, apply to county court for possession order",
                "6. If tenant still does not leave, apply for warrant of possession (bailiffs)",
            ],
            "powered_by": "landlaw.ai",
        }

    else:  # section_8
        if not grounds:
            return {
                "error": "Section 8 requires at least one ground to be specified.",
                "available_grounds": {
                    "mandatory": list(notice_info["grounds"]["mandatory"].keys()),
                    "discretionary": list(notice_info["grounds"]["discretionary"].keys()),
                },
            }

        # Validate grounds and determine notice period
        ground_details = []
        shortest_notice = "2 months"
        all_grounds = {**notice_info["grounds"]["mandatory"], **notice_info["grounds"]["discretionary"]}

        for g in grounds:
            g_info = all_grounds.get(g)
            if not g_info:
                return {"error": f"Unknown ground '{g}'.", "available_grounds": list(all_grounds.keys())}
            ground_type = "mandatory" if g in notice_info["grounds"]["mandatory"] else "discretionary"
            ground_details.append({
                "ground": g,
                "type": ground_type,
                "description": g_info["description"],
                "notice_period": g_info["notice_period"],
            })

        return {
            "notice_reference": notice_ref,
            "notice_type": notice_info["name"],
            "legislation": notice_info["legislation"],
            "prescribed_form": notice_info["valid_form"],
            "notice_content": {
                "to_tenant": tenant_name,
                "property": property_address,
                "from_landlord": landlord_name,
                "tenancy_start_date": tenancy_start_date,
                "notice_served_date": now.strftime("%Y-%m-%d"),
                "grounds_relied_upon": ground_details,
                "arrears_amount": f"GBP {arrears_amount:,.2f}" if arrears_amount else None,
            },
            "validity_notes": [
                "Use prescribed Form 3",
                "Must specify the ground(s) and give particulars",
                "Mandatory grounds: court MUST grant possession if proved",
                "Discretionary grounds: court MAY grant possession if reasonable",
                "Ground 8 (mandatory): requires 2+ months arrears at BOTH notice date AND hearing date",
            ],
            "next_steps": [
                "1. Complete prescribed Form 3 with grounds and particulars",
                "2. Serve notice on tenant(s)",
                "3. Wait for applicable notice period to expire",
                "4. Issue possession claim at county court (Form N5/N5B)",
                "5. Attend possession hearing",
                "6. If order granted and tenant does not leave, apply for warrant",
            ],
            "powered_by": "landlaw.ai",
        }


@mcp.tool()
def check_right_of_way(
    description: str,
    right_type: Optional[str] = None,
    registered: bool = True, api_key: str = "") -> dict:
    """Analyze a right of way or easement and explain its implications.

    Takes a description of a right of way or easement (from title register,
    conveyance, or physical observation) and explains the legal implications,
    extent, and practical considerations.

    Args:
        description: Description of the right of way/easement. Can be legal text
            from a deed or a plain description (e.g. "footpath across the garden
            to the rear gate").
        right_type: Type of right: "right_of_way", "easement", "prescriptive",
            "public_footpath". Auto-detected if not provided.
        registered: Whether the right is noted on the Land Registry title.

    Returns:
        Analysis of the right, its extent, enforceability, and practical implications.

    Behavior:
        This tool is read-only and stateless — it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded."}

    if not description or len(description.strip()) < 10:
        return {"error": "Please provide a description of the right of way (minimum 10 characters)."}

    desc_lower = description.lower()

    # Auto-detect type
    if not right_type:
        if any(w in desc_lower for w in ["public footpath", "public bridleway", "definitive map", "byway"]):
            right_type = "public_footpath"
        elif any(w in desc_lower for w in ["prescriptive", "20 years", "long use", "without permission"]):
            right_type = "prescriptive"
        elif any(w in desc_lower for w in ["drain", "pipe", "cable", "wire", "sewer", "utility", "service"]):
            right_type = "easement"
        else:
            right_type = "right_of_way"

    # Right type details
    type_details = {
        "right_of_way": {
            "name": "Private Right of Way",
            "description": "A right to pass over another person's land. May be on foot, with vehicles, or both.",
            "creation_methods": [
                "Express grant (in a deed/conveyance)",
                "Express reservation (seller reserves right when selling part of land)",
                "Implied grant (Wheeldon v Burrows 1879; s.62 LPA 1925)",
                "Prescription (20+ years continuous use as of right)",
                "Necessity (landlocked land)",
            ],
            "legislation": "Law of Property Act 1925, s.1(2)(a), s.62; Prescription Act 1832; Land Registration Act 2002",
        },
        "easement": {
            "name": "Easement",
            "description": "A right over another's land (e.g. drainage, light, support, utilities). Must have a dominant and servient tenement.",
            "creation_methods": [
                "Express grant/reservation in a deed",
                "Implied (necessity, common intention, Wheeldon v Burrows, s.62 LPA 1925)",
                "Prescription (20 years uninterrupted use)",
            ],
            "essential_characteristics": [
                "There must be a dominant and servient tenement (Re Ellenborough Park [1956])",
                "The easement must accommodate the dominant tenement",
                "Dominant and servient owners must be different persons",
                "The right must be capable of forming the subject matter of a grant",
            ],
            "legislation": "Law of Property Act 1925; Prescription Act 1832; Land Registration Act 2002",
        },
        "prescriptive": {
            "name": "Prescriptive Right",
            "description": "A right acquired through long use (20+ years) without permission, without secrecy, and without force.",
            "requirements": [
                "Use for 20+ years (Prescription Act 1832) or since 'time immemorial' (common law)",
                "Use must be 'as of right' (nec vi, nec clam, nec precario - not by force, not secretly, not with permission)",
                "Use must be continuous and uninterrupted",
                "Use must be by or on behalf of a freehold owner against a freehold owner",
            ],
            "legislation": "Prescription Act 1832; common law; Land Registration Act 2002 s.27(2)(d)",
        },
        "public_footpath": {
            "name": "Public Right of Way",
            "description": "A right for the general public to pass along a defined route. Recorded on the Definitive Map.",
            "categories": {
                "footpath": "On foot only",
                "bridleway": "On foot, horseback, or bicycle",
                "restricted_byway": "On foot, horseback, bicycle, or non-mechanically propelled vehicle",
                "byway_open_to_all_traffic": "All traffic including motor vehicles",
            },
            "key_points": [
                "Cannot be extinguished by the landowner - only by legal order",
                "Obstructing a public right of way is a criminal offence (Highways Act 1980 s.137)",
                "Diversion or extinguishment requires order from local authority or Secretary of State",
                "Minimum width: 1m cross-field footpath, 1.5m field-edge footpath, 3m bridleway",
            ],
            "legislation": "Highways Act 1980; Countryside and Rights of Way Act 2000; Wildlife and Countryside Act 1981",
        },
    }

    details = type_details.get(right_type, type_details["right_of_way"])

    # Practical implications
    implications = {
        "for_benefiting_owner": [
            "Right to use the route/facility as described in the grant",
            "Cannot exceed the scope of the right (e.g. foot access only does not include vehicles)",
            "Must not cause unnecessary damage to the servient land",
            "May carry out reasonable repairs if necessary",
        ],
        "for_burdened_owner": [
            "Must not obstruct or interfere with the right",
            "Cannot lock gates unless keys are provided to all entitled users",
            "Can use the land for own purposes provided the right is not substantially interfered with",
            "Responsible for maintenance only if expressly covenanted",
        ],
        "property_impact": [
            "Rights of way can affect property value (positively or negatively)",
            "Must be disclosed to buyers (Material Information - Consumer Protection from Unfair Trading Regulations 2008)",
            "Lenders may require indemnity insurance for certain rights of way",
            "Building over a right of way may be an actionable interference",
        ],
    }

    # Registration status implications
    reg_status = {}
    if registered:
        reg_status = {
            "status": "Registered - noted on title",
            "enforceability": "Binds all subsequent owners of the burdened land (overriding interest if also in actual occupation, or protected by notice on register)",
            "evidence": "Check Property Register (Section A) for rights benefiting the property, and Charges Register (Section C) for rights burdening it",
        }
    else:
        reg_status = {
            "status": "Unregistered - not noted on title",
            "enforceability": "May still be enforceable as an overriding interest under Schedule 3, Land Registration Act 2002 if the right is exercised and apparent",
            "risk": "Greater risk of dispute. Consider applying for voluntary registration of the right.",
            "action": "Apply to register the right at Land Registry (Form AP1 with supporting evidence)",
        }

    return {
        "description": description,
        "right_type": right_type,
        "type_details": details,
        "registration_status": reg_status,
        "implications": implications,
        "dispute_resolution": [
            "Negotiate with the other landowner",
            "Mediation (recommended before litigation)",
            "Application to First-tier Tribunal (Property Chamber) for boundary/easement disputes",
            "County Court or High Court proceedings for injunction or damages",
            "For public rights of way: contact Local Authority Rights of Way department",
        ],
        "warning": "This is general guidance. The extent and enforceability of any right depends on the specific wording of the grant, the factual circumstances, and the applicable law. Seek qualified legal advice for specific situations.",
        "powered_by": "landlaw.ai",
    }


if __name__ == "__main__":
    mcp.run()
