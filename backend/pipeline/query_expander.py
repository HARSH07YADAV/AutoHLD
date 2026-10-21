"""
query_expander.py — Natural language query understanding and expansion for AutoHLD.

Responsibilities:
  1. Detect user query intent (overview/summary, component inspection, ports/interfaces,
     functional safety, thermal/power flow, inconsistency audit, general technical).
  2. Expand automotive and AUTOSAR acronyms, synonyms, and related engineering terms.
  3. Extract core technical entities (SWC names, port identifiers, standards).
  4. Generate expanded search queries for hybrid retrieval and fallback retries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(str, Enum):
    DOCUMENT_OVERVIEW = "document_overview"
    COMPONENT_INSPECTION = "component_inspection"
    PORTS_INTERFACES = "ports_interfaces"
    SAFETY_ASIL = "safety_asil"
    THERMAL_POWER = "thermal_power"
    INCONSISTENCY = "inconsistency"
    GENERAL_TECHNICAL = "general_technical"


# ── AUTOSAR Acronym & Domain Synonym Dictionary ──────────────────────────────
AUTOSAR_SYNONYMS: dict[str, list[str]] = {
    "bms": [
        "battery management system",
        "high voltage battery pack",
        "bms controller",
    ],
    "swc": [
        "software component",
        "atomic swc",
        "application component",
    ],
    "bsw": [
        "basic software",
        "mcal",
        "ecu abstraction",
        "service layer",
    ],
    "rte": [
        "runtime environment",
        "virtual function bus",
        "vfb",
    ],
    "mcal": [
        "microcontroller abstraction layer",
        "driver",
    ],
    "asil": [
        "automotive safety integrity level",
        "iso 26262",
        "functional safety",
    ],
    "hara": [
        "hazard analysis and risk assessment",
        "safety goal",
    ],
    "soc": [
        "state of charge",
        "battery percentage",
    ],
    "soh": [
        "state of health",
        "battery degradation",
    ],
    "can": [
        "can fd",
        "controller area network",
        "can bus",
    ],
    "uds": [
        "unified diagnostic services",
        "iso 14229",
        "diagnostics",
    ],
    "wdgm": [
        "watchdog manager",
        "supervision",
    ],
    "dem": [
        "diagnostic event manager",
        "dtc",
    ],
    "dcm": [
        "diagnostic communication manager",
    ],
    "nvm": [
        "non volatile memory",
        "flash eeprom",
    ],
    "ecum": [
        "ecu state manager",
    ],
    "bswm": [
        "bsw mode manager",
    ],
    "pdur": [
        "pdu router",
    ],
    "com": [
        "autosar com",
        "communication",
    ],
}

# ── Intent detection patterns ────────────────────────────────────────────────
_OVERVIEW_PATTERNS = [
    r"\b(info|information|about|overview|summary|summarize|purpose|scope|intro|introduction)\b",
    r"\b(what is this document|what does this document|what is this hld|tell me about the document)\b",
    r"\b(table of contents|executive summary|system context|high level design)\b",
    r"\b(explain the system|system architecture overview)\b",
]

_COMPONENT_PATTERNS = [
    r"\b(swc|software component|components|atomic swc|composition)\b",
    r"\b(what components|list components|which components|describe component)\b",
    r"\b(batterymanagement|thermalmanagement|chargingcontrol|powercontrol|cellsupervisor|cellbalancing)\b",
    r"\b(inverterinterface|vehiclesafetysupervisor|torquecalculator)\b",
]

_PORT_INTERFACE_PATTERNS = [
    r"\b(port|ports|interface|interfaces|p-port|r-port|sender|receiver|client|server)\b",
    r"\b(signal|signals|dataelement|comspec|connections|data type)\b",
]

_SAFETY_PATTERNS = [
    r"\b(safety|asil|iso 26262|hara|hazard|safe state|de-energize|contactor|watchdog|e2e)\b",
    r"\b(functional safety|asil-d|asil-c|asil-b|asil-a|qm)\b",
]

_THERMAL_POWER_PATTERNS = [
    r"\b(thermal|temperature|cooling|coolant|heater|heating|cell temp)\b",
    r"\b(power|voltage|800v|high voltage|current|balancing|precharge|soc|soh|inverter)\b",
]

_INCONSISTENCY_PATTERNS = [
    r"\b(inconsistency|inconsistencies|conflict|conflicts|discrepancy|mismatch|contradiction)\b",
    r"\b(issue|issues|error|review finding|audit)\b",
]


@dataclass
class QueryAnalysis:
    """Structured analysis of a user question."""
    original_query: str
    intent: QueryIntent
    expanded_terms: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    is_overview: bool = False
    is_technical: bool = True
    suggested_search_queries: list[str] = field(default_factory=list)


def analyze_query(question: str) -> QueryAnalysis:
    """
    Analyze a natural language question to determine intent and query expansions.
    """
    q_clean = question.strip()
    q_lower = q_clean.lower()

    # 1. Detect Intent
    intent = QueryIntent.GENERAL_TECHNICAL

    if any(re.search(pat, q_lower) for pat in _INCONSISTENCY_PATTERNS):
        intent = QueryIntent.INCONSISTENCY
    elif any(re.search(pat, q_lower) for pat in _OVERVIEW_PATTERNS) and (
        len(q_clean.split()) <= 8 or "document" in q_lower or "hld" in q_lower or "summary" in q_lower
    ):
        intent = QueryIntent.DOCUMENT_OVERVIEW
    elif any(re.search(pat, q_lower) for pat in _PORT_INTERFACE_PATTERNS):
        intent = QueryIntent.PORTS_INTERFACES
    elif any(re.search(pat, q_lower) for pat in _COMPONENT_PATTERNS):
        intent = QueryIntent.COMPONENT_INSPECTION
    elif any(re.search(pat, q_lower) for pat in _SAFETY_PATTERNS):
        intent = QueryIntent.SAFETY_ASIL
    elif any(re.search(pat, q_lower) for pat in _THERMAL_POWER_PATTERNS):
        intent = QueryIntent.THERMAL_POWER

    is_overview = (intent == QueryIntent.DOCUMENT_OVERVIEW)

    # 2. Extract technical entities (CamelCase names, SWC names, port-like tokens)
    entities: list[str] = []
    # Match CamelCase words like BatteryManagement, InverterInterface, BattV_Prov
    camel_tokens = re.findall(r"\b[A-Z][a-zA-Z0-9]+(?:_[A-Za-z0-9]+)*\b", q_clean)
    for token in camel_tokens:
        if len(token) > 2 and token.lower() not in {"what", "which", "how", "give", "tell", "list", "show", "is", "the", "this"}:
            entities.append(token)

    # 3. Extract keywords and expand acronyms
    tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", q_lower)
    expanded_terms: list[str] = []
    keywords: list[str] = []

    _STOPWORDS = {
        "what", "is", "the", "are", "of", "in", "to", "for", "a", "an", "and",
        "or", "this", "that", "these", "those", "how", "does", "do", "tell",
        "me", "about", "give", "show", "list", "explain", "describe", "can",
        "you", "document", "hld", "pdf",
    }

    for t in tokens:
        if t in AUTOSAR_SYNONYMS:
            expanded_terms.extend(AUTOSAR_SYNONYMS[t])
        if t not in _STOPWORDS and len(t) > 1:
            keywords.append(t)

    # 4. Formulate suggested search queries for multi-stage / fallback retrieval
    suggested_queries: list[str] = [q_clean]

    if is_overview:
        suggested_queries.append("Executive Summary Vehicle E/E Architecture Scope Introduction")
        suggested_queries.append("AUTOSAR Layered Architecture Software Components Overview")
    elif intent == QueryIntent.COMPONENT_INSPECTION:
        suggested_queries.append(f"{' '.join(keywords)} Software Component SWC specification")
        if entities:
            suggested_queries.append(f"{' '.join(entities)} ports interfaces runnable")
    elif intent == QueryIntent.PORTS_INTERFACES:
        suggested_queries.append(f"{' '.join(keywords)} port interface sender receiver client server signal")
    elif intent == QueryIntent.SAFETY_ASIL:
        suggested_queries.append(f"{' '.join(keywords)} ISO 26262 ASIL HARA functional safety hazard")
    elif intent == QueryIntent.THERMAL_POWER:
        suggested_queries.append(f"{' '.join(keywords)} thermal cooling temperature voltage 800V battery")

    if expanded_terms:
        suggested_queries.append(f"{' '.join(keywords)} {' '.join(expanded_terms[:3])}")

    return QueryAnalysis(
        original_query=q_clean,
        intent=intent,
        expanded_terms=list(dict.fromkeys(expanded_terms)),
        keywords=list(dict.fromkeys(keywords)),
        entities=list(dict.fromkeys(entities)),
        is_overview=is_overview,
        suggested_search_queries=list(dict.fromkeys(suggested_queries)),
    )
