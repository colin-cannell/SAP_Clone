from __future__ import annotations

import numpy as np
import pytest

from policyclash_envs import Outcome, Termination, make
from policyclash_envs.base import Forkable
from policyclash_envs.sap2 import (
    ACT_BUY_FOOD_BASE,
    ACT_BUY_PET_BASE,
    ACT_COMBINE_BASE,
    ACT_FREEZE_FOOD_BASE,
    ACT_FREEZE_PET_BASE,
    ACT_REPOSITION_BASE,
    ACT_REROLL,
    ACT_SELL_BASE,
    FOOD_SLOTS,
    MAX_LEVEL,
    MAX_ROUNDS,
    MAX_SHOP_PETS,
    MAX_TICKS,
    NUM_ACTIONS,
    NUM_ALL_SPECIES,
    NUM_FOODS,
    NUM_PERKS,
    NUM_SHOP_SPECIES,
    OBS_FLOATS,
    PERK_HONEY,
    PERK_MEATBONE,
    PERK_NONE,
    SHOP_FOOD_SLOT_FLOATS,
    SHOP_PET_SLOT_FLOATS,
    STARTING_GOLD,
    STARTING_LIVES,
    TEAM_SLOT_FLOATS,
    TEAM_SLOTS,
    TROPHIES_TO_WIN,
)

HORSE_SPECIES = 6         # sap2.h's species ids, Tier-1 Pack1 roster
PIGEON_SPECIES = 10
DUCK_SPECIES = 4
HONEY_FOOD = 2            # SAP2_HONEY
BREAD_CRUMBS_FOOD = 3     # SAP2_BREAD_CRUMBS
MEATBONE_FOOD = 4         # SAP2_MEATBONE
MUFFIN_FOOD = 5           # SAP2_MUFFIN
PILL_FOOD = 6             # SAP2_PILL
APPLE2_FOOD = 7           # SAP2_APPLE2 ("Better Apple", Worm-only)
APPLE3_FOOD = 8           # SAP2_APPLE3 ("Best Apple", Worm-only)
APPLE_DISCOUNT_FOOD = 9   # SAP2_APPLE_DISCOUNT (Worm-only, 2g instead of 3g)

ENV_ID = "sap2-v1"

# Every offset below comes from the env, not from a copy of the layout:
# blocks have widened twice while matching the shipped game, and a stale
# constant here shows up as a nonsense test failure rather than as a
# layout error.
END_TURN = 0
BUY_PET_BASE = ACT_BUY_PET_BASE
SELL_BASE = ACT_SELL_BASE
COMBINE_BASE = ACT_COMBINE_BASE
REROLL = ACT_REROLL
REPOSITION_BASE = ACT_REPOSITION_BASE
BUY_FOOD_BASE = ACT_BUY_FOOD_BASE
FREEZE_PET_BASE = ACT_FREEZE_PET_BASE
FREEZE_FOOD_BASE = ACT_FREEZE_FOOD_BASE


def buy(shop_slot: int, position: int) -> int:
    """The real game's buy carries the position you dropped the pet on."""
    return BUY_PET_BASE + shop_slot * TEAM_SLOTS + position


def buy_food(food_slot: int, target: int) -> int:
    return BUY_FOOD_BASE + food_slot * TEAM_SLOTS + target


TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
# NUM_ALL_SPECIES-wide species one-hot, attack, health, 3 level one-hot,
# exp, NUM_PERKS-wide perk one-hot.
TEAM_SLOT_WIDTH = TEAM_SLOT_FLOATS
SHOP_PET_BASE = TEAM_BASE + TEAM_SLOTS * TEAM_SLOT_WIDTH
SHOP_PET_SLOT_WIDTH = SHOP_PET_SLOT_FLOATS
SHOP_FOOD_BASE = SHOP_PET_BASE + MAX_SHOP_PETS * SHOP_PET_SLOT_WIDTH
SHOP_FOOD_SLOT_WIDTH = SHOP_FOOD_SLOT_FLOATS

IGNORED = NUM_ACTIONS + 99


@pytest.fixture
def env():
    return make(ENV_ID)


# Within a team slot: species one-hot, then attack, health, level one-hot,
# exp, perk one-hot, in that order - see sap2.h's SAP2_TEAM_SLOT_FLOATS.
TEAM_ATK_OFF = NUM_ALL_SPECIES
TEAM_HP_OFF = TEAM_ATK_OFF + 1
TEAM_LEVEL_OFF = TEAM_HP_OFF + 1
TEAM_EXP_OFF = TEAM_LEVEL_OFF + MAX_LEVEL
TEAM_PERK_OFF = TEAM_EXP_OFF + 1

# Within a shop pet slot: species one-hot, hp bonus, frozen - see
# SAP2_SHOP_PET_SLOT_FLOATS. The species one-hot is NUM_SHOP_SPECIES+1
# wide (0 = empty).
SHOP_PET_HP_BONUS_OFF = NUM_SHOP_SPECIES + 1
SHOP_PET_FROZEN_OFF = SHOP_PET_HP_BONUS_OFF + 1

# Within a shop food slot: species one-hot (NUM_FOODS wide), frozen.
SHOP_FOOD_FROZEN_OFF = NUM_FOODS


def team_species(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_ALL_SPECIES]))


def team_attack(f: np.ndarray, slot: int) -> float:
    return f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + TEAM_ATK_OFF]


def team_health(f: np.ndarray, slot: int) -> float:
    return f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + TEAM_HP_OFF]


def team_level(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH + TEAM_LEVEL_OFF
    return int(np.argmax(f[base : base + MAX_LEVEL])) + 1


def team_exp(f: np.ndarray, slot: int) -> int:
    return int(f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + TEAM_EXP_OFF])


def team_perk(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH + TEAM_PERK_OFF
    return int(np.argmax(f[base : base + NUM_PERKS]))


def shop_pet_species(f: np.ndarray, slot: int) -> int:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_SHOP_SPECIES + 1]))


def shop_pet_frozen(f: np.ndarray, slot: int) -> bool:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return bool(f[base + SHOP_PET_FROZEN_OFF])


def shop_food_species(f: np.ndarray, slot: int) -> int:
    base = SHOP_FOOD_BASE + slot * SHOP_FOOD_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_FOODS]))


def shop_food_frozen(f: np.ndarray, slot: int) -> bool:
    base = SHOP_FOOD_BASE + slot * SHOP_FOOD_SLOT_WIDTH
    return bool(f[base + SHOP_FOOD_FROZEN_OFF])


def gold(f: np.ndarray) -> float:
    return f[0]


def lives(f: np.ndarray) -> float:
    return f[1]


def trophies(f: np.ndarray) -> float:
    return f[2]


def turn(f: np.ndarray) -> float:
    return f[3]


def end_both(env, result):
    """Play pure end-turns until the whole MATCH ends. For "just get
    through one round" use end_one_round instead - this one does not stop
    at a round boundary, since submitting END_TURN every tick for two
    idle seats has nothing to make it stop there."""
    while not result.done:
        a0 = END_TURN if result.observations[0] is not None else IGNORED
        a1 = END_TURN if result.observations[1] is not None else IGNORED
        result = env.step(a0, a1)
    return result


def end_one_round(env, result):
    """Pure end-turns until either the match ends or the round boundary is
    crossed (env.turn changes) - whichever comes first."""
    prev_turn = env.turn
    while not result.done and env.turn == prev_turn:
        a0 = END_TURN if result.observations[0] is not None else IGNORED
        a1 = END_TURN if result.observations[1] is not None else IGNORED
        result = env.step(a0, a1)
    return result


# --------------------------------------------------------------------------


def test_registered_with_expected_shape():
    spec = make(ENV_ID).spec
    assert spec.qualified_id == ENV_ID
    assert spec.obs_shape == (OBS_FLOATS,)
    assert spec.num_actions == NUM_ACTIONS
    assert spec.actors_per_tick == 2
    assert spec.stochastic_dynamics
    assert MAX_TICKS == MAX_ROUNDS * 20


def test_reset_state(env):
    result = env.reset(seed=0)
    assert not result.done
    assert env.turn == 1
    for obs in result.observations:
        assert obs.features.shape == (OBS_FLOATS,)
        assert gold(obs.features) == STARTING_GOLD
        assert lives(obs.features) == STARTING_LIVES
        assert trophies(obs.features) == 0
        assert turn(obs.features) == 1
        # turn 1: 3 pet slots x 5 team positions (an empty board takes a pet
        # anywhere, as the real game does) + end_turn + reroll + 3 freeze_pet
        # + 1 freeze_food = 21
        assert obs.legal_actions.sum() == 21
        assert not obs.legal_actions[FREEZE_PET_BASE + 3]  # slot 3 doesn't exist yet
        assert not obs.legal_actions[FREEZE_FOOD_BASE + 1]  # slot 1 doesn't exist yet


def test_a_bought_pet_goes_where_it_is_dropped(env):
    """The real game's buy carries a destination: `BoardEvents.PlayMinion`
    takes the point you dropped the pet on, and an empty board accepts one
    anywhere - holes included, since the board is never compacted."""
    result = env.reset(seed=0)
    result = env.step(buy(0, 3), END_TURN)
    f = result.observations[0].features
    assert team_species(f, 3) != 0
    assert all(team_species(f, s) == 0 for s in (0, 1, 2, 4))


def test_dropping_a_pet_on_an_occupied_slot_inserts_and_shifts(env):
    """Measured: dropping a different species onto an occupied position
    inserts it there and slides the neighbours - pets at 2,3 taking a drop
    on 2 end up at 3,4. It does not swap and it does not fail."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        if species[0] == species[1]:
            continue  # a same-species drop is a stack, not an insert
        result = probe.step(buy(0, 2), END_TURN)
        first = team_species(result.observations[0].features, 2)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(buy(1, 2), seat1)  # different species, same position
        f = result.observations[0].features
        assert team_species(f, 3) == first, "the sitting pet slid back"
        assert team_species(f, 2) == species[1]
        return
    pytest.fail("no seed in 200 gave two different species in the first two shop slots")


def test_buying_a_copy_onto_its_twin_stacks_in_one_action(env):
    """The shop stack is ONE action in the real game (PlayType.Stack), not
    buy-then-merge: exp goes up by one and the stats become the higher of
    each, +1."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        before = result.observations[0].features
        assert team_level(before, 0) == 1
        result = probe.step(buy(j, 0), seat1)  # dropped on its own twin
        f = result.observations[0].features
        assert team_species(f, 0) == species[i]
        assert all(team_species(f, s) == 0 for s in range(1, 5)), "one pet, not two"
        assert team_attack(f, 0) == team_attack(before, 0) + 1
        assert team_health(f, 0) == team_health(before, 0) + 1
        return
    pytest.fail("no seed in 200 offered a duplicate species in the turn-1 shop")


def test_shop_grows_with_tier_not_turn(env):
    # Measured from the shipped build (policy-clash-re-tools' sap/shop.py): the shop
    # grows on TIER, and tiers unlock on turns 3/5/7/9/11, so the pet slots
    # go 3 (turns 1-4) -> 4 (turns 5-8) -> 5 (turns 9+) and the food slots
    # go 1 -> 2 at turn 5. The old 4-slots-on-turn-3 schedule was folklore.
    result = env.reset(seed=0)
    for expected_turn in (2, 3, 4):
        result = end_one_round(env, result)
        assert not result.done
        assert env.turn == expected_turn
        assert result.observations[0].legal_actions[buy(2, 0)]
        assert not result.observations[0].legal_actions[buy(3, 0)]
        assert not result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]

    result = end_one_round(env, result)  # -> turn 5, tier 3: 4 pet / 2 food
    assert env.turn == 5
    assert result.observations[0].legal_actions[buy(3, 0)]
    assert not result.observations[0].legal_actions[buy(4, 0)]
    assert result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]

    for expected_turn in (6, 7, 8, 9):
        result = end_one_round(env, result)
        assert env.turn == expected_turn
    assert env.turn == 9  # tier 5: the shop reaches its full 5 pet slots
    assert result.observations[0].legal_actions[buy(4, 0)]


def test_gold_resets_every_round_does_not_carry(env):
    result = env.reset(seed=0)
    result = env.step(REROLL, END_TURN)  # seat0 spends 1g -> 9g
    assert gold(result.observations[0].features) == STARTING_GOLD - 1
    result = end_one_round(env, result)  # round resolves, next round starts
    assert gold(result.observations[0].features) == STARTING_GOLD  # not 9, not accumulated


def test_levelling_follows_the_shipped_exp_table(env):
    """Measured from the shipped build (policy-clash-re-tools' sap/difftest_shop.py):
    a copy is worth +1 exp and the higher of each stat +1, and the level
    thresholds are exp 0/2/5 - so an Ant walks 2/2 L1, 3/3 L1, 4/4 L2 and
    only reaches L3 on the sixth copy. sap2 used to level up on the second
    copy, which made levels roughly three times too cheap."""
    result = env.reset(seed=0)
    # Find a seed whose turn-1 shop offers the same species twice, so one
    # round is enough to observe a stack.
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)
        result = probe.step(buy(j, 1), IGNORED if result.observations[1] is None else END_TURN)
        f = result.observations[0].features
        base = TEAM_BASE
        assert result.observations[0].legal_actions[COMBINE_BASE + 0]  # slots 0,1 stack
        result = probe.step(COMBINE_BASE + 0, IGNORED if result.observations[1] is None else END_TURN)
        f = result.observations[0].features
        level_one_hot = f[base + TEAM_LEVEL_OFF : base + TEAM_LEVEL_OFF + MAX_LEVEL]
        assert int(np.argmax(level_one_hot)) == 0, "one stack is exp 1, still level 1"
        assert team_exp(f, 0) == 1, "the exp counter is observable, not just the level"
        return
    pytest.fail("no seed in 200 offered a duplicate species in the turn-1 shop")


def test_horses_buff_counts_in_this_rounds_battle_and_expires_next_turn(env):
    """Measured from the shipped build via policy-clash-re-tools: Horse's
    ability effect carries Duration = Temp(1) - the only one in this
    roster, Ant/Otter/Beaver/Duck/Fish are all Perm(0) - and the deadline
    Temp(1) names is the start of the NEXT TURN, not the end of battle.
    A Horse plus a freshly bought Ant showed Ant 3/2 on turn 1, including
    that turn's battle, and 2/2 from turn 2 on.

    Both halves are checked. The battle half compares two plays that
    differ in nothing but the buff: buying the Horse first buffs the pet
    dropped beside it, buying it second does not, and both plays end the
    shop phase with the same two bodies in the same two positions. The
    buffed pet is picked to be neither Otter nor Fish - the only pets
    whose on-play/level-up draw from the seat RNG - so the two plays also
    consume the RNG identically. A buff that did not reach the battle
    would have to give both plays the same round result.
    """
    for seed in range(200):
        f = make(ENV_ID).reset(seed=seed).observations[0].features
        shop = [shop_pet_species(f, s) for s in range(3)]
        horse = next((s for s in range(3) if shop[s] == HORSE_SPECIES), None)
        # Not Otter (8) and not Fish (5): those two draw from the seat RNG
        # when they are played, which would make the two plays below
        # differ in more than the buff.
        other = next((s for s in range(3) if shop[s] not in (HORSE_SPECIES, 5, 8)), None)
        if horse is None or other is None:
            continue

        plays = {}
        for name, first, second in (
            ("buffed", (horse, 1), (other, 0)),  # Horse first: the next pet is summoned beside it
            ("plain", (other, 0), (horse, 1)),   # Horse last: nobody is summoned after it
        ):
            probe = make(ENV_ID)
            result = probe.reset(seed=seed)
            # Seat 1 buys the same two pets in both plays, so seat 0's
            # ordering is the only thing that differs.
            result = probe.step(buy(*first), buy(0, 0))
            seat1 = IGNORED if result.observations[1] is None else buy(1, 1)
            result = probe.step(buy(*second), seat1)
            plays[name] = (result.observations[0].features, end_one_round(probe, result))

        buffed_obs, buffed_result = plays["buffed"]
        plain_obs, plain_result = plays["plain"]
        assert team_species(buffed_obs, 0) == team_species(plain_obs, 0) == shop[other]
        assert team_species(buffed_obs, 1) == team_species(plain_obs, 1) == HORSE_SPECIES
        assert team_attack(buffed_obs, 0) == team_attack(plain_obs, 0) + 1  # Horse is level 1
        assert team_health(buffed_obs, 0) == team_health(plain_obs, 0)  # attack only

        after = buffed_result.observations[0].features
        assert team_species(after, 0) == shop[other], "the pet is still there"
        assert team_attack(after, 0) == team_attack(plain_obs, 0), "the buff expired"

        plain_after = plain_result.observations[0].features
        if (trophies(after), lives(after)) == (trophies(plain_after), lives(plain_after)):
            continue  # this seed's battle was not decided by one point of attack
        return
    pytest.fail("no seed in 200 gave a Horse plus a battle the buff decided")


def test_a_stack_keeps_the_honey_perk_from_the_absorbed_copy(env):
    """Honey changes no stat - it leaves a perk on the pet, which summons
    a 1/1 Bee when that pet faints - and the perk survives a merge from
    either copy: feed Honey to one of two twins, drag it onto the other,
    and the survivor is the one carrying the Bee. The observation shows
    the perk as a one-hot, so this reads it back from what the agent
    actually sees."""
    for seed in range(400):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        if shop_food_species(f, 0) != HONEY_FOOD:
            continue
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)  # 3g
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(buy(j, 1), seat1)  # 6g
        result = probe.step(buy_food(0, 1), seat1)  # 9g, Honey onto the second copy
        f = result.observations[0].features
        assert team_perk(f, 0) == PERK_NONE
        assert team_perk(f, 1) == PERK_HONEY
        assert team_attack(f, 1) == team_attack(f, 0)  # Honey is not an Apple
        assert team_health(f, 1) == team_health(f, 0)

        result = probe.step(COMBINE_BASE + 0, seat1)  # pair (0,1): 1 is absorbed into 0
        f = result.observations[0].features
        assert team_species(f, 0) == species[i]
        assert team_species(f, 1) == 0, "one body, not two"
        assert team_exp(f, 0) == 1
        assert team_perk(f, 0) == PERK_HONEY, "the perk came with the absorbed copy"
        return
    pytest.fail("no seed in 400 offered a duplicate species and Honey in the same turn-1 shop")


def test_a_stack_keeps_a_temporary_buff_from_either_copy(env):
    """Measured against `IntegerStat.Permanent`/`.Temporary` in the shipped
    build: a merge stacks the permanent components (higher of each, +1) and
    takes the HIGHER of the two temporary components with no +1 - so the
    buff survives whichever copy carried it. sap2 used to keep only the
    survivor's, dropping Horse's buff when the absorbed copy was the buffed
    one. Here the absorbed copy is the buffed one: the Horse is bought
    last, so only the twin bought after it is buffed."""
    for seed in range(400):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        horse = next((s for s in range(3) if species[s] == HORSE_SPECIES), None)
        pair = next(
            (
                (i, j)
                for i in range(3)
                for j in range(i + 1, 3)
                if species[i] == species[j] and species[i] != HORSE_SPECIES
            ),
            None,
        )
        if horse is None or pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)  # the unbuffed twin
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(buy(horse, 4), seat1)
        result = probe.step(buy(j, 1), seat1)  # bought with the Horse present
        f = result.observations[0].features
        buffed = team_attack(f, 1)
        plain = team_attack(f, 0)
        assert buffed == plain + 1, "Horse buffed the pet bought after it"

        result = probe.step(COMBINE_BASE + 0, seat1)  # absorbs slot 1 into slot 0
        f = result.observations[0].features
        # permanent max(2,2)+1 = 3, plus the absorbed copy's temporary +1.
        assert team_attack(f, 0) == plain + 2
        # And it is still temporary: it goes away when the next turn starts.
        result = end_one_round(probe, result)
        if result.observations[0] is not None:
            assert team_attack(result.observations[0].features, 0) == plain + 1
        return
    pytest.fail("no seed in 400 offered a Horse and a duplicate pair in the turn-1 shop")


def test_pigeon_stocks_free_bread_crumbs_without_evicting_food(env):
    """Measured: selling a Pigeon prepends `level` free Bread Crumbs to the
    food shop and leaves the rolled food where it is (pushed right), which
    is why the food array is wider than the rolled capacity - a roll only
    ever fills 1 or 2 slots."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        pigeon_slot = next(
            (s for s in range(3) if shop_pet_species(f, s) == PIGEON_SPECIES), None
        )
        if pigeon_slot is None:
            continue
        food_before = shop_food_species(f, 0)
        result = probe.step(buy(pigeon_slot, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(SELL_BASE + 0, seat1)
        f = result.observations[0].features
        assert shop_food_species(f, 0) == BREAD_CRUMBS_FOOD
        assert shop_food_species(f, 1) == food_before  # the rolled food survived
        assert result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]
        return
    pytest.fail("no seed in 200 offered a Pigeon in the turn-1 shop")


def test_pigeon_crumbs_are_unfrozen_and_a_roll_clears_them(env):
    """Measured: the crumbs a Pigeon stocks come in UNFROZEN, so the next
    roll clears them along with any other unfrozen stock past the rolled
    capacity. A reading that said otherwise on a turn>=2 board turned out
    to be the oracle sitting with BoardModel.TurnOver still set - see
    docs/envs/sap-v2.md."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        pigeon = next((s for s in range(3) if shop_pet_species(f, s) == PIGEON_SPECIES), None)
        if pigeon is None:
            continue
        result = probe.step(buy(pigeon, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(SELL_BASE + 0, seat1)
        f = result.observations[0].features
        assert shop_food_species(f, 0) == BREAD_CRUMBS_FOOD
        assert not shop_food_frozen(f, 0), "a stocked crumb is not frozen"
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(REROLL, seat1)
        f = result.observations[0].features
        # Unfrozen, so the roll replaced it and cleared the stock past the
        # turn-1 capacity of one.
        assert shop_food_species(f, 0) != BREAD_CRUMBS_FOOD
        assert shop_food_species(f, 1) == 0
        return
    pytest.fail("no seed in 200 offered a Pigeon in the turn-1 shop")


def test_the_food_shop_is_wide_enough_for_a_team_of_pigeons(env):
    """The array is sized for the worst case the real game allows - a full
    team of level-3 Pigeons sold in one phase - because measured against
    the shipped build nothing is evicted and every slot stays buyable."""
    from policyclash_envs.sap2 import MAX_LEVEL as _lvl

    assert FOOD_SLOTS == 2 + TEAM_SLOTS * _lvl
    # And the action space reaches all of them.
    assert ACT_FREEZE_PET_BASE == ACT_BUY_FOOD_BASE + FOOD_SLOTS * TEAM_SLOTS
    assert NUM_ACTIONS == ACT_FREEZE_FOOD_BASE + FOOD_SLOTS


def test_a_frozen_shop_pet_slides_to_the_leftmost_slot(env):
    """Measured: a roll refills around frozen items and they slide left -
    freezing slot 1 of three and rerolling leaves the frozen pet at slot 0.
    The offers would be the same either way, but the slot decides which
    action index buys it, so the ordering is behaviour."""
    result = env.reset(seed=0)
    f = result.observations[0].features
    frozen_species = shop_pet_species(f, 1)
    result = env.step(FREEZE_PET_BASE + 1, END_TURN)
    assert shop_pet_frozen(result.observations[0].features, 1)
    seat1 = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(REROLL, seat1)
    f = result.observations[0].features
    assert shop_pet_species(f, 0) == frozen_species
    assert shop_pet_frozen(f, 0)
    assert not shop_pet_frozen(f, 1)


def test_a_lost_battle_costs_a_life_not_the_pet(env):
    """The corrected behavior: fainting in battle is not permanent. Search
    a small seed range for a decisive first round (loser found by their
    lives dropping), then confirm the loser's team is completely
    unchanged going into round 2 - it lost life, not pets."""
    for seed in range(100):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = probe.step(buy(0, 0), buy(0, 0))
        before = [
            [team_species(result.observations[s].features, t) for t in range(5)] for s in range(2)
        ]
        result = probe.step(END_TURN, END_TURN)
        if result.done:
            continue
        after_lives = [lives(result.observations[s].features) for s in range(2)]
        if after_lives == [STARTING_LIVES, STARTING_LIVES]:
            continue  # draw, try another seed
        loser = 0 if after_lives[0] < STARTING_LIVES else 1
        after = [team_species(result.observations[loser].features, t) for t in range(5)]
        assert after_lives[loser] == STARTING_LIVES - 1
        assert after == before[loser], "loser's team must be unchanged - fainting isn't permanent"
        return
    pytest.fail("no decisive first round found in 100 seeds")


def test_freeze_persists_across_reroll(env):
    result = env.reset(seed=0)
    sp0 = shop_pet_species(result.observations[0].features, 0)
    result = env.step(FREEZE_PET_BASE + 0, END_TURN)
    assert shop_pet_frozen(result.observations[0].features, 0)
    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(REROLL, seat1_action)
    f0 = result.observations[0].features
    assert shop_pet_species(f0, 0) == sp0  # frozen slot untouched by the reroll
    assert shop_pet_frozen(f0, 0)  # stays frozen until explicitly toggled or bought


def test_freeze_persists_into_next_round(env):
    result = env.reset(seed=0)
    sp0 = shop_pet_species(result.observations[0].features, 0)
    result = env.step(FREEZE_PET_BASE + 0, END_TURN)
    result = end_one_round(env, result)
    f0 = result.observations[0].features
    assert shop_pet_species(f0, 0) == sp0
    assert shop_pet_frozen(f0, 0)


def test_win_on_ten_trophies():
    # Cheapest deterministic route to a decisive match: buy one pet on
    # turn 1 for seat 0 only, then pure end-turns forever. Seat 1 stays
    # empty the whole match, so seat 0's single Tier-1 pet wins every
    # round on its own - no need to keep buying - racking up 10 trophies
    # (and never losing a life) well inside MAX_ROUNDS.
    env = make(ENV_ID)
    result = env.reset(seed=0)
    result = env.step(buy(0, 0), END_TURN)
    result = end_both(env, result)
    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.NATURAL


def test_illegal_action_forfeits(env):
    env.reset(seed=0)
    result = env.step(NUM_ACTIONS, END_TURN)
    assert result.done
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_budget_forces_end_after_twenty_actions_per_round(env):
    # Both seats take the same 20 actions (buy, then 19 repositions) and
    # never voluntarily END_TURN, so both hit the budget on the same,
    # 20th tick - round 1 resolves right there (mirrored actions -> a
    # draw), landing on round 2's fresh turn rather than leaving seat 0
    # mid-round-1 with seat 1 already idle, which is what let round 1
    # resolve earlier than a naive "20 actions should end this seat" check
    # expects - budgets reset every round, so hitting one is a round
    # event, not necessarily an end-of-episode one.
    result = env.reset(seed=0)
    result = env.step(buy(0, 0), buy(0, 0))
    for _ in range(19):
        result = env.step(REPOSITION_BASE + 0, REPOSITION_BASE + 0)
        if result.done:
            break
    assert result.done or env.turn == 2


def test_step_limit_is_reachable_and_uses_documented_tiebreak(env):
    # Both seats do nothing, every round, forever -> MAX_ROUNDS reached
    # with 0-0 trophies and 5-5 lives -> DRAW_STEP_LIMIT.
    result = env.reset(seed=0)
    result = end_both(env, result)
    assert env.turn == MAX_ROUNDS
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.STEP_LIMIT


def test_deterministic_given_same_seed():
    def play(seed):
        e = make(ENV_ID)
        result = e.reset(seed=seed)
        result = e.step(buy(0, 0), buy(0, 0))
        result = end_both(e, result)
        result = end_both(e, result)
        return e.replay(), (result.outcome, result.done)

    a = play(seed=42)
    b = play(seed=42)
    assert a == b


def test_replay_is_flat_two_per_tick(env):
    env.reset(seed=0)
    r = env.step(END_TURN, REROLL)
    replay = env.replay()
    assert replay == [END_TURN, REROLL]
    assert len(replay) == 2


def test_env_advertises_the_forkable_capability(env):
    # How a runner decides whether a search-based submission can be served
    # at all. sap2 opts in; Forkable is not part of TwoPlayerEnv, so this is
    # a real capability check and not a tautology about the base interface.
    assert isinstance(env, Forkable)


def test_clone_does_not_affect_the_original(env):
    result = env.reset(seed=7)
    result = end_one_round(env, result)
    turn_at_fork = env.turn

    fork = env.clone()
    end_both(fork, fork.step(END_TURN, END_TURN))

    # The fork played the match out to its end. The original is still sitting
    # exactly where it was forked, which is the whole point of the capability.
    assert env.turn == turn_at_fork
    assert not result.done


def test_clone_continues_the_rng_stream_rather_than_restarting_it(env):
    # A clone that re-seeded, or that shared shop/battle RNG words with its
    # source, would make a search's rollouts disagree with what the real match
    # goes on to do - the failure that makes forking worthless. Same state and
    # same actions must therefore produce the same match.
    result = env.reset(seed=11)
    result = end_one_round(env, result)

    fork = env.clone()
    fork_result = end_both(fork, fork.step(END_TURN, END_TURN))
    real_result = end_both(env, env.step(END_TURN, END_TURN))

    assert fork_result.outcome == real_result.outcome
    assert fork_result.termination == real_result.termination
    assert fork.replay() == env.replay()
    assert fork.turn == env.turn


# --------------------------------------------------------------------------
# Tier 2 (species 11-20, foods 4-9). Ground truth for all of it came out of
# policy-clash-re-tools directly (roster.py's minion/spell dump - not a wiki:
# this build's Tier-2 foods are named MeatBone/Muffin/Pill, not the
# "Cupcake"/"Sleeping Pill" an older community snapshot would suggest, and
# Worm's own ability stocks a *better* Apple rather than a "friend eats an
# apple" trigger - see docs/envs/sap-v2.md). Two abilities are documented
# no-ops (Spider's Faint summon, blocked on a Tier-3 roster that doesn't
# exist yet; Hedgehog's Faint damage, blocked on a general recursive
# faint-resolution pass sap2.h doesn't have yet) - see
# sap2_battle_resolve_faint's own comments, not retested here.


def _reroll_until(env, result, found):
    """Rerolls seat 0's shop (seat 1 mirrors it, so both stay in lock-step)
    until `found(features)` is true, advancing to the next round for fresh
    gold whenever this one's is spent. Bounded so a real regression fails
    the test instead of hanging."""
    for _ in range(400):
        f = result.observations[0].features
        if found(f):
            return result
        if result.observations[0].legal_actions[REROLL]:
            a1 = REROLL if result.observations[1] is not None else IGNORED
            result = env.step(REROLL, a1)
        else:
            result = end_one_round(env, result)
    pytest.fail("gave up searching the shop before the target condition held")


def test_tier2_species_gate_on_turn_three_not_before(env):
    """Measured via policy-clash-re-tools: species roll uniformly over
    every species at or below the CURRENT tier, and Tier 2 unlocks at
    turn 3 (same schedule the shop-size gate already uses). Turn 1-2
    shops across many seeds should never offer a Tier-2 species (id > 10);
    turn 3 on, they should - checked statistically since the roll is
    random either way."""
    for seed in range(60):
        f = make(ENV_ID).reset(seed=seed).observations[0].features
        for s in range(3):
            assert shop_pet_species(f, s) <= 10, "Tier 2 leaked into a turn-1 shop"

    result = env.reset(seed=0)
    result = end_one_round(env, result)
    result = end_one_round(env, result)
    assert env.turn == 3

    result = _reroll_until(
        env, result, lambda f: any(shop_pet_species(f, s) > 10 for s in range(3))
    )
    assert env.turn == 3, "should not have needed to spend a whole round hunting for this"


def test_meatbone_gives_a_perk_without_changing_displayed_stats(env):
    """Measured via policy-clash-re-tools' battle.py (a MeatBone-perked 2/2
    Ant vs. a 50-health dummy dealt 5 damage while the pre-battle grid
    still read "2/2"): the +3 is hidden bonus damage, not a stat change.
    This only checks the shop-phase half - the perk lands, and the card's
    attack/health are untouched - the battle-phase half is the oracle
    measurement above, transcribed directly into sap2_battle's exchange
    loop (see SAP2_MEATBONE_BONUS_DAMAGE)."""
    result = env.reset(seed=0)
    # Get any pet onto the team first, from the turn-1 shop.
    result = env.step(buy(0, 0), IGNORED if result.observations[1] is None else END_TURN)

    result = _reroll_until(
        env,
        result,
        lambda f: any(shop_food_species(f, s) == MEATBONE_FOOD for s in range(FOOD_SLOTS)),
    )
    f = result.observations[0].features
    slot = next(s for s in range(FOOD_SLOTS) if shop_food_species(f, s) == MEATBONE_FOOD)
    atk, hp = team_attack(f, 0), team_health(f, 0)

    result = env.step(buy_food(slot, 0), IGNORED if result.observations[1] is None else REROLL)
    f = result.observations[0].features
    assert team_perk(f, 0) == PERK_MEATBONE
    assert team_attack(f, 0) == atk, "Meat Bone must not touch the displayed attack"
    assert team_health(f, 0) == hp


def test_pill_destroys_the_target_pet_with_no_sell_effect(env):
    """Measured via policy-clash-re-tools: Sleeping Pill's effect is
    EffectDestroyMinion - the pet is just gone, no sell value and no
    Sell-triggered ability. Target a Duck specifically: Duck's Sell effect
    buffs every shop pet's hp_bonus, which Pill must NOT trigger."""
    result = env.reset(seed=0)
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        duck_slot = next((s for s in range(3) if shop_pet_species(f, s) == DUCK_SPECIES), None)
        if duck_slot is None:
            continue
        result = probe.step(buy(duck_slot, 0), IGNORED if result.observations[1] is None else END_TURN)
        env_, result = probe, result
        break
    else:
        pytest.fail("no seed in 200 offered a Duck in the turn-1 shop")

    gold_before = gold(result.observations[0].features)
    result = _reroll_until(
        env_,
        result,
        lambda f: any(shop_food_species(f, s) == PILL_FOOD for s in range(FOOD_SLOTS)),
    )
    f = result.observations[0].features
    slot = next(s for s in range(FOOD_SLOTS) if shop_food_species(f, s) == PILL_FOOD)
    shop_hp_before = [f[SHOP_PET_BASE + k * SHOP_PET_SLOT_WIDTH + SHOP_PET_HP_BONUS_OFF] for k in range(MAX_SHOP_PETS)]
    gold_before_pill = gold(f)

    result = env_.step(buy_food(slot, 0), IGNORED if result.observations[1] is None else END_TURN)
    f = result.observations[0].features
    assert team_species(f, 0) == 0, "the Duck should be gone"
    assert gold(f) == gold_before_pill - 1, "Pill costs 1 gold, and nothing else changes it"
    shop_hp_after = [f[SHOP_PET_BASE + k * SHOP_PET_SLOT_WIDTH + SHOP_PET_HP_BONUS_OFF] for k in range(MAX_SHOP_PETS)]
    assert shop_hp_after == shop_hp_before, "Duck's Sell effect must not have fired"
