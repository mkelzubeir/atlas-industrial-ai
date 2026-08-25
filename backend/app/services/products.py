"""Product search and ambiguity detection.

The hard part of this endpoint is not finding matches -- it is deciding whether
the match is good enough to act on. A distributor's catalog is full of items
that differ in exactly one attribute, and a caller saying "M8 stainless screws"
has named a *family*, not a product.

So search returns three things the agent needs:

* `resolved` -- may I act on this, yes or no.
* `distinguishing_attributes` -- the attributes on which the candidates actually
  differ. Asking "what length?" is useful; asking "what material?" when every
  candidate is stainless is noise.
* `clarification_hint` -- a ready-made question.

Computing this server-side rather than shipping ten products to the model and
hoping it notices keeps the behaviour deterministic and testable.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product

#: Words that carry no discriminating power in a catalog query.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "by", "do", "for", "from", "have", "i", "in",
        "is", "it", "me", "need", "of", "on", "or", "our", "please", "some", "that", "the",
        "to", "want", "we", "with", "you", "your", "x", "get", "got", "looking", "like",
        "quote", "pcs", "pieces", "units", "unit", "each",
    }
)

#: Attribute keys ordered by how naturally a purchaser would be asked about
#: them. The first differing attribute becomes the clarifying question.
ATTRIBUTE_QUESTION_PRIORITY: tuple[str, ...] = (
    "length_mm",
    "material",
    "thread_size",
    "head_style",
    "finish",
    "bore_mm",
    "gauge_awg",
    "thickness_mil",
    "cut_level",
    "grade",
    "size_oz",
    "size_ml",
    "dimensions_in",
    "width_in",
    "length_in",
    "nrr_db",
)

#: How each attribute is phrased when asking the caller about it.
ATTRIBUTE_PHRASING: dict[str, str] = {
    "length_mm": "what length you need (in millimetres)",
    "material": "which material you need",
    "thread_size": "which thread size you need",
    "head_style": "which head style you need",
    "finish": "which finish you need",
    "bore_mm": "which bore size you need",
    "gauge_awg": "which wire gauge you need",
    "thickness_mil": "which thickness you need",
    "cut_level": "which cut level you need",
    "grade": "which grade you need",
    "size_oz": "which size you need",
    "size_ml": "which size you need",
    "dimensions_in": "which size you need",
    "width_in": "which width you need",
    "length_in": "which length you need",
    "nrr_db": "which noise reduction rating you need",
}

SKU_PATTERN = re.compile(r"\bATL-\d{4}\b", re.IGNORECASE)


def _normalise(token: str) -> str:
    """Fold a token to its comparison form.

    Naive singularisation only: "screws" -> "screw", "boxes" -> "box". A real
    system would use a proper stemmer, but over this catalog the simple rule is
    both sufficient and predictable, which matters more for a demo than recall.
    """
    token = token.strip().lower()
    if token.endswith("es") and len(token) > 4 and token[-3] in "sxz":
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def tokenise(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    tokens: list[str] = []
    for token in raw:
        # "30mm" should match both "30" and "30mm".
        match = re.fullmatch(r"(\d+)([a-z]+)", token)
        if match:
            tokens.extend([match.group(1), token])
            continue
        tokens.append(token)
    return [t for t in (_normalise(t) for t in tokens) if t and t not in STOPWORDS]


def _haystack(product: Product) -> set[str]:
    """Every token a product can be matched on."""
    parts = [product.name, product.description, product.category, product.search_terms]
    for key, value in (product.attributes or {}).items():
        parts.append(str(key).replace("_", " "))
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    tokens: set[str] = set()
    for part in parts:
        tokens.update(tokenise(str(part)))
    return tokens


def _score(product: Product, query_tokens: list[str]) -> int:
    haystack = _haystack(product)
    return sum(1 for token in query_tokens if token in haystack)


def _distinguishing_attributes(products: list[Product]) -> list[str]:
    """Attribute keys whose values differ across the candidate set."""
    if len(products) < 2:
        return []

    keys: list[str] = []
    for product in products:
        for key in (product.attributes or {}):
            if key not in keys:
                keys.append(key)

    differing: list[str] = []
    for key in keys:
        values = {
            str((product.attributes or {}).get(key, "<missing>")) for product in products
        }
        if len(values) > 1:
            differing.append(key)

    # Present the ones a buyer would actually be asked about first.
    ranked = [k for k in ATTRIBUTE_QUESTION_PRIORITY if k in differing]
    ranked += [k for k in differing if k not in ranked]
    return ranked


def _clarification_hint(products: list[Product], attributes: list[str]) -> str | None:
    if len(products) < 2:
        return None

    if attributes:
        key = attributes[0]
        phrasing = ATTRIBUTE_PHRASING.get(key, f"which {key.replace('_', ' ')} you need")
        options = []
        for product in products:
            value = (product.attributes or {}).get(key)
            if value is not None and str(value) not in options:
                options.append(str(value))
        if options:
            return (
                f"{len(products)} products match. Ask the caller {phrasing} "
                f"-- Atlas stocks {', '.join(options[:6])}."
            )
        return f"{len(products)} products match. Ask the caller {phrasing}."

    names = ", ".join(p.name for p in products[:4])
    return f"{len(products)} products match ({names}). Ask the caller which one they mean."


def search_products(session: Session, query: str, limit: int = 6) -> dict[str, Any]:
    """Resolve a spoken product description to candidate SKUs.

    Returns the *tied best* matches rather than a ranked list padded out to
    `limit`. If four products score equally well, all four come back and
    `resolved` is false; if one scores strictly highest, it comes back alone and
    `resolved` is true. That distinction is the whole contract with the agent.
    """
    query = (query or "").strip()

    # An explicit SKU is unambiguous by definition -- short-circuit.
    sku_match = SKU_PATTERN.search(query)
    if sku_match:
        sku = sku_match.group(0).upper()
        product = session.get(Product, sku)
        if product:
            return {
                "query": query,
                "match_count": 1,
                "resolved": True,
                "distinguishing_attributes": [],
                "clarification_hint": None,
                "products": [product],
            }

    query_tokens = tokenise(query)
    if not query_tokens:
        return {
            "query": query,
            "match_count": 0,
            "resolved": False,
            "distinguishing_attributes": [],
            "clarification_hint": "The description was empty. Ask the caller what they need.",
            "products": [],
        }

    products = list(session.scalars(select(Product)))
    scored = [(p, _score(p, query_tokens)) for p in products]

    # A candidate must match a majority of the caller's meaningful words.
    # Without this floor, a one-token overlap ("gloves") would drag in every
    # glove in the catalog for a query that named a specific material.
    threshold = max(1, (len(query_tokens) + 1) // 2)
    viable = [(p, s) for p, s in scored if s >= threshold]

    if not viable:
        return {
            "query": query,
            "match_count": 0,
            "resolved": False,
            "distinguishing_attributes": [],
            "clarification_hint": None,
            "products": [],
        }

    best = max(score for _, score in viable)
    top = [p for p, s in viable if s == best]
    top.sort(key=lambda p: p.sku)

    # A tie beyond `limit` is still a tie; report the true count so the agent can
    # say "we stock quite a few" rather than implying it saw all of them.
    match_count = len(top)
    shown = top[:limit]
    attributes = _distinguishing_attributes(shown)

    return {
        "query": query,
        "match_count": match_count,
        "resolved": match_count == 1,
        "distinguishing_attributes": attributes,
        "clarification_hint": _clarification_hint(shown, attributes),
        "products": shown,
    }
