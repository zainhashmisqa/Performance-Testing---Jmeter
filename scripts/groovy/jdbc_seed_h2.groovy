/* ===========================================================================
 * CONCEPT 8 (deck 8) — JDBC proof: seed H2 embedded database.
 *
 * Called by proof-jdbc.ps1 setUp to populate the student_courseenrollment
 * table with realistic data matching the SBA Academy API responses.
 * H2 is pure Java — no external database server needed.
 * =========================================================================== */

import groovy.sql.Sql

def dbUrl = props.get("db_url") ?: "jdbc:h2:file:./results/proof-jdbc;AUTO_SERVER=TRUE"
def sql = Sql.newInstance(dbUrl, props.get("db_user") ?: "sa", props.get("db_password") ?: "", "org.h2.Driver")

sql.execute('''
    CREATE TABLE IF NOT EXISTS student_courseenrollment (
        id INT PRIMARY KEY,
        user_id INT,
        course_id INT,
        course_slug VARCHAR(100),
        status VARCHAR(20),
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

def enrollments = [
    [63, 5, 76, 've', 'completed'],
    [62, 5, 75, 'test-course-01', 'completed'],
    [60, 5, 71, 'basel-iii', 'confirmed'],
    [59, 5, 69, 'compliance-basics', 'completed'],
    [58, 5, 68, 'risk-management', 'confirmed'],
    [55, 5, 56, 'aml-certification', 'completed'],
    [50, 5, 40, 'kyc-fundamentals', 'completed']
]

enrollments.each { e ->
    sql.execute('''
        MERGE INTO student_courseenrollment (id, user_id, course_id, course_slug, status)
        VALUES (?, ?, ?, ?, ?)
    ''', e)
}

log.info("JDBC PROOF: Seeded ${enrollments.size()} enrollment rows into H2 at ${dbUrl}")
sql.close()
SampleResult.setIgnore()
