/* ===========================================================================
 * Token pool — PUBLISH side.
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor on setUp › S00 Login, after the self-heal.
 *
 * WHY A QUEUE, NOT AN INDEX:
 * An earlier version keyed tokens by ctx.getThreadNum(), which silently assumed
 * the setUp Thread Group and the Main Thread Group have identical thread counts.
 * Override -Jthreads for one and not the other and some Main threads find no
 * token, fall back to re-login, and pollute the transaction timings with an
 * extra auth call — exactly the thing putting login in setUp was meant to avoid.
 *
 * A shared queue decouples the two groups completely: setUp publishes however
 * many tokens it obtained, Main consumes one per thread, and any shortfall is
 * visible and logged rather than silent.
 * =========================================================================== */

import java.util.concurrent.ConcurrentLinkedQueue

final String SENTINEL = "NOT_FOUND"
def token = vars.get("authToken")

if (token == null || token == SENTINEL || token.trim().isEmpty()) {
    log.error("setUp: no usable token for ${vars.get('username')} — Main will re-login for one thread.")
    return
}

// Lazily create the shared queue. props is a java.util.Properties (a Hashtable),
// so it holds arbitrary objects and is shared across all thread groups.
def queue = props.get("token_pool")
if (queue == null) {
    synchronized (props) {
        queue = props.get("token_pool")
        if (queue == null) {
            queue = new ConcurrentLinkedQueue()
            props.put("token_pool", queue)
        }
    }
}

queue.add(token)
props.put("token_pool_published", queue.size().toString())

// Also publish as a shared property so the Monitor thread group can authenticate
// without consuming a token from the pool.
props.put("shared_token", token)
