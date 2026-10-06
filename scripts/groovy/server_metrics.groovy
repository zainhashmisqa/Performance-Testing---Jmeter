/* ===========================================================================
 * CONCEPT 8 (deck 13) — Monitoring & Reporting: SERVER-SIDE metrics
 * ---------------------------------------------------------------------------
 * Placement: JSR223 PostProcessor on "MON Server metrics".
 *
 * WHY THIS MATTERS MORE THAN IT LOOKS
 * Client-side numbers tell you THAT checkout is slow. They can never tell you
 * WHY. Without CPU, memory and queue depth from the application under test,
 * "name the bottleneck" is an assertion, not a diagnosis - and a reviewer is
 * right to discount it.
 *
 * The standard JMeter answer is the PerfMon plugin plus ServerAgent on the
 * target host. That needs a plugin install and an agent running on someone
 * else's box. Polling the application's own metrics endpoint needs neither and
 * works against anything that exposes one (Spring Actuator, /metrics,
 * Prometheus text, a custom health route). Point path_metrics at whatever the
 * real target exposes.
 *
 * Values are written into variables so the Backend Listener ships them to
 * InfluxDB alongside the response times, which is what lets you overlay
 * "checkout p95" against "server CPU" on one Grafana panel - the single most
 * useful chart in a performance report.
 * =========================================================================== */

import groovy.json.JsonSlurper

if (!prev.isSuccessful()) {
    log.warn("Server metrics endpoint unreachable (rc=${prev.getResponseCode()}). " +
             "Bottleneck analysis will be client-side only.")
    return
}

try {
    def m = new JsonSlurper().parseText(prev.getResponseDataAsString())

    // Tolerate several common shapes rather than assuming one vendor's schema.
    def cpu  = m.cpu_percent ?: m.cpu ?: m.system_cpu_usage ?: m.processCpuLoad
    def mem  = m.memory_mb ?: m.memory ?: m.jvm_memory_used
    def act  = m.active_requests ?: m.active ?: m.threads_busy
    def rows = m.enrollment_rows

    if (cpu  != null) vars.put("srv_cpu",    cpu.toString())
    if (mem  != null) vars.put("srv_mem_mb", mem.toString())
    if (act  != null) vars.put("srv_active", act.toString())
    if (rows != null) vars.put("srv_rows",   rows.toString())

    // Append a timeseries the report can chart even with no Grafana available.
    def f = new File("results")
    if (!f.exists()) f.mkdirs()
    new File(f, "server-metrics.csv").append(
        [System.currentTimeMillis(), cpu ?: "", mem ?: "", act ?: "", rows ?: ""]
            .join(",") + System.lineSeparator())

    // Saturation warning while the run is still going, not after the fact.
    if (cpu != null && (cpu as Double) > 85.0) {
        log.warn("SERVER SATURATION: cpu=${cpu}% active=${act} - response-time " +
                 "degradation from here is the server, not the script.")
    }
} catch (e) {
    log.error("Could not parse server metrics: ${e.message}")
}
