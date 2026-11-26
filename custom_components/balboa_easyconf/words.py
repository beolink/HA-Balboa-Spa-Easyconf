"""The words for the spa's parts, in Swedish and English.

Entity names come from the translations; the part a power or energy entity
is about goes into its name as a placeholder, and placeholders are not
translated, so the words for the parts live here. The same words make the
labels of the power fields in the set-up and options forms
(scripts/build_strings.py).
"""

from __future__ import annotations

from .model import Component

LANGS = ("sv", "en")

KIND_WORDS: dict[str, tuple[str, str]] = {
    "heater": ("värmare", "heater"),
    "pump": ("pump", "pump"),
    "blower": ("blåsare", "blower"),
    "circulation_pump": ("cirkulationspump", "circulation pump"),
    "light": ("belysning", "light"),
    "aux": ("aux", "aux"),
    "mister": ("dimma", "mister"),
    "standby": ("styrsystem och wifi", "controller and Wi-Fi"),
}

LEVEL_WORDS: dict[str, tuple[str, str]] = {
    "on": ("på", "on"),
    "low": ("låg fart", "low speed"),
    "medium": ("mellanfart", "medium speed"),
    "high": ("hög fart", "high speed"),
}


def _pick(words: tuple[str, str], lang: str) -> str:
    return words[0] if lang == "sv" else words[1]


def component_words(component: Component, lang: str, *, numbered: bool = True) -> str:
    """ "pump 1", "värmare", "blåsare" (lower case, for the middle of a name)."""
    word = _pick(KIND_WORDS[component.kind], lang)
    if component.number is not None and numbered:
        return f"{word} {component.number}"
    return word


def level_words(component: Component, level: str, lang: str, *, numbered: bool = True) -> str:
    """ "pump 1, låg fart", or just "pump 2" for a part with one level."""
    base = component_words(component, lang, numbered=numbered)
    if len(component.levels) == 1:
        return base
    return f"{base}, {_pick(LEVEL_WORDS[level], lang)}"


def capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def numbered_kinds(components: list[Component]) -> set[str]:
    """Kinds with more than one part, whose names need their number."""
    counts: dict[str, int] = {}
    for component in components:
        counts[component.kind] = counts.get(component.kind, 0) + 1
    # Pumps keep their number even alone: the spa's panel and manual number them.
    return {kind for kind, count in counts.items() if count > 1} | {"pump"}


def language(hass_language: str | None) -> str:
    return "sv" if (hass_language or "").lower().startswith("sv") else "en"
