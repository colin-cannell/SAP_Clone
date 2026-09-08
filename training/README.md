# Training

Self-play PPO for `sap-v1`, driving the existing, already-tested `Sap` env
from `policy-clash/envs/policyclash_envs` directly — no PufferLib.

## Why not PufferLib

`https://puffer.ai` was the original ask. Checked against PufferLib's `4.0`
branch directly (not the summary in `policy-clash`'s own docs) before
writing anything: there is no pure-Python env path in that branch. Every
env is a native C module (`ocean/<name>/`) statically compiled into
`pufferlib/_C.so` by `build.sh`, driven through `.ini` config and the
`puffer train/eval/sweep` CLI. Training `sap-v1` there means a **second**,
separately-maintained implementation of the shop/battle rules against
PufferLib's `vecenv.h` struct-and-macro contract — not a wrapper around
`policy-clash/envs/csrc/sap.h`, a rewrite of it.

That port is a bounded task if it happens (`ocean/robocode/` — the
smallest real 2-agent self-play example, not `ocean/chess/`'s 3600 lines —
is ~1270 lines total including its bot AI, and the `vecenv.h` contract
itself is learnable: `my_init`, `my_setup_perm`, `my_log`, plus a rules
file exposing `allocate_env`/`c_reset`/`c_step`/`c_close`, no rendering
required for headless training). But it's real new work with a real
duplication cost, so this directory exists to answer one question first
without paying it: **does self-play PPO actually learn anything on this
env at all?** If the training signal is dead or broken, no amount of
throughput fixes that, and finding out costs zero new rules code.

**Update: the native port now exists**, at `pufferlib/ocean/sap/` (a
sibling checkout, branch `4.0`), once this script validated the training
signal was real (95%+ vs. a random baseline within 20 iterations). See
`pufferlib/ocean/sap/README.md` for the full story — it reuses
`policy-clash/envs/csrc/sap.h` **verbatim** as `sap_rules.h` (zero new
rules code, only a binding around the same functions this script already
calls through `policyclash_envs`), validated with a standalone 200k-episode
harness (no crashes, ~3M ticks/sec single-threaded, sane outcome
distribution), and documents two real bugs a naive "does it compile"
check would have missed. Not yet run through an actual `puffer train` pass
— building the full trainer on this machine hits two environment gaps
unrelated to this env (documented in that README): `build.sh`'s x86_64-only
SIMD flags, and CUDA being required even for `--cpu` mode's static-compile
stage.

## Usage

Uses the `policy-clash/envs/.venv` venv (already has `policyclash_envs`
installed editable; PyTorch was added to it for this):

```
cd training
../policy-clash/envs/.venv/bin/python sap_selfplay_ppo.py [flags]
```

Key flags (see `--help` for the rest): `--iterations`,
`--episodes-per-iter`, `--eval-every` / `--eval-episodes` (win rate vs a
uniform-random legal-action baseline — self-play win rate alone is always
~50% by construction and says nothing about absolute progress),
`--checkpoint-every` (writes `checkpoints/sap_ppo_iter<N>.pt`, a plain
`state_dict` for `ActorCritic`).

## Design notes

- **One network plays both seats.** `sap-v1`'s shop-phase observation is
  already from the acting seat's own perspective with no `player` field
  (`policyclash_envs/base.py`), so there's nothing seat-specific to
  condition on.
- **Reward is sparse and terminal, credited per-seat at that seat's own
  last action**, not at the episode's last tick. A seat's trajectory ends
  when it stops being asked to act (`END_TURN`, or its `SHOP_ACTION_BUDGET`
  forcing it) — after that point it makes no more decisions that affect
  the outcome, so GAE over its own trajectory needs no bootstrap past that
  point. See the module docstring in `sap_selfplay_ppo.py` for the full
  reasoning; this is the standard treatment for agents that finish acting
  at different times within one shared episode.
- **The legal-action mask is applied before sampling, always** — same
  contract the env itself enforces (`docs/adding-an-env.md`: "illegal
  actions forfeit"). This means `Termination.ILLEGAL_ACTION` should never
  actually fire during training; the per-iteration log line counts it
  anyway as a canary that masking broke.
- **Observation scaling** (`OBS_SCALE` in `sap_selfplay_ppo.py`) rescales
  the raw integer fields (gold, attack, health, Duck's shop hp-bonus) down
  to roughly the same range as the one-hot flags they sit next to in the
  136-float vector, so a freshly-initialized network's early gradients
  aren't dominated by the larger raw magnitudes. One-hots are untouched.
