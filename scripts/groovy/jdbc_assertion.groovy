/* ===========================================================================
 * CONCEPT 11 — JDBC Validation  (Tier B)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 Assertion on the "JDBC verify enrollment row" request,
 *            which sits inside a While Controller so the query can be re-issued.
 *
 * Proves the checkout actually persisted. An HTTP 200 with status=confirmed
 * only says the API *claimed* success; the DB row says it happened.
 *
 * RACE CONDITION THIS HANDLES:
 * If checkout is processed asynchronously (queue, worker, eventual commit) the
 * row will not exist the instant the HTTP call returns. A single immediate
 * query would report a false failure and make the whole suite look broken under
 * load — precisely when async lag is worst. So the query is retried up to
 * db_max_tries with a short delay, and only genuine exhaustion fails.
 *
 * Set -Jdb_max_tries=1 to assert strictly synchronously (useful once you have
 * confirmed the write is synchronous — a stricter test is a better test).
 *
 * Execution order note: JMeter runs PostProcessors, then Assertions. The loop
 * state is maintained here and read by the While Controller's condition.
 * =========================================================================== */

def maxTries = (props.get("db_max_tries") ?: "3").toInteger()
def delayMs  = (props.get("db_retry_delay_ms") ?: "400").toInteger()

def tries = (vars.get("dbTries") ?: "0").toInteger() + 1
vars.put("dbTries", tries.toString())

def orderId = vars.get("orderId") ?: "(none)"
def rows = vars.getObject("dbResult")

// --- Hard failures: no retry will fix a broken pool or a bad driver ---------
if (rows == null) {
    vars.put("dbFound", "true")   // stop the loop; this is not a timing problem
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage(
        "JDBC returned no result object — check the pool name (db_pool) and that " +
        "the driver jar is in <jmeter>/lib/ with JMeter restarted.")
    return
}

// --- Count the row --------------------------------------------------------
int cnt = 0
if (!rows.isEmpty()) {
    def row = rows[0]
    def raw = row["cnt"] ?: row["CNT"] ?: row.values().find { it != null }
    try { cnt = (raw as String).toInteger() } catch (ignored) { cnt = 0 }
}

if (cnt >= 1) {
    vars.put("dbFound", "true")
    if (tries > 1) {
        log.warn("JDBC validation OK for orderId=${orderId} on attempt ${tries} " +
                 "— the write is asynchronous; note this in the report.")
    } else {
        log.info("JDBC validation OK — ${cnt} row(s) for orderId=${orderId}")
    }
    return
}

// --- Not found yet --------------------------------------------------------
vars.put("dbFound", "false")

if (tries < maxTries) {
    // Do not fail: the row may still be committing. The While Controller will
    // re-issue the query. Keep the sample green so a recoverable async lag does
    // not inflate the error rate.
    AssertionResult.setFailure(false)
    prev.setSuccessful(true)
    log.info("JDBC row not yet present for orderId=${orderId} " +
             "(attempt ${tries}/${maxTries}) — retrying in ${delayMs}ms")
    sleep(delayMs)
} else {
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage(
        "DB VALIDATION FAILED — no enrollment row for orderId=${orderId} after " +
        "${maxTries} attempts. The API reported success but nothing was persisted.")
    log.error("JDBC validation failed for orderId=${orderId} after ${maxTries} attempts")
}
