import re
from difflib import SequenceMatcher

from .models import CatalogItem
from .schemas import CatalogMatch


def normalize(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(
        None,
        normalize(a),
        normalize(b)
    ).ratio()


def extract_attributes(value: str) -> set[str]:
    """
    Extract meaningful product specifications.

    Examples:
        A5 -> a5
        A4 -> a4
        16oz -> 16oz
        20oz -> 20oz
        500ml -> 500ml
        64GB -> 64gb
        8ft -> 8ft
    """

    normalized = normalize(value)

    attributes = set()

    # Paper/product sizes: A4, A5, A6...
    attributes.update(
        re.findall(r"\ba\d+\b", normalized)
    )

    # Measurements/specifications
    attributes.update(
        re.findall(
            r"\b\d+(?:oz|in|ft|ml|gb|tb|pk)\b",
            normalized
        )
    )

    return attributes

def find_catalog_match(
    description: str,
    catalog: list[CatalogItem]
) -> CatalogMatch:

    normalized_description = normalize(description)

    print("========== RECONCILER DEBUG ==========")
    print("DESCRIPTION:", description)
    print("CATALOG SIZE:", len(catalog))

    requested_attributes = extract_attributes(description)

    print("REQUESTED ATTRIBUTES:", requested_attributes)

    # ---------------------------------------------------------
    # 1. Exact normalized match
    # ---------------------------------------------------------

    exact = [
        item
        for item in catalog
        if normalize(item.name) == normalized_description
    ]

    if exact:
        item = exact[0]

        print("EXACT MATCH:", item.sku, item.name)

        return CatalogMatch(
            sku=item.sku,
            name=item.name,
            confidence=1.0,
            match_type="exact",
            reason="Normalized product name exactly matches the catalog.",
        )

    # ---------------------------------------------------------
    # 2. Specification-based matching
    # ---------------------------------------------------------

    if requested_attributes:

        specification_matches = []

        for item in catalog:

            catalog_attributes = extract_attributes(item.name)

            if requested_attributes == catalog_attributes:

                specification_matches.append(item)

        print(
            "SPECIFICATION MATCHES:",
            [
                (item.sku, item.name)
                for item in specification_matches
            ]
        )

        # Exactly one catalog item has the requested specification
        if len(specification_matches) == 1:

            item = specification_matches[0]

            print(
                "SPECIFICATION MATCH SELECTED:",
                item.sku,
                item.name
            )

            return CatalogMatch(
                sku=item.sku,
                name=item.name,
                confidence=0.95,
                match_type="attribute",
                reason=(
                    "Catalog item selected using the matching "
                    "product specification."
                ),
            )

        # More than one item has same specification.
        # Use fuzzy matching among those candidates.
        if len(specification_matches) > 1:

            scored = sorted(
                [
                    (
                        similarity(description, item.name),
                        item
                    )
                    for item in specification_matches
                ],
                key=lambda x: x[0],
                reverse=True
            )

            score, item = scored[0]

            if len(scored) == 1 or (
                score - scored[1][0] >= 0.06
            ):

                return CatalogMatch(
                    sku=item.sku,
                    name=item.name,
                    confidence=max(score, 0.85),
                    match_type="attribute_fuzzy",
                    reason=(
                        "Catalog item selected using matching "
                        "product specification and name similarity."
                    ),
                )

    # ---------------------------------------------------------
    # 3. Normal fuzzy matching fallback
    # ---------------------------------------------------------

    scored = sorted(
        [
            (
                similarity(description, item.name),
                item
            )
            for item in catalog
        ],
        key=lambda x: x[0],
        reverse=True
    )

    if not scored:

        return CatalogMatch(
            sku=None,
            name=None,
            confidence=0,
            match_type="no_catalog",
            reason="Catalog is empty.",
        )

    score, item = scored[0]

    second_score = (
        scored[1][0]
        if len(scored) > 1
        else 0
    )

    print(
        "FUZZY TOP:",
        item.sku,
        item.name,
        score
    )

    # ---------------------------------------------------------
    # 4. Minimum confidence
    # ---------------------------------------------------------

    if score < 0.72:

        return CatalogMatch(
            sku=None,
            name=None,
            confidence=score,
            match_type="no_confident_match",
            reason=(
                "No catalog item reached the minimum "
                "similarity threshold."
            ),
        )

    # ---------------------------------------------------------
    # 5. Ambiguous fuzzy match
    # ---------------------------------------------------------

    if score - second_score < 0.06:

        return CatalogMatch(
            sku=None,
            name=None,
            confidence=score,
            match_type="ambiguous",
            reason=(
                "Top catalog candidates are too close "
                "to choose safely."
            ),
        )

    # ---------------------------------------------------------
    # 6. Successful fuzzy match
    # ---------------------------------------------------------

    return CatalogMatch(
        sku=item.sku,
        name=item.name,
        confidence=score,
        match_type="fuzzy",
        reason=(
            "Best catalog match selected by normalized "
            "string similarity."
        ),
    )