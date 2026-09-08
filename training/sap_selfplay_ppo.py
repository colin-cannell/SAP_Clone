#!/usr/bin/env python3
"""Self-play PPO for `sap-v1`, no PufferLib.

Why this exists instead of a PufferLib port: PufferLib 4.0 has no
pure-Python env path (checked against the `4.0` branch directly) — every
env is a native C module statically compiled into `pufferlib/_C.so`, so
training on `sap-v1` there would mean a second, separately-maintained
implementation of the shop/battle rules against PufferLib's `vecenv.h`
contract, duplicating `policy-clash/envs/csrc/sap.h`. This script instead
drives the *existing*, already-tested `Sap` env directly — zero new rules
code — to validate the training signal end-to-end first. A native PufferLib
port remains the natural next step if this env's throughput (not the rules)
turns out to be the actual bottleneck; see training/README.md.

One network plays both seats (self-play): SAP's shop-phase observation is
already from the acting seat's own perspective with no `player` field (see
policyclash_envs/base.py), so there is nothing seat-specific to condition
the policy on beyond the observation it's handed.

Reward model: sparse and terminal. Every shop-phase step gets 0 reward.
A seat's own trajectory ends at its own last action (END_TURN, or the tick
its action budget forces it to stop) — not at the whole episode's last
tick, since after that point the seat makes no more decisions that affect
the outcome. The env's eventual Outcome, mapped to +1 win / -1 loss / 0
draw from that seat's perspective, is credited entirely to that seat's own
final step. This is the standard treatment for agents that finish acting
at different times within one episode: GAE over each seat's own trajectory
needs no bootstrap value past its own last action, because nothing it does
after matters to the reward it already fully explains.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# The policy-clash checkout (sibling directory) has policyclash_envs
# installed editable into its own venv - run this script with that venv's
# python (see training/README.md) rather than adding sys.path games here.
from policyclash_envs import make
from policyclash_envs.base import Outcome, Termination
from policyclash_envs.sap import OBS_FLOATS, NUM_ACTIONS, STARTING_GOLD

ENV_ID = "sap-v1"
DEVICE = torch.device("cpu")  # this network and batch size have no business on a GPU

# --------------------------------------------------------------------------
# Observation scaling.
#
# The raw observation mixes 0/1 one-hot flags with small integer counts
# (gold up to 10, attack/health up to 50, Duck's shop hp-bonus up to a few).
# Feeding raw integer magnitudes next to 0/1 flags into a freshly-initialized
# network makes the large-magnitude fields dominate early gradients for no
# reason - this rescales the count fields into a similar range as the
# one-hots, once, rather than asking the network to learn the rescaling.
#
# Layout mirrors sap.h / docs/envs/sap-v1.md exactly (also re-derived, for
# the same reason, in envs/tests/test_sap.py): gold(1), 5x[species
# onehot(13) atk(1) hp(1) level onehot(3) honey(1)], 3x[species onehot(11)
# hp_bonus(1)], food onehot(4).
TEAM_SLOTS = 5
SHOP_PET_SLOTS = 3
TEAM_SLOT_WIDTH = 19
SHOP_PET_SLOT_WIDTH = 12
TEAM_BASE = 1
SHOP_PET_BASE = TEAM_BASE + TEAM_SLOTS * TEAM_SLOT_WIDTH
FOOD_BASE = SHOP_PET_BASE + SHOP_PET_SLOTS * SHOP_PET_SLOT_WIDTH
assert FOOD_BASE + 4 == OBS_FLOATS, "observation layout drifted from sap.h"


def _build_obs_scale() -> np.ndarray:
    scale = np.ones(OBS_FLOATS, dtype=np.float32)
    scale[0] = 1.0 / STARTING_GOLD  # gold
    for slot in range(TEAM_SLOTS):
        base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
        scale[base + 13] = 1.0 / 50.0  # attack
        scale[base + 14] = 1.0 / 50.0  # health
    for slot in range(SHOP_PET_SLOTS):
        base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
        scale[base + 11] = 1.0 / 10.0  # Duck's hp bonus, generously bounded
    return scale


OBS_SCALE = torch.from_numpy(_build_obs_scale())


# --------------------------------------------------------------------------
# Policy


class ActorCritic(nn.Module):
    def __init__(self, obs_size: int = OBS_FLOATS, num_actions: int = NUM_ACTIONS, hidden: int = 128):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(obs_size, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.actor = nn.Linear(hidden, num_actions)
        self.critic = nn.Linear(hidden, 1)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(obs * OBS_SCALE)
        return self.actor(h), self.critic(h).squeeze(-1)

    @torch.no_grad()
    def act(self, obs: np.ndarray, mask: np.ndarray) -> tuple[int, float, float]:
        """Sample one action for one (obs, legal mask) pair. Returns
        (action, log-prob of that action, value estimate)."""
        # obs is a read-only view over the env's own buffer (by design - see
        # policyclash_envs/sap.py) - torch.tensor copies rather than wraps it,
        # which is what from_numpy's "non-writable array" warning is asking for.
        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
        logits, value = self.forward(obs_t)
        logits = logits.masked_fill(~torch.tensor(mask).unsqueeze(0), float("-inf"))
        dist = torch.distributions.Categorical(logits=logits)
        action = dist.sample()
        return int(action.item()), float(dist.log_prob(action).item()), float(value.item())


# --------------------------------------------------------------------------
# Rollout collection


@dataclass
class Trajectory:
    """One seat's own sequence of decisions within one episode. Ends at
    that seat's own last action, not the episode's last tick - see the
    module docstring's reward-model note."""

    obs: list[np.ndarray] = field(default_factory=list)
    mask: list[np.ndarray] = field(default_factory=list)
    action: list[int] = field(default_factory=list)
    logprob: list[float] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    terminal_reward: float = 0.0


def _outcome_reward(outcome: Outcome, seat: int) -> float:
    if outcome is Outcome.DRAW:
        return 0.0
    won = (outcome is Outcome.PLAYER_0 and seat == 0) or (outcome is Outcome.PLAYER_1 and seat == 1)
    return 1.0 if won else -1.0


def play_episode(policy: ActorCritic, seed: int) -> tuple[list[Trajectory], Outcome, Termination, int]:
    env = make(ENV_ID)
    result = env.reset(seed=seed)
    trajectories = [Trajectory(), Trajectory()]
    ticks = 0

    while not result.done:
        actions = [0, 0]
        for seat in range(2):
            obs = result.observations[seat]
            if obs is None:
                continue
            action, logprob, value = policy.act(obs.features, obs.legal_actions)
            actions[seat] = action
            traj = trajectories[seat]
            traj.obs.append(obs.features)
            traj.mask.append(obs.legal_actions)
            traj.action.append(action)
            traj.logprob.append(logprob)
            traj.value.append(value)
        result = env.step(actions[0], actions[1])
        ticks += 1

    for seat in range(2):
        trajectories[seat].terminal_reward = _outcome_reward(result.outcome, seat)
    return trajectories, result.outcome, result.termination, ticks


# --------------------------------------------------------------------------
# GAE + PPO update


def compute_gae(traj: Trajectory, gamma: float, gae_lambda: float) -> tuple[np.ndarray, np.ndarray]:
    """Advantages and returns for one trajectory. Reward is 0 at every step
    but the last (terminal_reward there), and the last step needs no
    bootstrap - the seat's own decisions are done, see the module
    docstring."""
    T = len(traj.value)
    rewards = np.zeros(T, dtype=np.float32)
    if T > 0:
        rewards[-1] = traj.terminal_reward
    values = np.asarray(traj.value, dtype=np.float32)
    advantages = np.zeros(T, dtype=np.float32)
    gae = 0.0
    for t in reversed(range(T)):
        next_value = 0.0 if t == T - 1 else values[t + 1]  # last step bootstraps 0, not values[T]
        delta = rewards[t] + gamma * next_value - values[t]
        gae = delta + gamma * gae_lambda * gae
        advantages[t] = gae
    returns = advantages + values
    return advantages, returns


def ppo_update(
    policy: ActorCritic,
    optimizer: torch.optim.Optimizer,
    trajectories: list[Trajectory],
    gamma: float,
    gae_lambda: float,
    clip_eps: float,
    value_coef: float,
    entropy_coef: float,
    epochs: int,
    minibatch_size: int,
) -> dict[str, float]:
    obs_list, mask_list, action_list, old_logprob_list, advantage_list, return_list = [], [], [], [], [], []
    for traj in trajectories:
        if not traj.obs:
            continue
        advantages, returns = compute_gae(traj, gamma, gae_lambda)
        obs_list.extend(traj.obs)
        mask_list.extend(traj.mask)
        action_list.extend(traj.action)
        old_logprob_list.extend(traj.logprob)
        advantage_list.extend(advantages)
        return_list.extend(returns)

    n = len(obs_list)
    if n == 0:
        return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "batch_size": 0}

    obs = torch.from_numpy(np.stack(obs_list))
    mask = torch.from_numpy(np.stack(mask_list))
    actions = torch.tensor(action_list, dtype=torch.long)
    old_logprobs = torch.tensor(old_logprob_list, dtype=torch.float32)
    advantages = torch.tensor(np.asarray(advantage_list), dtype=torch.float32)
    returns = torch.tensor(np.asarray(return_list), dtype=torch.float32)
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    stats = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "batch_size": n}
    num_updates = 0
    for _ in range(epochs):
        perm = torch.randperm(n)
        for start in range(0, n, minibatch_size):
            idx = perm[start : start + minibatch_size]
            logits, values = policy(obs[idx])
            logits = logits.masked_fill(~mask[idx], float("-inf"))
            dist = torch.distributions.Categorical(logits=logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])

            surr1 = ratio * advantages[idx]
            surr2 = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * advantages[idx]
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = F.mse_loss(values, returns[idx])
            entropy = dist.entropy().mean()
            loss = policy_loss + value_coef * value_loss - entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimizer.step()

            stats["policy_loss"] += float(policy_loss.item())
            stats["value_loss"] += float(value_loss.item())
            stats["entropy"] += float(entropy.item())
            num_updates += 1

    for key in ("policy_loss", "value_loss", "entropy"):
        stats[key] /= max(num_updates, 1)
    return stats


# --------------------------------------------------------------------------
# Evaluation against a uniform-random legal-action baseline.
#
# Self-play win rate is ~50% by construction (one network plays both sides)
# and says nothing about absolute progress. This does: a fixed, un-trained
# reference the trained seat should beat more often as training progresses.


@torch.no_grad()
def eval_vs_random(policy: ActorCritic, episodes: int, rng: np.random.Generator) -> dict[str, float]:
    wins = draws = losses = 0
    for _ in range(episodes):
        env = make(ENV_ID)
        seed = int(rng.integers(0, 2**63 - 1))
        result = env.reset(seed=seed)
        trained_seat = int(rng.integers(0, 2))  # cancel any positional edge, same spirit as paired seating
        while not result.done:
            actions = [0, 0]
            for seat in range(2):
                obs = result.observations[seat]
                if obs is None:
                    continue
                if seat == trained_seat:
                    actions[seat], _, _ = policy.act(obs.features, obs.legal_actions)
                else:
                    legal = np.flatnonzero(obs.legal_actions)
                    actions[seat] = int(rng.choice(legal))
            result = env.step(actions[0], actions[1])
        r = _outcome_reward(result.outcome, trained_seat)
        wins += r > 0
        losses += r < 0
        draws += r == 0
    return {"win_rate": wins / episodes, "draw_rate": draws / episodes, "loss_rate": losses / episodes}


# --------------------------------------------------------------------------
# Main loop


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--episodes-per-iter", type=int, default=64)
    parser.add_argument("--eval-episodes", type=int, default=200)
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-eps", type=float, default=0.2)
    parser.add_argument("--value-coef", type=float, default=0.5)
    parser.add_argument("--entropy-coef", type=float, default=0.01)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--minibatch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--checkpoint-dir", type=Path, default=Path(__file__).parent / "checkpoints")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    policy = ActorCritic().to(DEVICE)
    optimizer = torch.optim.Adam(policy.parameters(), lr=args.lr)
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    print(f"env={ENV_ID} obs_floats={OBS_FLOATS} num_actions={NUM_ACTIONS} device={DEVICE}", file=sys.stderr)

    for iteration in range(1, args.iterations + 1):
        t0 = time.perf_counter()
        trajectories: list[Trajectory] = []
        outcomes = {Outcome.PLAYER_0: 0, Outcome.PLAYER_1: 0, Outcome.DRAW: 0}
        illegal_forfeits = 0
        total_ticks = 0
        for _ in range(args.episodes_per_iter):
            seed = int(rng.integers(0, 2**63 - 1))
            episode_trajs, outcome, termination, ticks = play_episode(policy, seed)
            trajectories.extend(episode_trajs)
            outcomes[outcome] += 1
            illegal_forfeits += termination is Termination.ILLEGAL_ACTION
            total_ticks += ticks
        collect_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        stats = ppo_update(
            policy,
            optimizer,
            trajectories,
            args.gamma,
            args.gae_lambda,
            args.clip_eps,
            args.value_coef,
            args.entropy_coef,
            args.epochs,
            args.minibatch_size,
        )
        update_s = time.perf_counter() - t0

        n = args.episodes_per_iter
        msg = (
            f"iter {iteration:4d}  "
            f"p0={outcomes[Outcome.PLAYER_0] / n:.2f} p1={outcomes[Outcome.PLAYER_1] / n:.2f} "
            f"draw={outcomes[Outcome.DRAW] / n:.2f} illegal={illegal_forfeits}  "
            f"avg_ticks={total_ticks / n:.1f}  "
            f"loss(pi={stats['policy_loss']:+.3f} v={stats['value_loss']:.3f} ent={stats['entropy']:.3f})  "
            f"batch={stats['batch_size']}  collect={collect_s:.1f}s update={update_s:.1f}s"
        )

        if iteration % args.eval_every == 0:
            eval_stats = eval_vs_random(policy, args.eval_episodes, rng)
            msg += (
                f"  | vs random: win={eval_stats['win_rate']:.2f} "
                f"draw={eval_stats['draw_rate']:.2f} loss={eval_stats['loss_rate']:.2f}"
            )
        print(msg, file=sys.stderr)

        if iteration % args.checkpoint_every == 0:
            path = args.checkpoint_dir / f"sap_ppo_iter{iteration}.pt"
            torch.save(policy.state_dict(), path)
            print(f"saved {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
