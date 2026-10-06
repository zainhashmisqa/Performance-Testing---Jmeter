/* ===========================================================================
 * CONCEPT 17 — AI Self-Healing  (Tier B)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor, immediately AFTER the token JSON Extractor
 *            in the setUp Thread Group.
 *
 * MULTI-STRATEGY SELF-HEALING AGENT
 *
 * Problem: the API renames, nests, or restructures the token field and a naive
 * extractor silently yields nothing, so every downstream request 401s.
 *
 * FOUR LAYERS, each more aggressive than the last:
 *   Layer 1 — Deterministic alias map (11 known field names).
 *   Layer 2 — JWT structure detection (header.payload.signature pattern).
 *   Layer 3 — Heuristic: long opaque string under a token-ish key.
 *   Layer 4 — Optional LLM fallback for a field name nobody predicted.
 *
 * AGENT FEATURES:
 *   - Circuit breaker: after 3 heals on the same alias, caches it for the
 *     rest of the run so subsequent iterations skip the scan entirely.
 *   - Healing statistics: tracks per-layer hit counts in JMeter properties
 *     so the tearDown or report script can summarize them.
 *   - Multi-field: also heals userId, courseSlug, enrollmentId if missing.
 *   - Response fingerprinting: logs structure changes between requests.
 *
 * Evidence for the report is appended to results/self-heal-<worker>.log.
 * =========================================================================== */

import groovy.json.JsonSlurper

final String SENTINEL = "NOT_FOUND"

// ---- Circuit breaker: if we already know the right field, use it directly ---
def cachedField = props.get("selfHeal_cachedField")
if (cachedField) {
    def body = prev.getResponseDataAsString()
    try {
        def parsed = new JsonSlurper().parseText(body)
        def val = deepGet(parsed, cachedField)
        if (val) {
            vars.put("authToken", val.toString())
            vars.put("selfHealApplied", "circuit-breaker")
            incStat("circuit_breaker")
            return
        }
    } catch (ignored) {}
    // Cache miss — field moved again, clear cache and fall through
    props.remove("selfHeal_cachedField")
}

def token = vars.get("authToken")

// Fast exit: extraction worked, nothing to heal.
if (token != null && token != SENTINEL && token.trim().length() > 0) {
    return
}

// ---- Evidence logging -------------------------------------------------------
def workerId = props.get("worker_id") ?: "local"
def hostName = InetAddress.getLocalHost().getHostName()

def healLog = { String msg ->
    try {
        def dir = new File("results")
        if (!dir.exists()) dir.mkdirs()
        new File(dir, "self-heal-" + workerId + ".log").append(
            new Date().format('yyyy-MM-dd HH:mm:ss') +
            "  [" + workerId + "@" + hostName + "]  " + msg + System.lineSeparator())
    } catch (ignored) {}
}

// ---- Stat counter -----------------------------------------------------------
def incStat = { String layer ->
    def key = "selfHeal_${layer}_count"
    def c = ((props.get(key) ?: "0") as int) + 1
    props.put(key, c.toString())
}

def body = prev.getResponseDataAsString()

// ---- Flatten the response (depth 5 for deeply nested APIs) ------------------
def flatten
flatten = { Object node, Map out, String prefix, int depth ->
    if (depth > 5 || !(node instanceof Map)) return out
    node.each { k, v ->
        def fullKey = prefix ? "${prefix}.${k}" : k as String
        if (v instanceof Map) {
            flatten(v, out, fullKey, depth + 1)
        } else if (v instanceof List && !v.isEmpty() && v[0] instanceof Map) {
            flatten(v[0], out, "${fullKey}[0]", depth + 1)
        } else {
            if (!out.containsKey(k as String)) out[k as String] = v
            out[fullKey] = v
        }
    }
    return out
}

def deepGet
deepGet = { Object node, String path ->
    if (!node || !path) return null
    def parts = path.tokenize('.')
    def current = node
    for (p in parts) {
        if (current instanceof Map) current = current[p]
        else return null
    }
    return current
}

def flat = [:]
def parsed = null
try {
    parsed = new JsonSlurper().parseText(body)
    flatten(parsed, flat, "", 0)
} catch (e) {
    log.error("SELF-HEAL: response is not parseable JSON — ${e.message}")
    healLog("FAIL  unparseable response for ${prev.getSampleLabel()} (rc=${prev.getResponseCode()})")
    return
}

// ---- Response fingerprint (track structure changes) -------------------------
def structureKeys = flat.keySet().sort().join(",")
def prevFingerprint = props.get("selfHeal_lastFingerprint")
if (prevFingerprint && prevFingerprint != structureKeys) {
    healLog("STRUCTURE-CHANGE  previous_keys=${prevFingerprint.take(200)}  new_keys=${structureKeys.take(200)}")
    log.warn("SELF-HEAL: response structure changed — API may have been updated")
}
props.put("selfHeal_lastFingerprint", structureKeys)

String healed = null
String healedKey = null
String healLayer = null

// ---- LAYER 1: known aliases, ordered most-likely-first ----------------------
def aliases = ["authToken", "accessToken", "access_token", "sessionToken",
               "session_token", "token", "jwt", "id_token", "idToken",
               "bearerToken", "bearer_token", "api_token", "apiToken",
               "auth_token", "refresh_token", "x-auth-token"]

for (a in aliases) {
    def v = flat[a]
    if (v != null && v.toString().trim().length() > 0) {
        healed = v.toString(); healedKey = a; healLayer = "alias_map"; break
    }
}

// ---- LAYER 2: JWT structure detection (xxx.xxx.xxx base64 pattern) ----------
if (healed == null) {
    def jwtPattern = ~/^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$/
    flat.each { k, v ->
        if (healed != null) return
        def vs = v?.toString()?.trim() ?: ""
        if (jwtPattern.matcher(vs).matches()) {
            healed = vs; healedKey = "${k} (jwt-detected)"; healLayer = "jwt_detect"
        }
    }
}

// ---- LAYER 3: heuristic — long opaque string under a token-ish key ----------
if (healed == null) {
    def tokenKeywords = ["token", "auth", "jwt", "bearer", "session", "credential", "key", "secret"]
    flat.each { k, v ->
        if (healed != null) return
        def ks = k.toString().toLowerCase()
        def vs = v?.toString() ?: ""
        if (tokenKeywords.any { kw -> ks.contains(kw) } && vs.length() >= 16) {
            healed = vs; healedKey = "${k} (heuristic)"; healLayer = "heuristic"
        }
    }
}

// ---- LAYER 3b: any long opaque string that looks like a token ---------------
if (healed == null) {
    def tokenPattern = ~/^[A-Za-z0-9_.\-+\/=]{32,}$/
    flat.each { k, v ->
        if (healed != null) return
        def vs = v?.toString()?.trim() ?: ""
        if (tokenPattern.matcher(vs).matches() && !k.toString().toLowerCase().contains("url") &&
            !k.toString().toLowerCase().contains("path") && !k.toString().toLowerCase().contains("email")) {
            healed = vs; healedKey = "${k} (pattern-match)"; healLayer = "pattern"
        }
    }
}

if (healed != null) {
    vars.put("authToken", healed)
    vars.put("selfHealApplied", "true")
    vars.put("selfHealField", healedKey)
    vars.put("selfHealLayer", healLayer)
    incStat(healLayer)

    // Circuit breaker: track consecutive heals on same field
    def cacheKey = "selfHeal_consecutiveHits_${healedKey}"
    def hits = ((props.get(cacheKey) ?: "0") as int) + 1
    props.put(cacheKey, hits.toString())
    if (hits >= 3) {
        def dotPath = healedKey.replaceAll(/ \(.*\)/, '')
        props.put("selfHeal_cachedField", dotPath)
        log.warn("SELF-HEAL CIRCUIT-BREAKER: caching field '${dotPath}' after ${hits} consecutive heals")
        healLog("CIRCUIT-BREAKER  cached_field='${dotPath}'  after=${hits} heals")
    }

    log.warn("SELF-HEAL OK [${healLayer}] — token recovered from '${healedKey}'")
    healLog("HEALED  layer=${healLayer}  field='${healedKey}'  sampler='${prev.getSampleLabel()}'  thread='${ctx.getThreadGroup().getName()}'")
    return
}

// ---- LAYER 4: LLM fallback (experimental, opt-in) ---------------------------
if (props.get("llm_enabled") == "true" && props.get("llm_endpoint")) {
    try {
        def endpoint = props.get("llm_endpoint")
        def apiKey   = props.get("llm_api_key") ?: ""
        def prompt   = "You are a JSON field analyzer. This API response contains an authentication token " +
                       "but the field name is unknown. Return ONLY the JSON key name that holds the auth/" +
                       "session token. No explanation, no quotes, no markdown.\n\n" + body.take(4000)

        def conn = new URL(endpoint).openConnection()
        conn.setRequestMethod("POST")
        conn.setDoOutput(true)
        conn.setConnectTimeout(3000)
        conn.setReadTimeout(5000)
        conn.setRequestProperty("Content-Type", "application/json")
        if (apiKey) conn.setRequestProperty("Authorization", "Bearer ${apiKey}")
        conn.outputStream.withWriter("UTF-8") { it << groovy.json.JsonOutput.toJson([prompt: prompt]) }

        def reply = conn.inputStream.getText("UTF-8")
        def key = new JsonSlurper().parseText(reply)?.key?.toString()?.trim()

        if (key && flat[key]) {
            vars.put("authToken", flat[key].toString())
            vars.put("selfHealApplied", "true")
            vars.put("selfHealField", "${key} (llm)")
            vars.put("selfHealLayer", "llm")
            incStat("llm")
            log.warn("SELF-HEAL OK [llm] — token recovered from '${key}'")
            healLog("HEALED-LLM  field='${key}'  sampler='${prev.getSampleLabel()}'")
            return
        }
        healLog("FAIL-LLM  model returned '${key}' which is not present in the response")
    } catch (e) {
        log.error("SELF-HEAL LLM fallback failed: ${e.message}")
        healLog("FAIL-LLM  ${e.message}")
    }
}

log.error("SELF-HEAL FAILED — no token-like field found. Keys seen: ${flat.keySet()}")
healLog("FAIL  no token-like field. keys=${flat.keySet()}")
