/* ===========================================================================
 * CONCEPT 17 — Self-Healing Statistics Reporter  (Tier B)
 * ---------------------------------------------------------------------------
 * Placement: JSR223 Sampler in the tearDown Thread Group, runs once at end.
 *
 * Aggregates all healing statistics collected during the run and writes a
 * summary to results/self-heal-summary.json + logs to JMeter output.
 *
 * This data feeds the concept-mapping report's evidence section.
 * =========================================================================== */

import groovy.json.JsonOutput

def stats = [:]

// Collect self-heal layer stats
["alias_map", "jwt_detect", "heuristic", "pattern", "llm", "circuit_breaker"].each { layer ->
    def key = "selfHeal_${layer}_count"
    def count = (props.get(key) ?: "0") as int
    if (count > 0) stats[layer] = count
}

// Correlation guardian stats
def guardianHeals = (props.get("corrGuard_totalHeals") ?: "0") as int
if (guardianHeals > 0) stats["correlation_guardian"] = guardianHeals

// Circuit breaker cached field
def cached = props.get("selfHeal_cachedField")
if (cached) stats["circuit_breaker_field"] = cached

// Structure change detection
def fingerprint = props.get("selfHeal_lastFingerprint")
if (fingerprint) stats["last_response_structure"] = fingerprint.take(500)

def totalHeals = stats.findAll { k, v -> v instanceof Integer }.values().sum() ?: 0

def summary = [
    run_timestamp : new Date().format('yyyy-MM-dd HH:mm:ss'),
    total_heals   : totalHeals,
    layers_hit    : stats,
    verdict       : totalHeals > 0 ? "SELF-HEALING ACTIVE — ${totalHeals} field(s) recovered" :
                                     "NO HEALING NEEDED — all extractions matched on first try"
]

// Write summary file
try {
    def dir = new File("results")
    if (!dir.exists()) dir.mkdirs()
    new File(dir, "self-heal-summary.json").text = JsonOutput.prettyPrint(JsonOutput.toJson(summary))
} catch (ignored) {}

// Log to JMeter output
log.info("=" * 60)
log.info("  SELF-HEALING SUMMARY")
log.info("=" * 60)
log.info("  Total heals: ${totalHeals}")
stats.each { k, v -> log.info("  ${k}: ${v}") }
log.info("  Verdict: ${summary.verdict}")
log.info("=" * 60)

// Set as variable for HTML report custom summary
vars.put("selfHealSummary", JsonOutput.toJson(summary))
