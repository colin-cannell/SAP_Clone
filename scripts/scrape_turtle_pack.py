#!/usr/bin/env python3
"""
Scrape pet and food stats/abilities for the Super Auto Pets *Turtle Pack*
(the base pack, Tier 1-6) from the community wiki.

Source: https://superautopets.wiki.gg/ (MediaWiki, CC-BY-SA content license).
Uses the site's public MediaWiki API (action=query / action=parse) rather
than scraping rendered HTML - it's the documented, low-load way to pull
wikitext, and we batch requests and rate-limit to be polite to their
servers per the license terms.

Output:
    data/turtle_pack/pets.json
    data/turtle_pack/foods.json

Usage:
    python3 scripts/scrape_turtle_pack.py
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://superautopets.wiki.gg/api.php"
USER_AGENT = "SAP-gym-env-scraper/0.1 (research project; contact: cjcannell35@gmail.com)"
CATEGORY = "Turtle Pack"
BATCH_SIZE = 40          # titles per API request (well under the 50-title anon cap)
REQUEST_DELAY_S = 0.5    # politeness delay between requests
DEFAULT_STAT_CAP = 50    # true for every Turtle Pack pet; named exceptions (e.g. Behemoth)
                          # live in later packs and are out of scope here.
DEFAULT_FOOD_COST = 3    # gold; a handful of foods override this (e.g. Sleeping Pill = 1)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "turtle_pack"


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------

def api_get(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_category_members(category: str) -> list[str]:
    """Return page titles in Category:<category>, paginating if needed."""
    titles: list[str] = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params)
        titles.extend(m["title"] for m in data["query"]["categorymembers"])
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        cmcontinue = cont
        time.sleep(REQUEST_DELAY_S)
    return titles


def fetch_wikitext_batch(titles: list[str]) -> dict[str, str]:
    """title -> raw wikitext, for one batch of <= BATCH_SIZE titles."""
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": "|".join(titles),
    }
    data = api_get(params)
    out = {}
    for page in data["query"]["pages"].values():
        if "revisions" not in page:
            continue  # missing/redirect page, skip
        out[page["title"]] = page["revisions"][0]["slots"]["main"]["*"]
    return out


def fetch_all_wikitext(titles: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for i in range(0, len(titles), BATCH_SIZE):
        batch = titles[i:i + BATCH_SIZE]
        result.update(fetch_wikitext_batch(batch))
        time.sleep(REQUEST_DELAY_S)
    return result


# --------------------------------------------------------------------------
# Minimal MediaWiki template parser
#
# We only need to pull out the first {{AnimalInfoBox ...}} / {{FoodInfoBox
# ...}} block and its named parameters. A regex can't do this reliably
# because parameter values contain nested templates like
# {{IconSAP|attack|nolink=yes}} which themselves contain "|" - so we track
# brace depth by hand and only split on "|" / "=" at the outermost level.
# --------------------------------------------------------------------------

def find_template_bounds(text: str, name: str) -> tuple[int, int] | None:
    """Return (start, end) of the first {{name ...}} template, end being the
    index right after its closing "}}". Brace-depth tracked by hand since
    values can contain nested templates."""
    marker = "{{" + name
    start = text.find(marker)
    if start == -1:
        return None
    i = start + 2
    depth = 1
    n = len(text)
    while i < n and depth > 0:
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i):
            depth -= 1
            i += 2
        else:
            i += 1
    return start, i


def find_template(text: str, name: str) -> str | None:
    """Return the raw inner text of the first {{name ...}} template, or None."""
    bounds = find_template_bounds(text, name)
    if bounds is None:
        return None
    start, end = bounds
    return text[start + 2:end - 2]  # inner text, braces stripped


def split_template_params(inner: str) -> dict[str, str]:
    """Split a template's inner text into {param_name: raw_value}.

    Positional (unnamed) params are skipped - the infoboxes we care about
    only use named params. Depth tracks both {{ }} (nested templates, e.g.
    {{IconSAP|attack|nolink=yes}}) and [[ ]] (wikilinks, e.g.
    [[Faint (Trigger)|Faint]]) since both use "|" internally and would
    otherwise be mistaken for a param separator.
    """
    parts: list[str] = []
    depth = 0
    i = 0
    start = 0
    n = len(inner)
    while i < n:
        if inner.startswith("{{", i) or inner.startswith("[[", i):
            depth += 1
            i += 2
            continue
        if inner.startswith("}}", i) or inner.startswith("]]", i):
            depth -= 1
            i += 2
            continue
        if inner[i] == "|" and depth == 0:
            parts.append(inner[start:i])
            start = i + 1
            i += 1
            continue
        i += 1
    parts.append(inner[start:])

    params: dict[str, str] = {}
    for part in parts[1:]:  # parts[0] is the template name
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        params[key.strip()] = val.strip()
    return params


# --------------------------------------------------------------------------
# Wikitext -> plain text cleanup
# --------------------------------------------------------------------------

_ICON_RE = re.compile(r"\{\{IconSAP\|([^|}]+)(?:\|([^}]*))?\}\}", re.IGNORECASE)
_FILE_LINK_RE = re.compile(r"\[\[(?:File|Image):[^\]]*\]\]", re.IGNORECASE)
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_BOLD_ITALIC_RE = re.compile(r"'{2,3}")
_GENERIC_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_WS_RE = re.compile(r"\s+")


def _icon_repl(m: re.Match) -> str:
    target, extra = m.group(1), m.group(2) or ""
    name_match = re.search(r"name=([^|]+)", extra)
    if name_match:
        return name_match.group(1).strip()
    if target.lower() in ("attack", "health", "gold", "experience"):
        return target.capitalize()
    return target.strip()


def clean_wikitext(text: str) -> str:
    if text is None:
        return ""
    text = _ICON_RE.sub(_icon_repl, text)
    text = _FILE_LINK_RE.sub("", text)  # decorative inline images, e.g. [[File:Attack.png|20x20px]]
    text = _LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    text = _BOLD_ITALIC_RE.sub("", text)
    # Any other template we don't specifically handle (e.g. {{distinguish|...}}
    # hatnotes) - drop it rather than leak raw braces into the output. Run
    # twice to catch simple one-level nesting left after the first pass.
    for _ in range(2):
        text = _GENERIC_TEMPLATE_RE.sub("", text)
    text = text.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    text = _WS_RE.sub(" ", text)
    return text.strip()


_LEVEL_LINE_RE = re.compile(r"^'''(?P<trig>.+?)'''\s*:\s*(?P<eff>.*)$")

# Canonical trigger phrases as used by the wiki's own ability text. A few
# pets (Beaver, Crocodile, Boar, ...) state their trigger as plain
# "Trigger: effect" text instead of "'''Trigger''': effect", so the bold
# regex above misses them; this whitelist lets us recover the trigger name
# instead of losing it into an untagged effect string. Sorted longest-first
# so e.g. "Friend ahead faints" isn't shadowed by a shorter partial match.
_KNOWN_TRIGGERS = sorted([
    "Start of battle", "Before attack", "After attack", "Hurt", "Faint",
    "Friend faints", "Friend ahead faints", "Knock out", "Summoned",
    "Friend summoned", "Level-up", "Sell", "Buy", "Start of turn",
    "End turn", "Eats food", "Friendly ate food", "Friend ahead attacks",
    "Four friends hurt", "Tier 1 friend bought",
], key=len, reverse=True)
_KNOWN_TRIGGER_LINE_RE = re.compile(
    r"^(?P<trig>" + "|".join(re.escape(t) for t in _KNOWN_TRIGGERS) + r")\s*:\s*(?P<eff>.*)$",
    re.IGNORECASE,
)


def parse_level_abilities(raw_value: str) -> list[dict]:
    """One infobox `level_N` value -> list of {trigger, effect} dicts.

    Most levels are a single "'''Trigger''': effect text" line. A few pets
    (e.g. Hippogriff) pack more than one trigger into the same level box,
    one per line.
    """
    abilities = []
    for line in raw_value.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _LEVEL_LINE_RE.match(line) or _KNOWN_TRIGGER_LINE_RE.match(line)
        if m:
            abilities.append({
                "trigger": clean_wikitext(m.group("trig")),
                "effect": clean_wikitext(m.group("eff")),
            })
        else:
            # Continuation text with no bold trigger prefix - append to the
            # previous ability's effect rather than dropping it.
            cleaned = clean_wikitext(line)
            if abilities and cleaned:
                abilities[-1]["effect"] = (abilities[-1]["effect"] + " " + cleaned).strip()
            elif cleaned:
                abilities.append({"trigger": "", "effect": cleaned})
    return abilities


_CATEGORY_RE = re.compile(r"\[\[Category:([^\]|]+)\]\]")
_PACK_CATEGORY_RE = re.compile(r"^(.+? Pack)$")


def extract_categories(wikitext: str) -> list[str]:
    return [c.strip() for c in _CATEGORY_RE.findall(wikitext)]


def extract_packs(categories: list[str]) -> list[str]:
    return [c for c in categories if _PACK_CATEGORY_RE.match(c)]


def extract_first_paragraph(wikitext: str, infobox_name: str) -> str:
    """Grab the descriptive paragraph right after the infobox, before the
    first == heading."""
    bounds = find_template_bounds(wikitext, infobox_name)
    if bounds is None:
        return ""
    _, end = bounds
    tail = wikitext[end:]
    heading_idx = tail.find("\n==")
    para = tail if heading_idx == -1 else tail[:heading_idx]
    return clean_wikitext(para)


def extract_gold_cost(wikitext: str, default: int = DEFAULT_FOOD_COST) -> tuple[int, str | None]:
    m = re.search(r"costs?\s+(\d+)\s+gold", wikitext, re.IGNORECASE)
    if m and int(m.group(1)) != default:
        return int(m.group(1)), f"overridden from default {default}g (source text says {m.group(0)})"
    return default, None


# --------------------------------------------------------------------------
# Per-page extraction
# --------------------------------------------------------------------------

@dataclass
class ScrapeStats:
    pets: int = 0
    foods: int = 0
    skipped: list[str] = field(default_factory=list)


def parse_pet(title: str, wikitext: str) -> dict | None:
    inner = find_template(wikitext, "AnimalInfoBox")
    if inner is None:
        return None
    params = split_template_params(inner)

    ah = params.get("attack/health", "")
    atk, hp = (ah.split("/") + ["", ""])[:2]

    levels = []
    for lvl in (1, 2, 3):
        key = f"level_{lvl}"
        if key in params:
            levels.append({
                "level": lvl,
                "abilities": parse_level_abilities(params[key]),
            })

    categories = extract_categories(wikitext)
    packs = extract_packs(categories)
    summary = extract_first_paragraph(wikitext, "AnimalInfoBox")

    return {
        "name": title,
        "tier": int(params["tier"]) if params.get("tier", "").strip().isdigit() else None,
        "base_attack": int(atk) if atk.strip().isdigit() else None,
        "base_health": int(hp) if hp.strip().isdigit() else None,
        "attack_cap": DEFAULT_STAT_CAP,
        "health_cap": DEFAULT_STAT_CAP,
        "wiki_id": int(params["ID"]) if params.get("ID", "").strip().isdigit() else None,
        "packs": packs,
        "secret_or_fusion": "secret" in summary.lower() and "combining" in summary.lower(),
        "levels": levels,
        "summary": summary,
        "source_url": f"https://superautopets.wiki.gg/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
    }


def parse_food(title: str, wikitext: str) -> dict | None:
    inner = find_template(wikitext, "FoodInfoBox")
    if inner is None:
        return None
    params = split_template_params(inner)

    categories = extract_categories(wikitext)
    packs = extract_packs(categories)
    summary = extract_first_paragraph(wikitext, "FoodInfoBox")
    gold_cost, cost_note = extract_gold_cost(wikitext)

    return {
        "name": title,
        "tier": int(params["tier"]) if params.get("tier", "").strip().isdigit() else None,
        "gold_cost": gold_cost,
        "gold_cost_note": cost_note,
        "wiki_id": int(params["ID"]) if params.get("ID", "").strip().isdigit() else None,
        "packs": packs,
        "effect": clean_wikitext(params.get("effect", "")),
        "summary": summary,
        "source_url": f"https://superautopets.wiki.gg/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    print(f"Fetching Category:{CATEGORY} member list...", file=sys.stderr)
    titles = fetch_category_members(CATEGORY)
    print(f"  {len(titles)} pages in category.", file=sys.stderr)

    print("Fetching wikitext (batched)...", file=sys.stderr)
    pages = fetch_all_wikitext(titles)

    pets: list[dict] = []
    foods: list[dict] = []
    stats = ScrapeStats()

    for title in titles:
        wikitext = pages.get(title)
        if wikitext is None:
            stats.skipped.append(f"{title} (no content returned)")
            continue

        pet = parse_pet(title, wikitext)
        if pet is not None:
            pets.append(pet)
            stats.pets += 1
            continue

        food = parse_food(title, wikitext)
        if food is not None:
            foods.append(food)
            stats.foods += 1
            continue

        stats.skipped.append(f"{title} (no AnimalInfoBox/FoodInfoBox found - likely a toy/other page)")

    pets.sort(key=lambda p: ((p["tier"] or 99), p["name"]))
    foods.sort(key=lambda f: ((f["tier"] or 99), f["name"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pets.json").write_text(json.dumps(pets, indent=2) + "\n")
    (OUT_DIR / "foods.json").write_text(json.dumps(foods, indent=2) + "\n")

    print(f"\nWrote {len(pets)} pets -> {OUT_DIR / 'pets.json'}", file=sys.stderr)
    print(f"Wrote {len(foods)} foods -> {OUT_DIR / 'foods.json'}", file=sys.stderr)
    if stats.skipped:
        print(f"\nSkipped {len(stats.skipped)} page(s):", file=sys.stderr)
        for s in stats.skipped:
            print(f"  - {s}", file=sys.stderr)


if __name__ == "__main__":
    main()
