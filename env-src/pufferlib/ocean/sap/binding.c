#include "sap.h"
#define OBS_SIZE SAP_OBS_FLOATS
#define NUM_ATNS 1
#define ACT_SIZES {SAP_NUM_ACTIONS}
#define OBS_TENSOR_T FloatTensor
#define MY_ACTION_MASK SAP_NUM_ACTIONS

#define MY_USES_PERM
#define Env Sap
#include "vecenv.h"

/* Routes per-agent buffer pointers into the shared vectorized buffers,
 * respecting agent_perm if set - same role robocode's my_setup_perm plays,
 * plus action_mask_ptr wiring the way chess's does, since (unlike
 * robocode) this env actually uses a legal-action mask: sap_rules.h's
 * illegal-action-forfeits-immediately rule means an unmasked policy could
 * tank a whole episode on one bad index, same as it would in
 * policyclash_envs' own copy of these rules. */
void my_setup_perm(StaticVec* vec, Env* env, int slot_base) {
    for (int s = 0; s < env->num_agents; s++) {
        int phys = vec->agent_perm ? vec->agent_perm[slot_base + s] : (slot_base + s);
        env->obs_ptr[s] = (float*)vec->observations + (size_t)phys * OBS_SIZE;
        env->action_ptr[s] = vec->actions + (size_t)phys * NUM_ATNS;
        env->reward_ptr[s] = vec->rewards + phys;
        env->terminal_ptr[s] = vec->terminals + phys;
        env->action_mask_ptr[s] = vec->action_mask + (size_t)phys * MY_ACTION_MASK;
    }
}

void my_init(Env* env, Dict* kwargs) {
    env->num_agents = 2; /* selfplay-only in this first port - see sap.h */
    init(env);
    /* Optional `seed` kwarg overrides the per-instance default init() set
     * (env index folded into a constant - see sap.h). dict_get_unsafe,
     * not dict_get, because dict_get asserts the key exists; this one
     * genuinely may not be in the .ini's [env] section. */
    DictItem* seed_entry = dict_get_unsafe(kwargs, "seed");
    if (seed_entry != NULL) {
        env->episode_rng = (uint64_t)seed_entry->value;
    }
}

void my_log(Log* log, Dict* out) {
    dict_set(out, "perf", log->perf);
    dict_set(out, "score", log->score);
    dict_set(out, "episode_return", log->episode_return);
    dict_set(out, "episode_length", log->episode_length);
    /* Read by pufferl.match() as the A/B win rates - see sap.h's Log field
     * comments and robocode/binding.c's identical convention. */
    dict_set(out, "slot_0_score", log->slot_0_score);
    dict_set(out, "slot_1_score", log->slot_1_score);
    dict_set(out, "draw_rate", log->draw_rate);
    dict_set(out, "n", log->n);
}
