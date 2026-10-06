/* ===========================================================================
 * Token pool — CONSUME side.
 * ---------------------------------------------------------------------------
 * Placement: JSR223 Sampler at the top of the Main Thread Group.
 *
 * Claims ONE token per thread, once, and keeps it for the whole run. JMeter
 * variables persist across iterations within a thread, so the fast path after
 * the first iteration is a single string comparison.
 *
 * If the pool is exhausted (setUp obtained fewer tokens than Main has threads),
 * tokenBound stays false and the IF controller downstream performs a re-login
 * for that thread.
 * =========================================================================== */

final String SENTINEL = "NOT_FOUND"

// Fast path: this thread already holds a token from an earlier iteration.
def existing = vars.get("authToken")
if (existing != null && existing != SENTINEL && !existing.trim().isEmpty()) {
    vars.put("tokenBound", "true")
    SampleResult.setIgnore()
    return
}

def queue = props.get("token_pool")
def token = queue?.poll()

if (token) {
    vars.put("authToken", token.toString())
    vars.put("tokenBound", "true")
    log.info("token_pool_bind: bound token from pool for thread " + ctx.getThreadNum())
} else {
    vars.put("tokenBound", "false")
    def published = props.get("token_pool_published") ?: "0"
    log.warn("Token pool exhausted for thread ${ctx.getThreadNum()} " +
             "(setUp published ${published}). This thread will re-login.")
}

SampleResult.setIgnore()
