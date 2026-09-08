# sap (Ocean env)

Native PufferLib port of `sap-v1` (see `docs/envs/sap-v1.md` and
`policy-clash/envs/csrc/sap.h` in the sap-gym-env project this was built
alongside). Selfplay-only, 2 agents, headless (no rendering in this first
pass).

## Files

- `sap_rules.h` — **verbatim copy** of `policy-clash/envs/csrc/sap.h`. Zero
  PufferLib dependency (same as it has zero Python dependency), so this
  port needed no second implementation of the rules - only a binding
  around the same `sap_reset`/`sap_step`/`sap_observe`/`sap_legal`
  functions already written and tested against policy-clash's own 19-test
  suite. Re-sync by re-copying if the upstream file changes.
- `sap.h` — the PufferLib-facing wrapper: `Sap` struct, `init` /
  `allocate_sap` / `c_reset` / `c_step` / `c_close` / `c_render` (a no-op
  stub - headless only). Adapts sap_rules.h's one-call-per-function API to
  vecenv.h's per-tick array-write contract (`obs_ptr`/`action_ptr`/
  `reward_ptr`/`terminal_ptr`, auto-reset on terminal).
- `binding.c` — `my_init` / `my_setup_perm` / `my_log` + `#include
  "vecenv.h"`. Defines `MY_ACTION_MASK` (chess-style legal-action masking,
  which robocode's simpler example doesn't need but this env does, same as
  the policy-clash/pure-Python versions both require it).

## Both seats act every tick - no chess-style turn simulation needed

Chess must simulate "one mover at a time" inside a framework that always
asks every agent slot for an action every tick, because chess genuinely
has only one mover. SAP's shop phase has no such constraint: neither seat
sees the other's team or shop, so there is nothing for the two seats'
actions to interact over until battle. `c_step` calls
`sap_step(core, a0, a1)` directly, one PufferLib tick per real shop tick -
exactly what `policyclash_envs/sap.py`'s own adapter does. A seat that has
already ended (`sap_rules.h`'s per-seat `ended` flag) has its action
ignored inside `sap_step`, same as always; `sap_observe` naturally keeps
returning its frozen last state every subsequent tick with no
special-casing needed here, since that seat's Markov state genuinely
hasn't changed.

## Two real bugs a standalone harness caught before this ever touched real training

Neither was in `sap_rules.h` - both were in this new wrapper, found by
writing throwaway `/tmp` test harnesses that called `allocate_sap`/
`c_reset`/`c_step` directly (no Python, no vecenv.h vectorization, just
the plain C functions), rather than trusting the framework macros compiled
clean and calling it done:

1. **`c_reset` was clobbering the very outcome it needed to report.** The
   auto-reset-on-terminal convention every Ocean env uses (chess, robocode,
   go, slimevolley) is: `c_step`'s terminal branch sets
   `reward_ptr`/`terminal_ptr` to the finished episode's outcome, then
   calls `c_reset` to prepare the next episode - and `c_reset` itself must
   never touch reward/terminal, only the internal game state and the
   observation buffer. An early draft's `c_reset` zeroed reward/terminal
   "for safety," which silently overwrote every episode's real result back
   to `0.0`/ongoing immediately after it was set, so every episode looked
   like it never terminated. A harness that only checked "does it compile"
   or "does it run 2000 episodes without crashing" (both of which it did)
   would have missed this - it took printing `terminal_ptr` after each
   `c_step` and noticing it was always `0.0` even after `sap_step` had
   genuinely returned `SAP_DRAW`.
2. **`env->log` was uninitialized garbage.** It's a plain struct field, not
   a `calloc`'d buffer, and nothing zeroed it before first use - one test
   run printed a correct `slot_0_score`/`n` but a wildly wrong
   `draw_rate` (a stack-garbage float bit pattern), because that run's
   stack memory for the struct wasn't already zero the way an earlier run's
   coincidentally had been. Fixed by explicitly zeroing `env->log` in
   `init()` (the one-time per-instance setup call), not `c_reset` (which
   runs every episode and must not reset a stat that accumulates across
   many of them).

## Validated so far

- Compiles clean against the real `vecenv.h` macro contract (`-Wall
  -Wextra`, zero warnings from this env's own code - see the SIMD_FLAGS
  note below for what building the *whole* trainer needs beyond this).
- A standalone `/tmp` harness ran 200,000 full episodes under a uniform
  *legal* random policy (masked via `action_mask_ptr`, exercising every
  action category - buy/sell/combine/reroll/reposition/food/real battles,
  not just the trivial empty-team case) with no crashes: p0=34.6%,
  p1=34.5%, draw=30.9% (sane, not lopsided - a seat-order bug would show up
  as an asymmetric split), ~3M ticks/sec single-threaded, log stats
  reconciling exactly against the episode counts.
- Not yet run through an actual `puffer train` pass end-to-end - see below.

## Building on Apple Silicon: two environment gaps, not this env's bugs

Both already flagged, independently, in `policy-clash/docs/adding-an-env.md`'s
own PufferLib section before this port existed - confirmed for real
attempting to build `sap` here, not just cited secondhand:

1. `build.sh` applies `SIMD_FLAGS=(-mavx2 -mfma)` unconditionally to the
   static-object compile step, in every mode including `--cpu` - x86_64
   only, no arm64 branch. Building on Apple Silicon needs those flags
   stripped locally first (a scoped, temporary edit to a *checked-out copy*
   of `build.sh`, not something to commit upstream without more thought
   about what it costs on the x86_64 builds that do want them).
2. The default (no `--cpu`/`--web`/etc.) build mode requires `nvcc`/CUDA
   unconditionally for the actual trainer backend - there is no
   CPU-without-CUDA default. `--cpu` exists for exactly this case but still
   goes through step 1's static-compile stage first.

Given both, this session validated the env at the `binding.c`-against-
`vecenv.h` level (direct `clang -c`, and the standalone harnesses above),
not via a full `puffer train sap` run - that needs either an x86_64 box, a
CUDA GPU, or both gaps patched locally, none of which this session had.
The C code itself is confirmed correct at the level a `puffer train`
launch would actually exercise beyond what's already been validated here.
