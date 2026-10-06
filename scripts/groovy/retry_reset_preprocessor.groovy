/* ===========================================================================
 * CONCEPT 15 — Error Handling & Retry  (Tier A, part 1 of 2)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PreProcessor on the "Reset retry state" sampler, placed
 *            BEFORE the While Controller on every iteration.
 *
 * Without this reset, a thread that succeeded once would carry ok=true into
 * the next iteration and the While Controller would never enter — the retry
 * wrapper would look like it works while actually doing nothing.
 * =========================================================================== */

vars.put("ok", "false")
vars.put("tries", "0")
vars.remove("lastRetryReason")
