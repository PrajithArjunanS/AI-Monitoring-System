"""Read-only database checks for process-level monitoring."""

import sqlite3


def main():
    conn = sqlite3.connect("monitoring.db")

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    print("Tables:", ", ".join(tables))

    print("system_metrics:", conn.execute(
        "SELECT COUNT(*) FROM system_metrics"
    ).fetchone()[0])
    print("anomaly_logs:", conn.execute(
        "SELECT COUNT(*) FROM anomaly_logs"
    ).fetchone()[0])
    print("process_metrics:", conn.execute(
        "SELECT COUNT(*) FROM process_metrics"
    ).fetchone()[0])

    print("\nRecent process metrics:")
    rows = conn.execute("""
        SELECT id, timestamp, pid, process_name, create_time, cpu, memory
        FROM process_metrics
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    for row in rows:
        print(row)

    matching_timestamps = conn.execute("""
        SELECT COUNT(*)
        FROM process_metrics AS process
        WHERE EXISTS (
            SELECT 1
            FROM system_metrics AS system
            WHERE system.timestamp = process.timestamp
        )
    """).fetchone()[0]
    print("\nProcess rows with matching system timestamps:", matching_timestamps)

    conn.close()


if __name__ == "__main__":
    main()
