"""
6.7 / FR11 — Drug-Interaction & Duplicate-Dose Advisory.

A maintained offline reference dataset maps medicine names to active
ingredients (medicine_reference.json) and known interaction pairs
(interaction_pairs.json). On every new-medicine confirmation, this
lookup checks the new active ingredient(s) against the user's
existing library and returns a plain advisory string if there's a
match.

Per Section 13 (Safety Requirements), this NEVER blocks or
auto-modifies anything — it only ever returns an advisory to be
spoken/displayed, framed as "please confirm with your pharmacist."
"""
import json
import os
from typing import List

from backend.schemas import InteractionAdvisory

_REF_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "medicine_reference.json")
_PAIRS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "interaction_pairs.json")

with open(_REF_PATH) as f:
    _REFERENCE = json.load(f)
with open(_PAIRS_PATH) as f:
    _INTERACTION_PAIRS = json.load(f)

_NAME_TO_INGREDIENT = {entry["name"].lower(): entry["active_ingredient"].lower() for entry in _REFERENCE}


def _active_ingredient_for(medicine_name: str) -> str:
    """Best-effort lookup; falls back to the name itself so unknown
    medicines still get *something* to compare (matches on exact
    repeats at minimum, per the duplicate-dose case)."""
    return _NAME_TO_INGREDIENT.get(medicine_name.strip().lower(), medicine_name.strip().lower())


def check_interactions(new_medicine_name: str, existing_medicine_names: List[str]) -> InteractionAdvisory:
    new_ingredient = _active_ingredient_for(new_medicine_name)
    existing_ingredients = {_active_ingredient_for(n) for n in existing_medicine_names}

    # Exact duplicate active ingredient (duplicate-dose case).
    if new_ingredient in existing_ingredients:
        return InteractionAdvisory(
            hasConflict=True,
            severity="Moderate",
            advisoryMessage=(
                f"This also contains {new_ingredient}, matching a medicine already in your "
                "library. Please confirm the combined dose with your pharmacist before taking both."
            ),
        )

    for pair in _INTERACTION_PAIRS:
        a, b = pair["pair"]
        if (new_ingredient == a and b in existing_ingredients) or (
            new_ingredient == b and a in existing_ingredients
        ):
            return InteractionAdvisory(
                hasConflict=True,
                severity=pair["severity"],
                advisoryMessage=pair["message"],
            )

    return InteractionAdvisory(
        hasConflict=False,
        severity="None",
        advisoryMessage="No known interactions or duplicate ingredients found against your current library.",
    )
