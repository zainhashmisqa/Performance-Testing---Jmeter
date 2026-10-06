/* ===========================================================================
 * CONCEPT 15 — Error Handling & Retry  (Tier B, part 2 of 2)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor INSIDE the While Controller, directly after
 *            the Certificates sampler (S07).
 *
 * While Controller condition (set on the controller itself):
 *   ${__groovy(vars.get("ok") != "true" && (vars.get("tries") ?: "0").toInteger() < Integer.parseInt(props.getProperty("max_retries","3")))}
 *
 * Decides success on BODY CONTENT, not just the HTTP code — a 200 carrying an
 * error body must count as a failure (this is one of the brief's five pitfalls).
 *
 * Retried attempts are marked non-failing so a recovered transaction does not
 * pollute the error rate; only exhaustion of all attempts is a real failure.
 * =========================================================================== */

def maxRetries = (props.get("max_retries") ?: "3").toInteger()
def backoff    = (props.get("retry_backoff_ms") ?: "500").toInteger()

def tries = (vars.get("tries") ?: "0").toInteger() + 1
vars.put("tries", tries.toString())

def code = prev.getResponseCode()
def body = prev.getResponseDataAsString() ?: ""

// Success = transport OK *and* the body actually confirms the business outcome.
// Certificates endpoint returns a JSON array with id and course_slug fields.
def bodyConfirms = body.contains("\"id\"") &&
                   (body.contains("\"course_slug\"") || body.contains("\"course_title\"") ||
                    body.contains("\"issued_at\"")   || body.contains("confirmed") ||
                    body.contains("complete")         || body.contains("success"))

if (prev.isSuccessful() && bodyConfirms) {
    vars.put("ok", "true")
    if (tries > 1) {
        log.warn("RETRY RECOVERED — '${prev.getSampleLabel()}' succeeded on attempt ${tries}")
        vars.put("recoveredAfter", tries.toString())
    }
} else {
    vars.put("ok", "false")
    def reason = !prev.isSuccessful() ? "rc=${code}" : "body did not confirm status"
    vars.put("lastRetryReason", reason)

    if (tries < maxRetries) {
        // Don't count an attempt we are about to retry as a run failure.
        prev.setSuccessful(true)
        prev.setResponseMessage("RETRYING (attempt ${tries}/${maxRetries}) — ${reason}")
        log.warn("RETRY ${tries}/${maxRetries} for '${prev.getSampleLabel()}' — ${reason}")
        sleep(backoff * tries)   // linear backoff: 500ms, 1000ms, ...
    } else {
        prev.setSuccessful(false)
        prev.setResponseMessage("FAILED after ${maxRetries} attempts — ${reason}")
        log.error("RETRY EXHAUSTED for '${prev.getSampleLabel()}' after ${maxRetries} attempts — ${reason}")
    }
}
