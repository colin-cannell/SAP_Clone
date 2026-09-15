# env-src

`policy-clash/` and `pufferlib/` (siblings of this repo's root, one level
up from here in a full checkout) are separate git clones of other
projects — [pjsny/policy-clash](https://github.com/pjsny/policy-clash) and
[PufferAI/PufferLib](https://github.com/PufferAI/PufferLib) — not vendored
into this repo. This directory holds copies of only the files this project
added or changed inside those checkouts, at the same relative paths, so
they can be dropped back in.

**Superseded, as of the Tier-2 roster work (2026-09-14): `sap-v1` is gone
from `policy-clash` upstream.** `sap.h`/`sap_binding.c`/`sap.py`/
`test_sap.py` used to be mirrored here; upstream (pjsny/policy-clash)
replaced `sap-v1` with `sap2-v1` (the full multi-round Arena match) some
time after this repo forked from it, and only `sap2` is registered in the
checkout now. The old sap-v1 mirror below was deleted rather than kept
alongside a registry that no longer references it — training/'s own
self-play script still targets `sap-v1` and needs that env restored (from
git history, or reimplemented against `sap2-v1`) before it will run again.
See `docs/envs/sap-v2.md` for what `sap2-v1` covers now: the Tier-1
roster verified against the shipped build, plus a Tier-2 roster
(10 more pets, 6 more foods) added and verified the same way.

## Reproducing the checkout

```
git clone https://github.com/pjsny/policy-clash.git
cp -r env-src/policy-clash/envs/. policy-clash/envs/
cp -r env-src/policy-clash/tools/. policy-clash/tools/

git clone --branch 4.0 https://github.com/PufferAI/PufferLib.git pufferlib
cp -r env-src/pufferlib/. pufferlib/
```

`policy-clash/envs/policyclash_envs/__init__.py` and `envs/setup.py` here
are the **full files**, already containing the upstream content plus the
`sap2-v1` registration — not a diff — so the `cp -r` above is safe to run
directly against a fresh clone. The Tier-2 roster work itself lives on
the `tier2-roster` branch of
[colin-cannell/policy-clash](https://github.com/colin-cannell/policy-clash)
(forked from upstream `main`, not yet a PR back to pjsny/policy-clash);
this directory is the same content, laid out for a clean-upstream-clone
instead of a fork checkout.

## What's in each

- **`policy-clash/`** — `sap2-v1`, the evaluation-shaped env (`TwoPlayerEnv`
  interface: `reset`/`step`/`replay`, seat-indexed observations, legal-mask
  enforcement, plus `Forkable` for search-based bots). Spec:
  [`docs/envs/sap-v2.md`](../docs/envs/sap-v2.md). 70 passing tests at
  `envs/tests/test_sap2.py`. `tools/visualize_sap2.py` is included too -
  it decodes the observation layout directly (species/food counts,
  perk/slot widths) rather than hardcoding it, so it's worth keeping in
  sync with the env it renders.
- **`pufferlib/`** — a native PufferLib training port, against the
  now-removed `sap-v1`. `ocean/sap/sap_rules.h` is a **verbatim copy** of
  the `sap.h` this repo no longer has a live copy of (see the superseded
  note above) - the rules core was framework-free C, so this port needed
  no second implementation of the game rules, only a binding
  (`ocean/sap/sap.h`, `binding.c`) adapting the same functions to
  PufferLib's `vecenv.h` contract. See `pufferlib/ocean/sap/README.md`
  for what was validated, two real bugs found writing a standalone test
  harness, and the build gaps hit attempting this on Apple Silicon
  without a CUDA GPU. Porting `sap2-v1` here instead is unstarted.

`training/` (this repo's own top level, not under `env-src/`) is a third,
independent path: a plain PyTorch self-play PPO loop driving the
`policy-clash` env directly, no PufferLib involved. It exists because it
answers "does the training signal even work" far more cheaply than the
native port does — see `training/README.md`.
