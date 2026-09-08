/* PufferLib Ocean wrapper around sap_rules.h (a verbatim copy of
 * policy-clash's sap.h). This file has no rules in it - shop mechanics,
 * abilities, and battle resolution are all in sap_rules.h, already written
 * and tested against policy-clash's own 19-test suite. What's here is only
 * the adaptation from `SAP` (reset/step/observe/legal, one call per
 * function) to the per-tick array-write contract vecenv.h expects
 * (obs_ptr/action_ptr/reward_ptr/terminal_ptr, auto-reset on terminal).
 *
 * Both seats act every real shop tick here, same as sap_rules.h's own
 * sap_step(a0, a1) signature already expects - unlike chess, which must
 * simulate "one mover at a time" inside a framework that always asks every
 * agent slot for an action every tick, SAP's shop phase genuinely has no
 * interaction between the two seats until battle, so there is nothing to
 * simulate: this env calls c_step -> sap_step(core, a0, a1) directly, one
 * PufferLib tick per real shop tick, exactly matching policyclash_envs'
 * own adapter. A seat that has already ended (sap_rules.h's per-seat
 * `ended` flag) simply has its action ignored inside sap_step, same as
 * always, and sap_observe naturally keeps returning its frozen last state
 * every subsequent tick with no special-casing needed here - its true
 * Markov state genuinely hasn't changed, since nothing about its own shop
 * or team can change once it has stopped acting.
 */

#ifndef OCEAN_SAP_H
#define OCEAN_SAP_H

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "sap_rules.h"

typedef struct Log Log;
struct Log {
    float perf;
    float score;         /* seat 0 win indicator, this episode: 1/0.5/0 win/draw/loss */
    float episode_return; /* r0 + r1 - always ~0 for a zero-sum selfplay env; kept for
                            * interface consistency with other Ocean envs' Log structs,
                            * not a useful training curve here by construction. */
    float episode_length;
    /* Per-slot outcome sums (not rates - divide by `n` at the reporting
     * layer, same convention every other Ocean env's Log struct uses).
     * `pufferl.match()` reads slot_0_score / slot_1_score / draw_rate as
     * the A/B win rates for exactly this reason - see robocode/binding.c's
     * own comment on the same three fields. */
    float slot_0_score;
    float slot_1_score;
    float draw_rate;
    float n;
};

typedef struct Client Client; /* no rendering in this first pass - training is headless */

typedef struct Sap Sap;
struct Sap {
    /* PufferLib inputs/outputs. These four flat arrays back the standalone
     * (demo/single-instance) allocation path in allocate_sap() below; under
     * real vectorized training, vecenv.h's my_setup_perm re-points
     * obs_ptr/action_ptr/reward_ptr/terminal_ptr into the shared vec
     * buffers instead, and these flat arrays go unused. Both paths write
     * through the *_ptr fields only, never these directly, so c_step and
     * c_reset don't need to know which path is active. */
    float* observations;
    float* actions;
    float* rewards;
    float* terminals;
    int num_agents; /* always 2 - this env is selfplay-only, no vs-bot mode (yet) */

    float* obs_ptr[2];
    float* action_ptr[2];
    float* reward_ptr[2];
    float* terminal_ptr[2];
    /* vecenv.h writes both of these unconditionally when MY_ACTION_MASK is
     * defined: the plain `action_mask` field is the framework's own
     * single-agent-shaped default wiring (present on every Ocean env's
     * struct regardless, per e.g. ocean/chess/chess.h - unused by this
     * env's own code, which reads through action_mask_ptr[s] instead, the
     * same way chess itself declares and ignores it). */
    unsigned char* action_mask;
    unsigned char* action_mask_ptr[2]; /* NULL under the standalone path: no masking there */

    unsigned int rng; /* vecenv.h's own field name, populated by its default
                        * my_vec_init as this instance's env index - not
                        * sap_rules.h's RNG and not read by this env's own
                        * code except once, in init(), to seed episode_rng
                        * distinctly per vectorized instance. */

    SAP core; /* the actual rules state - see sap_rules.h */
    uint64_t episode_rng; /* draws each fresh episode's seed on auto-reset; a
                            * stream of its own, independent of sap_rules.h's
                            * per-seat/battle RNG streams inside `core`. */

    Log log;
    Client* client;
};

/* Called from vecenv.h's rendering path; this env has no rendering in this
 * first pass (headless training only), so a no-op stub is enough to link -
 * static_vec_render's call to it is only reachable from the interactive
 * viewer, never from `puffer train`. */
static inline void c_render(Sap* env) {
    (void)env;
}

static inline void allocate_sap(Sap* env) {
    env->num_agents = 2;
    env->observations = (float*)calloc((size_t)SAP_OBS_FLOATS * (size_t)env->num_agents, sizeof(float));
    env->actions = (float*)calloc((size_t)env->num_agents, sizeof(float)); /* NUM_ATNS=1: one scalar action per agent */
    env->rewards = (float*)calloc((size_t)env->num_agents, sizeof(float));
    env->terminals = (float*)calloc((size_t)env->num_agents, sizeof(float));
    for (int s = 0; s < env->num_agents; s++) {
        env->obs_ptr[s] = env->observations + (size_t)s * SAP_OBS_FLOATS;
        env->action_ptr[s] = env->actions + s;
        env->reward_ptr[s] = env->rewards + s;
        env->terminal_ptr[s] = env->terminals + s;
        env->action_mask_ptr[s] = NULL;
    }
    env->client = NULL;
}

static inline void free_allocated_sap(Sap* env) {
    free(env->observations);
    free(env->actions);
    free(env->rewards);
    free(env->terminals);
}

static inline void sap_ocean_populate_observations(Sap* env) {
    /* sap_observe/sap_legal write directly into whatever buffer they're
     * given - obs_ptr[s] IS that buffer, standalone or vectorized, so
     * there is no intermediate copy here. */
    sap_observe(&env->core, 0, env->obs_ptr[0]);
    sap_observe(&env->core, 1, env->obs_ptr[1]);
    if (env->action_mask_ptr[0] != NULL) {
        sap_legal(&env->core, 0, env->action_mask_ptr[0]);
    }
    if (env->action_mask_ptr[1] != NULL) {
        sap_legal(&env->core, 1, env->action_mask_ptr[1]);
    }
}

static inline void init(Sap* env) {
    /* env->log is a plain struct field, not a calloc'd buffer, so nothing
     * has zeroed it before this - found the hard way: a standalone harness
     * printed a garbage draw_rate despite score/n being correct, because
     * this run's stack memory for `log` happened not to start at zero the
     * way it coincidentally had in an earlier run. init() runs once per
     * env instance (unlike c_reset, which runs once per episode and must
     * NOT touch log - it accumulates across many episodes for reporting),
     * so this is the one correct place to zero it. */
    memset(&env->log, 0, sizeof(env->log));

    /* vecenv.h's default my_vec_init has already set env->rng to this
     * instance's env index before calling my_init (which calls this) - see
     * sap.h's `rng` field comment. Folding it into the splitmix64 constant
     * gives every vectorized instance a distinct starting episode-seed
     * stream with no coordination needed between them, rather than every
     * instance in an unconfigured run drawing the identical sequence of
     * episodes. my_init may still override episode_rng outright from a
     * `seed` kwarg after calling this, for a fully reproducible run. */
    env->episode_rng = 0x2545F4914F6CDD1Dull ^ (uint64_t)env->rng;
}

static inline void c_reset(Sap* env) {
    /* Deliberately does not touch reward_ptr/terminal_ptr - neither does
     * chess's or robocode's c_reset. c_step's terminal branch sets them to
     * the just-finished episode's outcome and calls this after, so the
     * bundled transition PufferLib expects is: terminal=1, reward=result
     * (set by the caller, untouched here), observation=the fresh episode
     * this call produces. Zeroing them here would clobber the very result
     * c_step just computed - found by writing a standalone harness for
     * this env and watching every episode dead-loop at 0/0/ongoing despite
     * sap_step correctly returning SAP_DRAW every time; the calloc'd
     * initial state in allocate_sap already covers the one case this
     * function's own zeroing was for (the very first reset, before any
     * episode has run). */
    sap_reset(&env->core, sap_splitmix64(&env->episode_rng));
    sap_ocean_populate_observations(env);
}

/* Status code -> (reward seat0, reward seat1). Mirrors _TERMINAL in
 * policyclash_envs/sap.py's outcome mapping exactly, just as a pair of
 * floats instead of an (Outcome, Termination) tuple - PufferLib's reward
 * channel is the only signal the training loop reads the result through,
 * there being no separate Termination field in this framework. */
static inline void sap_ocean_reward(int status, float* r0, float* r1) {
    switch (status) {
    case SAP_P0_WIN:
    case SAP_P0_WIN_ILLEGAL:
        *r0 = 1.0f;
        *r1 = -1.0f;
        break;
    case SAP_P1_WIN:
    case SAP_P1_WIN_ILLEGAL:
        *r0 = -1.0f;
        *r1 = 1.0f;
        break;
    default: /* SAP_DRAW, SAP_DRAW_ILLEGAL */
        *r0 = 0.0f;
        *r1 = 0.0f;
        break;
    }
}

static inline void c_step(Sap* env) {
    const int a0 = (int)(*env->action_ptr[0]);
    const int a1 = (int)(*env->action_ptr[1]);
    const int status = sap_step(&env->core, a0, a1);
    env->log.episode_length += 1.0f;

    if (status == SAP_ONGOING) {
        *env->reward_ptr[0] = 0.0f;
        *env->reward_ptr[1] = 0.0f;
        *env->terminal_ptr[0] = 0.0f;
        *env->terminal_ptr[1] = 0.0f;
        sap_ocean_populate_observations(env);
        return;
    }

    float r0, r1;
    sap_ocean_reward(status, &r0, &r1);
    *env->reward_ptr[0] = r0;
    *env->reward_ptr[1] = r1;
    *env->terminal_ptr[0] = 1.0f;
    *env->terminal_ptr[1] = 1.0f;

    env->log.episode_return += r0 + r1; /* ~0 always in this zero-sum env; see Log's field comment */
    env->log.n += 1.0f;
    if (r0 > 0.0f) {
        env->log.slot_0_score += 1.0f;
        env->log.score += 1.0f;
    } else if (r1 > 0.0f) {
        env->log.slot_1_score += 1.0f;
    } else {
        env->log.draw_rate += 1.0f;
        env->log.score += 0.5f;
    }
    env->log.perf = env->log.score;

    /* Auto-reset: the same convention chess/go/robocode/slimevolley all
     * use. The terminal transition's reward above is this episode's
     * outcome; the observation bundled with it (written by c_reset, right
     * here) is already the *next* episode's start - vecenv.h expects
     * exactly this, not a separate reset call from the training loop. */
    c_reset(env);
}

static inline void c_close(Sap* env) {
    (void)env;
}

#endif /* OCEAN_SAP_H */
