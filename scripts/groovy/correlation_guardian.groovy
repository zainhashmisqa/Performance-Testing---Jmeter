/* ===========================================================================
 * CONCEPT 17 — Correlation Guardian Agent  (Tier B)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor after EVERY JSON Extractor group, or as a
 *            single PostProcessor on the Test Plan root (runs after every sampler).
 *
 * The self_heal_token.groovy handles authToken specifically. This script is
 * the generalized agent: it monitors ALL extracted variables and heals any
 * that fall back to their NOT_FOUND sentinel.
 *
 * WHAT IT DOES:
 *   1. Maintains a registry of expected extraction targets and their aliases.
 *   2. After each sampler, checks if any registered variable is NOT_FOUND.
 *   3. Scans the response for alternative field names.
 *   4. Logs every heal decision for the report.
 *
 * AGENT BEHAVIOR:
 *   - Learns: records which field names actually work per sampler and caches
 *     them as properties so subsequent iterations use the known mapping.
 *   - Adapts: if a previously working mapping breaks, clears the cache and
 *     re-scans.
 *   - Reports: writes a structured JSON log that the tearDown script can
 *     aggregate into a summary table.
 * =========================================================================== */

import groovy.json.JsonSlurper
import groovy.json.JsonOutput

final String SENTINEL = "NOT_FOUND"

// Registry: variable name -> list of aliases to search for
def registry = [
    "userId"         : ["userId", "user_id", "id", "pk", "uid", "account_id", "accountId",
                        "profile_id", "profileId", "user_pk", "userPk"],
    "courseSlug"     : ["courseSlug", "course_slug", "slug", "course_id", "courseId",
                        "course_key", "courseKey", "course_code"],
    "enrollmentId"   : ["enrollmentId", "enrollment_id", "enroll_id", "enrollId",
                        "registration_id", "registrationId"],
    "certId"         : ["certId", "cert_id", "certificate_id", "certificateId",
                        "credential_id", "credentialId"],
    "categorySlug"   : ["categorySlug", "category_slug", "category_id", "categoryId",
                        "cat_slug", "catSlug", "category"],
    "catalogCourseId": ["catalogCourseId", "catalog_course_id", "course_id", "courseId",
                        "catalog_id", "catalogId"],
    "orderId"        : ["orderId", "order_id", "orderNumber", "order_number",
                        "transaction_id", "transactionId", "purchase_id"]
]

def body = prev.getResponseDataAsString()
if (!body || body.trim().isEmpty()) return

def parsed
try {
    parsed = new JsonSlurper().parseText(body)
} catch (e) {
    return // not JSON — nothing to heal
}

// Flatten response including arrays
def flat = [:]
def flatten
flatten = { Object node, Map out, int depth ->
    if (depth > 5) return out
    if (node instanceof Map) {
        node.each { k, v ->
            if (v instanceof Map) {
                flatten(v, out, depth + 1)
            } else if (v instanceof List && !v.isEmpty() && v[0] instanceof Map) {
                flatten(v[0], out, depth + 1)
            } else if (!out.containsKey(k as String)) {
                out[k as String] = v
            }
        }
    } else if (node instanceof List && !node.isEmpty()) {
        if (node[0] instanceof Map) flatten(node[0], out, depth + 1)
    }
    return out
}
flatten(parsed, flat, 0)

def samplerName = prev.getSampleLabel()
int healed = 0
def healDetails = []

registry.each { varName, aliases ->
    def current = vars.get(varName)

    // Skip if variable was never set (this sampler doesn't extract it)
    if (current == null) return

    // Skip if extraction succeeded
    if (current != SENTINEL && current.trim().length() > 0) {
        // Learning: cache which field worked for this sampler
        def cacheKey = "corrGuard_${samplerName}_${varName}"
        if (!props.get(cacheKey)) {
            props.put(cacheKey, "original")
        }
        return
    }

    // Variable is NOT_FOUND — attempt healing

    // Check cached mapping first
    def cacheKey = "corrGuard_${samplerName}_${varName}"
    def cachedAlias = props.get(cacheKey)
    if (cachedAlias && cachedAlias != "original" && flat[cachedAlias]) {
        def val = flat[cachedAlias].toString()
        if (val.trim().length() > 0) {
            vars.put(varName, val)
            healed++
            healDetails << [var: varName, from: cachedAlias, method: "cache"]
            return
        }
        props.remove(cacheKey) // cached alias no longer works
    }

    // Scan aliases
    for (alias in aliases) {
        def v = flat[alias]
        if (v != null && v.toString().trim().length() > 0) {
            vars.put(varName, v.toString())
            props.put(cacheKey, alias) // learn for next iteration
            healed++
            healDetails << [var: varName, from: alias, method: "alias_scan"]
            log.warn("CORR-GUARDIAN: healed ${varName} from field '${alias}' in ${samplerName}")
            return
        }
    }

    // Heuristic: look for a key containing the variable's root word
    def rootWord = varName.replaceAll(/[A-Z]/) { "_${it.toLowerCase()}" }
        .split("_").findAll { it.length() > 2 }
    flat.each { k, v ->
        if (vars.get(varName) != SENTINEL) return
        def ks = k.toString().toLowerCase()
        if (rootWord.any { rw -> ks.contains(rw) } && v?.toString()?.trim()?.length() > 0) {
            vars.put(varName, v.toString())
            props.put(cacheKey, k)
            healed++
            healDetails << [var: varName, from: k, method: "heuristic"]
            log.warn("CORR-GUARDIAN: healed ${varName} from heuristic match '${k}' in ${samplerName}")
        }
    }
}

// Log healing events
if (healed > 0) {
    def statsKey = "corrGuard_totalHeals"
    def total = ((props.get(statsKey) ?: "0") as int) + healed
    props.put(statsKey, total.toString())

    try {
        def dir = new File("results")
        if (!dir.exists()) dir.mkdirs()
        def workerId = props.get("worker_id") ?: "local"
        def entry = [
            timestamp: new Date().format('yyyy-MM-dd HH:mm:ss'),
            sampler  : samplerName,
            worker   : workerId,
            healed   : healDetails
        ]
        new File(dir, "correlation-guardian-${workerId}.jsonl").append(
            JsonOutput.toJson(entry) + System.lineSeparator())
    } catch (ignored) {}
}
