# tools

## `visualize_sap2.py`

A terminal visualizer for `sap2-v1` matches, driven by the real C engine
(`policyclash_envs.make("sap2-v1")`) — not a reimplementation, and not the
browser "Turtle Shop" artifact's separate JS engine.

```
policy-clash/envs/.venv/bin/python tools/visualize_sap2.py
policy-clash/envs/.venv/bin/python tools/visualize_sap2.py --seed 42 --pause 0.6
policy-clash/envs/.venv/bin/python tools/visualize_sap2.py --style random --max-rounds 5
```

Run with the `policy-clash` venv's Python — `policyclash_envs` is installed
editable there, same as `training/sap_selfplay_ppo.py` already requires.
`rich` was added to that venv for this tool.

**What it can and can't show, and why.** `sap2_battle` in the C core
resolves a round's fight and returns only the aggregate outcome
(`P0_WIN`/`P1_WIN`/`DRAW`) — it doesn't record a per-exchange trace, by
design (`adding-an-env.md`'s "keep the adapter thin" rule). So this tool
shows exactly what the real engine exposes: each seat's team/shop/gold/
lives/trophies before a round, the shop actions taken that round (decoded
from the actions the env actually received), and the round's result — not
a fabricated blow-by-blow battle animation. The browser game's battle log
is a genuinely separate JS reimplementation of the battle algorithm that
tracks a trace for exactly this reason; this tool deliberately doesn't
duplicate that, so nothing it shows can silently drift from what the real
engine did.

Caught one real thing worth knowing about while building this: the
turn-3 life-back rule can fire in the same transition that costs a seat
its first life, immediately restoring it — so "Seat X loses a life" from
naively inferring off the trophy count can flatly contradict the very
next panel's displayed life total. The tool reads the actual before/after
lives delta rather than inferring, and calls out the catch-up rule
explicitly when it's what happened.
