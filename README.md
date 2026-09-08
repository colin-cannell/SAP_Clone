# SAP_Clone

A [Super Auto Pets](https://teamwoodgames.com/games/super-auto-pets)
simulator built as an evaluation environment for
[policy-clash](https://github.com/pjsny/policy-clash) (head-to-head RL
policy evaluation) and a training environment for
[PufferLib](https://puffer.ai) — plus the data pipeline and design work
behind both.

## Status

**`sap-v1`, Tier 1 MVP: implemented and tested** against `policy-clash`'s
`TwoPlayerEnv` interface (19 passing tests), and ported to PufferLib as a
native training env (validated via a 200k-episode standalone harness).
Self-play PPO against the `policy-clash` env directly already shows a real
training signal (95%+ win rate vs. a random baseline within 20
iterations). Not yet run through an actual `puffer train` pass — see
`env-src/pufferlib/ocean/sap/README.md` for why (a build-environment gap
on Apple Silicon, unrelated to this env's own code).

## Layout

| path | what |
|---|---|
| [`SAP_clone.md`](SAP_clone.md) | Design doc: the real game's rules, the MVP scope, and how this maps onto `policy-clash`'s interface. Start here. |
| [`docs/envs/sap-v1.md`](docs/envs/sap-v1.md) | The `sap-v1` env spec: action/observation encoding, step-limit derivation, battle-trigger ordering — written before the C code, corrected against it. |
| [`data/turtle_pack/`](data/turtle_pack/) | Scraped pet/food stats (all 6 tiers, 61 pets + 17 foods) from the Super Auto Pets wiki, with a documented JSON schema. |
| [`scripts/scrape_turtle_pack.py`](scripts/scrape_turtle_pack.py) | The scraper that produced the data above, via the wiki's MediaWiki API. |
| [`training/`](training/) | Self-play PPO against the `policy-clash` env directly, no PufferLib — validates the training signal cheaply before paying for a native port. |
| [`env-src/`](env-src/) | The actual `sap-v1` implementation and its PufferLib port — copies of what was added to two external checkouts (`policy-clash`, `pufferlib`), which aren't vendored into this repo. See `env-src/README.md` for how to reproduce those checkouts and drop these back in. |

## Why two implementations of the same rules don't exist

The C rules core (`env-src/policy-clash/envs/csrc/sap.h`) has zero
dependency on either `policy-clash`'s Python binding or PufferLib —
`env-src/pufferlib/ocean/sap/sap_rules.h` is a verbatim copy of it. One
gets a thin CPython binding for evaluation, the other a thin PufferLib
binding for training; the game rules (shop mechanics, ability effects,
battle resolution) are written once.
