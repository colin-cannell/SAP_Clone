# env-src

`policy-clash/` and `pufferlib/` (siblings of this repo's root, one level
up from here in a full checkout) are separate git clones of other
projects — [pjsny/policy-clash](https://github.com/pjsny/policy-clash) and
[PufferAI/PufferLib](https://github.com/PufferAI/PufferLib) — not vendored
into this repo. This directory holds copies of only the files this project
added or changed inside those checkouts, at the same relative paths, so
they can be dropped back in.

## Reproducing the checkouts

```
git clone https://github.com/pjsny/policy-clash.git
cd policy-clash && git checkout -b sap-v1-env && cd ..
cp -r env-src/policy-clash/envs/. policy-clash/envs/

git clone --branch 4.0 https://github.com/PufferAI/PufferLib.git pufferlib
cp -r env-src/pufferlib/. pufferlib/
```

`policy-clash/envs/policyclash_envs/__init__.py` and `envs/setup.py` here
are the **full files**, already containing the upstream content plus the
`sap-v1` registration — not a diff — so the `cp -r` above is safe to run
directly against a fresh clone.

## What's in each

- **`policy-clash/`** — `sap-v1`, the evaluation-shaped env (`TwoPlayerEnv`
  interface: `reset`/`step`/`replay`, seat-indexed observations, legal-mask
  enforcement). Spec: [`docs/envs/sap-v1.md`](../docs/envs/sap-v1.md).
  19 passing tests at `envs/tests/test_sap.py`.
- **`pufferlib/`** — a native PufferLib training port. `ocean/sap/sap_rules.h`
  is a **verbatim copy** of `policy-clash/envs/csrc/sap.h` — the rules
  core is framework-free C, so this port needed no second implementation
  of the game rules, only a binding (`ocean/sap/sap.h`, `binding.c`)
  adapting the same functions to PufferLib's `vecenv.h` contract. See
  `pufferlib/ocean/sap/README.md` for what was validated, two real bugs
  found writing a standalone test harness, and the build gaps hit
  attempting this on Apple Silicon without a CUDA GPU.

`training/` (this repo's own top level, not under `env-src/`) is a third,
independent path: a plain PyTorch self-play PPO loop driving the
`policy-clash` env directly, no PufferLib involved. It exists because it
answers "does the training signal even work" far more cheaply than the
native port does — see `training/README.md`.
