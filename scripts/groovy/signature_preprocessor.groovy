/* ===========================================================================
 * CONCEPT 6 — JSR223 Scripting  (Tier A)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PreProcessor on the Certificates sampler (S07).
 *
 * Signs the request with HMAC-SHA256 to demonstrate custom cryptographic
 * logic that no built-in JMeter element can do: canonical request fingerprint
 * + nonce + timestamp, all per-request.
 *
 * Produces: ${signature}  ${nonce}  ${requestTs}
 * =========================================================================== */

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

def secret  = props.get("hmac_secret") ?: "azm-test-secret-not-a-real-key"
def nonce   = UUID.randomUUID().toString()
def ts      = System.currentTimeMillis().toString()

def method  = "GET"
def path    = sampler.getPath() ?: "/api/certificates/"
def userId  = vars.get("userId") ?: "UNKNOWN"

// CONCEPT 15 support: -Jforce_fail=true injects a deliberately invalid path so
// the retry loop has something real to retry. Used only to PROVE retry works.
if (props.get("force_fail") == "true" && (vars.get("tries") ?: "0").toInteger() < 2) {
    path = "/api/certificates/FORCED_FAILURE/"
    sampler.setPath(path)
}

def fingerprintMap = [
    method    : method,
    path      : path,
    user_id   : userId,
    nonce     : nonce,
    timestamp : ts,
    channel   : "load-test",
    env       : props.get("env") ?: "staging"
]

def canonical = fingerprintMap.sort { it.key }.collect { k, v -> "${k}=${v}" }.join("&")

Mac mac = Mac.getInstance("HmacSHA256")
mac.init(new SecretKeySpec(secret.getBytes("UTF-8"), "HmacSHA256"))
def signature = mac.doFinal(canonical.getBytes("UTF-8")).encodeHex().toString()

vars.put("signature", signature)
vars.put("nonce", nonce)
vars.put("requestTs", ts)

if (log.isDebugEnabled()) {
    log.debug("Signed ${method} ${path} for user=${userId} sig=${signature.take(12)}...")
}
