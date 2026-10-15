"""Code lists from the TLC yellow-taxi data dictionary.

These small dimensions change rarely and only when TLC republishes the dictionary, so
they live in code (reviewed like any other change) rather than in a lookup file.
Source: TLC "Data Dictionary - Yellow Taxi Trip Records". Check it again when TLC
announces a new revision.
"""

from __future__ import annotations

from typing import Final

# Codes seen in the data but missing from the dictionary resolve to this member, so the
# fact table never has a null or dangling foreign key.
UNKNOWN_CODE: Final = -1
UNKNOWN_NAME: Final = "Unknown"

VENDORS: Final[dict[int, str]] = {
    1: "Creative Mobile Technologies, LLC",
    2: "Curb Mobility, LLC",
    6: "Myle Technologies Inc",
    7: "Helix",
}

RATE_CODES: Final[dict[int, str]] = {
    1: "Standard rate",
    2: "JFK",
    3: "Newark",
    4: "Nassau or Westchester",
    5: "Negotiated fare",
    6: "Group ride",
    99: "Null/unknown",
}

PAYMENT_TYPES: Final[dict[int, str]] = {
    0: "Flex Fare trip",
    1: "Credit card",
    2: "Cash",
    3: "No charge",
    4: "Dispute",
    5: "Unknown",
    6: "Voided trip",
}


def with_unknown(codes: dict[int, str]) -> list[tuple[int, str]]:
    """The code list as sorted rows, plus the unknown member."""
    return [(UNKNOWN_CODE, UNKNOWN_NAME), *sorted(codes.items())]
