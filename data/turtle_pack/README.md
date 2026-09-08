# Turtle Pack data

Scraped by `scripts/scrape_turtle_pack.py` from the [Super Auto Pets Wiki](https://superautopets.wiki.gg/)
(wiki.gg, CC-BY-SA), via its public MediaWiki API — not the rendered HTML.
Ability/effect text is the wiki's own wording, lightly de-markup'd (links,
`{{IconSAP}}` icon templates, and bold formatting stripped); it is **not**
yet normalized into the `Trigger` enum + structured effect schema from
Section 5 of `SAP_clone.md` — that mapping is a separate downstream step.

Scope: everything currently in `Category:Turtle Pack` on the wiki (the
live, current-game-version categorization) — **61 pets** (Tier 1-6, 10 per
tier, plus the secret fusion pet Hippogriff) and **17 foods**. This is
deliberately narrower than the pack's own descriptive page text, which
still lists a couple of items (e.g. Cake) that were moved out of the pack
in a later game patch per that item's own version history — the category
tag reflects the current state, the prose table doesn't always.

## Files

- `pets.json` — array of pet objects, sorted by (tier, name).
- `foods.json` — array of food objects, sorted by (tier, name).

### Pet schema

```
{
  "name": str,
  "tier": int,
  "base_attack": int,
  "base_health": int,
  "attack_cap": int,        # 50 for every pet here; named higher-cap
  "health_cap": int,        #   exceptions (e.g. Behemoth) live in later packs
  "wiki_id": int | null,    # the wiki's internal pet ID, when the infobox sets one
  "packs": [str],           # usually just ["Turtle Pack"]
  "secret_or_fusion": bool, # true for pets only obtainable by combining two
                             #   other specific pets (e.g. Hippogriff), not bought
  "levels": [
    {
      "level": 1|2|3,
      "abilities": [ { "trigger": str, "effect": str }, ... ]
      # usually one ability per level; a few pets (e.g. Hippogriff) list
      # more than one trigger per level. "trigger" is "" for the couple of
      # pets whose ability is a continuous passive with no wiki-stated
      # trigger (Cat, Tiger).
    }, ...
  ],
  "summary": str,           # first descriptive paragraph, de-markup'd
  "source_url": str
}
```

### Food schema

```
{
  "name": str,
  "tier": int,
  "gold_cost": int,             # 3 by default; a few foods override this
  "gold_cost_note": str | null, # explains the override, e.g. Sleeping Pill = 1g
  "wiki_id": int | null,
  "packs": [str],
  "effect": str,                # de-markup'd effect text, single line
  "summary": str,
  "source_url": str
}
```

## Re-running

```
python3 scripts/scrape_turtle_pack.py
```

Hits the wiki's `api.php` in batches of 40 titles with a 0.5s delay between
requests — polite to their servers, per the wiki's CC-BY-SA terms.
