/* ===========================================================================
 * Test data lifecycle — tearDown cleanup
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor on "TD Purge run data" in the tearDown
 *            Thread Group.
 *
 * WHY A PERFORMANCE SUITE NEEDS THIS MORE THAN A FUNCTIONAL ONE
 * Peak is 200 VUs x 15 minutes x 20% checkout - thousands of enrollment rows
 * per run. Leave them and the table grows monotonically across runs. By the
 * third run checkout genuinely slows, because the index is bigger, and you
 * report a checkout bottleneck that your own test manufactured. That is the
 * point at which nobody can trust the numbers, including you.
 *
 * Cleanup is therefore part of the measurement, not housekeeping.
 *
 * SAFETY: this issues a destructive DELETE. It is gated on cleanup_enabled and
 * MUST only ever point at a test environment. Never enable it against anything
 * holding data you did not create.
 * =========================================================================== */

import groovy.json.JsonSlurper

def env = props.get("env") ?: "unknown"

// Refuse to purge anything that is not clearly a test environment. A misrouted
// -Jbase_url should not be able to delete rows somewhere real.
if (env.toLowerCase() in ["prod", "production", "live"]) {
    log.error("CLEANUP ABORTED - env='${env}'. Refusing to purge a production-like environment.")
    prev.setSuccessful(false)
    prev.setResponseMessage("Cleanup refused: env=${env}")
    return
}

if (!prev.isSuccessful()) {
    log.error("CLEANUP FAILED (rc=${prev.getResponseCode()}). Test data from this " +
              "run remains in the environment and WILL skew the next run. " +
              "Purge it manually before re-running.")
    return
}

try {
    def body = new JsonSlurper().parseText(prev.getResponseDataAsString())
    def deleted = body.deleted ?: 0
    log.info("CLEANUP OK - removed ${deleted} row(s) created by this run (env=${env})")

    def dir = new File("results")
    if (!dir.exists()) dir.mkdirs()
    new File(dir, "cleanup.log").append(
        new Date().format('yyyy-MM-dd HH:mm:ss') +
        "  env=" + env + "  deleted=" + deleted + System.lineSeparator())
} catch (e) {
    log.warn("Cleanup ran but the response was not parseable: ${e.message}")
}
