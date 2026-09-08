# SAP_clone — Super Auto Pets Env Design Doc

**Purpose of this file:** shared reference for both agents working on this (chat-Claude and Claude Code). It covers the real game's rules well enough to implement a simulator, and maps those rules onto the `policy-clash` two-player env interface (see `docs/adding-an-env.md`, Connect4 reference implementation). This is a design doc, not a full data dump — the full pet/food/toy database is a separate scraping task, scoped at the bottom.

Source: [Super Auto Pets Wiki (wiki.gg)](https://superautopets.wiki.gg/) — the actively maintained wiki; the Fandom mirror is stale and says so on its own pages. All descriptions below are paraphrased summaries of mechanics, not copied wiki text.

---

## 1. What the real game is

Super Auto Pets is an auto-battler: two teams of pets are assembled during a shop phase, then fight automatically with no player input during the battle phase. Modes differ only in win condition — Arena Mode is first-to-10-match-wins, Versus/Friends is last-player-standing across a shared pool. For a policy-clash env we only care about **one head-to-head match resolution**: build a team, then compare it against an opponent's team. The meta-progression (multiple rounds, life totals, trophies) is a separate layer we can add once single-battle resolution works.

## 2. Turn structure

Each turn has two phases:

1. **Shop phase.** Player has Gold (10 per turn by default) to spend on:
   - Buying a pet into an empty slot (3 gold each)
   - Buying food (varies by food, feeds one pet)
   - Rerolling the shop for new offers (costs gold)
   - Freezing a shop slot so it persists into next turn
   - Combining two pets of the same type already on the team (free)
   - Selling a pet (refunds 1 gold per pet level)
   - Repositioning pets left-to-right
   No time pressure for a simulator — this phase is turn-based decisions, not real-time.

2. **Battle phase.** Fully automatic — no legal actions here, it's pure simulation given the two frozen team states.

Team size cap: **5 pets.** Pet tiers gate what appears in the shop — tier *X* unlocks on turn `2X − 1` (tier 1 on turn 1, tier 2 on turn 3, tier 3 on turn 5, ... tier 6 on turn 11), and once unlocked, all lower tiers can still appear.

## 3. Pet stats and leveling

- Two stats per pet: **Attack** and **Health**, both capped at 50 for most pets (a couple of named exceptions have higher caps — flag these as special cases when populating data, don't hardcode 50 everywhere).
- **Combining** two pets of the same type: keep one copy, add +1 to whichever of Attack/Health is higher on each side (not a straight stat sum), and add their XP together. Enough accumulated XP levels the pet up (level 1 → 2 → 3), which can grant a stronger version of its ability.
- Buffs come in two flavors: **temporary** (battle-only, reset after) and **permanent** (persist across turns, acquired mostly through food or certain abilities).
- **Summon** is a specific event type: a pet entering an *empty* slot (bought, or spawned by another pet's effect) counts as a summon; combining two owned pets does not. This distinction matters because some abilities trigger specifically on summon.

## 4. Battle resolution algorithm

This is the part to implement carefully in the C core, since ordering bugs are the most common source of divergence from the real game:

1. **Start of battle**: every pet with a start-of-battle trigger fires, in attack-descending order (ties broken randomly, per the shared seed).
2. **Combat loop**, repeated until one side has zero pets left:
   - The front (right-most, i.e. next-to-fight) pet on each side deals damage to each other simultaneously, equal to each one's current Attack.
   - Any pet at 0 or less Health faints and is removed; the next pet in line shifts up.
   - Fainting can itself trigger abilities (on-faint, on-friend-fainted, on-knockout dealt), which resolve before the next combat exchange, again ordered by attack descending with random tiebreak.
   - Hurt-but-not-fainted also has its own trigger category, separate from faint.
3. **Outcome**: win (opponent has 0 pets, yours has ≥1), loss (reverse), draw (both hit 0 simultaneously).

Community consensus (semi-confirmed by the developer on Steam forums) is that **all same-trigger-type abilities resolve in strict attack-descending order with random tiebreaks** — there is no fixed left/right precedence rule beyond that. This is worth encoding as the canonical rule rather than guessing at positional tiebreaks.

## 5. Ability trigger taxonomy

Build this as an enum in the C core — every pet ability hangs off one of these:

- `StartOfBattle` — fires once, before any attacks
- `BeforeAttack` / `Attack` — fires as a pet is about to strike
- `Hurt` — pet took damage and survived
- `Faint` — this pet fainted
- `FriendFainted` — another friendly pet fainted
- `KnockOut` — this pet's attack caused an enemy faint
- `Summoned` — a pet entered an empty slot (bought or spawned)
- `LevelUp` — this pet leveled via combining
- `Sold` — this pet was sold in the shop phase
- `StartOfTurn` — fires when the player enters the shop phase
- `EndOfTurn` — fires when leaving the shop phase (less common, some pets use it)

Effects are the second half of each ability (deal damage, buff stats, summon a pet, give a temporary effect, gain gold, etc.) — worth keeping trigger and effect as separate data fields per pet, since many effects repeat across many pets with different triggers/targets/magnitudes.

## 6. Food

Food is bought in the shop and fed to one pet (occasionally all pets, for some foods). Effects fall into a few buckets: flat stat buffs (permanent), granting a status effect / shield-like ability, or attaching a whole new ability to the pet. Exact food roster is part of the data-population task below.

## 7. Mapping onto the policy-clash interface

Per `adding-an-env.md`, the required shape is a C rules core + thin CPython binding + `TwoPlayerEnv` Python adapter. Some specific decisions this game forces:

- **This is not naturally symmetric-simultaneous like Connect4 — but it fits the interface via the tron-duel pattern, not a variant base class.** As of the `tron-duel-v1` env landing, `base.py`'s actual invariant is: `StepResult.observations` is indexed by seat, and any seat with a non-`None` entry must supply an action next `step`; a seat with `None` doesn't act that tick. Turn-based envs (connect4) set exactly one slot; simultaneous envs (tron-duel, `actors_per_tick=2`) set both every tick. SAP's shop phase maps onto the simultaneous shape directly: both seats act every tick on their own hidden team (non-interacting, same as tron-duel's two cycles before their paths cross), for as many ticks as each needs (a seat that has ended its turn stops receiving observations while the other continues — same "seat not asked to act, argument ignored" rule the interface already states). One `step()` call then internally resolves the full battle deterministically and returns `done=True` with `observations=(None, None)` and `outcome` set. **This resolves the open question below about `base.py` — confirmed, no variant needed.**
- **Legal action mask** still applies to the shop phase: buy (if slot empty & can afford), sell (if pet present), combine (if two same-type pets present), reroll (if can afford), freeze/unfreeze, reposition, end-turn. Build the mask from real game-state constraints, not inferred.
- **Action space must collapse to one flat `num_actions` int.** `EnvSpec.num_actions` is a single integer (see connect4's 7 columns, tron-duel's 3 relative turns) — not multi-discrete. Buy(slot)/sell(slot)/combine/reroll/freeze(slot)/reposition(i,j)/end-turn all need a single flat action-index encoding, with the legality of each index carried entirely by the mask.
- **Fixed `obs_shape`.** Team slots + shop slots + gold + turn/tier-unlock state need a fixed-size float encoding, analogous to tron-duel's plane layout — pets/abilities need a numeric id embedding, not text.
- **An explicit step bound.** Real SAP has no in-game action-count limit inside one shop phase (§2 above) — for `max_episode_steps` that's unbounded unless the env caps it explicitly, the way tron-duel derives `83` from board geometry rather than hoping the step limit is never hit.
- **Stochasticity**: shop offers are randomly rolled — this env is **not** deterministic like Connect4, so per the interface's own rule, set `stochastic_dynamics=True` and derive the shop RNG entirely from the recorded seed. No wall-clock, no unseeded RNG anywhere in the core — `base.py`'s own docstring states this now too, not just this doc.
- **Observation symmetry**: encode each player's view as "my board state + my shop" — the opponent's team is legitimately hidden during the shop phase (this mirrors real SAP, where you don't see the opponent's team while building), so symmetric-observation doesn't mean identical-information here, it means identically-shaped encoding. Worth an explicit design note in the PR since it's a deviation from Connect4's fully-observed model.
- **Replay**: same principle as Connect4 — action list + seed should fully reconstruct an episode, including the shop RNG rolls. `replay()` is flat, `actors_per_tick` entries per tick, per the interface (not nested) — same format for both the shop ticks and however the battle-resolution tick(s) get recorded.
- Per the doc's own PufferLib section (independently reconfirmed as of their 4.0 branch): **don't reach for PufferLib for this env.** No ladder, no persistence, source-only distribution, and its selfplay-capable Ocean envs (chess/go/robocode/slimevolley) don't cover anything SAP-shaped — board games there are still fixed-bot outside that named list. PufferLib may still be the right tool later for the *training* side (self-play RL loop) even if policy-clash's C-core/adapter pattern is what actually defines and evaluates the env.

## 8. MVP scope (build-small-first)

Following the same philosophy as the fire-survival game: get a minimal but *complete* vertical slice working before expanding data:

1. Tier 1 pets only (roughly 10-11 pets), a small fixed food list, 5 team slots, single battle resolution — no multi-round meta yet.
2. Implement the C core (bitboard-style compact state if possible, similar spirit to Connect4's two-bitboard trick, though pet stats need more than 1 bit each so this will be a packed struct rather than a true bitboard).
3. Binding + adapter, get `reset`/`step`/`observe`/`legal`/`replay` working end to end against the Tier-1 slice.
4. Write the win-geometry / draw / illegal-action / observation-perspective / seed-determinism tests the doc calls out, adapted to this game (e.g. "two pets simultaneously fainting = draw" is this game's version of Connect4's tricky draw case).
5. Only then expand tiers, pets, food, and multi-round meta-progression.

**Status: steps 1–4 done.** [`docs/envs/sap-v1.md`](docs/envs/sap-v1.md) is
the full design spec (action/observation encoding, step-limit derivation,
battle-trigger ordering) and `policy-clash/envs/csrc/sap.h` (local
checkout, branch `sap-v1-env`, uncommitted) is the implementation —
registered as `sap-v1`, 19 passing tests. Next up is step 5.

**Training, added since:** `training/` has a working self-play PPO loop
against the policy-clash env directly (validated: 95%+ win rate vs. a
random baseline within 20 iterations), and `pufferlib/ocean/sap/` (local
checkout, branch `4.0`, uncommitted) is a native PufferLib port reusing
`sap.h` verbatim as its rules core — see both directories' READMEs.

## 9. Data population — handoff to Claude Code

This doc intentionally does **not** enumerate the full pet/food/toy database (450+ pets across multiple packs) — that's a bulk-extraction job better done with Claude Code's ability to systematically fetch and script against the wiki, rather than one-off searches here. Suggested approach for that session:

- Scrape structured data (name, tier, pack, base Attack/Health, trigger, effect text, level-up variants) into a JSON/CSV data file per category (`pets.json`, `foods.json`, `toys.json`) — separate from this design doc, which should stay stable rules reference while the data files evolve.
- Start with Tier 1–2 pets and the base food list to unblock the MVP above; expand tier-by-tier afterward.
- Paraphrase/normalize ability text into the trigger/effect schema from Section 5 rather than storing raw wiki prose, both for copyright reasons and because the C core needs structured effect data, not sentences, anyway.
- Respect the wiki's CC-BY-SA content license and don't scrape at a rate that hammers their servers.

## Open questions to resolve before/while implementing

- ~~Does `base.py`'s `TwoPlayerEnv` assume strictly alternating single-action turns?~~ **Resolved** (see §7): no — the tron-duel-v1 env proves the simultaneous-tick shape (`actors_per_tick=2`, a seat with `None` doesn't act) fits SAP's shop phase without a variant base class.
- How much of the multi-round meta (persistent life totals across many battles) is actually needed for a training/eval env, versus just single-battle win/loss/draw being sufficient signal? Still open, but not blocking — the MVP scope in §8 already defers it.
- ~~Exact stat caps and their named exceptions~~ **Resolved for Turtle Pack**: flat 50 cap, no named exceptions within this pack (see `data/turtle_pack/README.md`). Higher-cap pets like Behemoth are confirmed to live in later packs, out of MVP scope.
- Full ordering/tiebreak rule for same-trigger abilities — still open. Worth digging for the developer's clarified answer beyond the community consensus cited above, since this is exactly the kind of detail that causes silent divergence from the real game.
- **New, forced by the interface (not previously called out):** the flat `num_actions` encoding for buy/sell/combine/reroll/freeze/reposition/end-turn, and the fixed `obs_shape` encoding for team+shop+gold+turn state. Both need a concrete design pass before the C core can be written — see §7.
- **New:** `max_episode_steps` for the shop phase needs an explicit cap; unlike tron-duel's board-geometry bound, SAP's shop phase has no natural termination the rules enforce on their own (a player could buy/sell/reroll indefinitely within one turn).
