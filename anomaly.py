import statistics
import sqlite3


def detect_anomaly(values, new_value):

    if len(values) < 5:
        return False

    mean = statistics.mean(values)

    std = statistics.stdev(values)

    if std == 0:
        return False

    z_score = abs((new_value - mean) / std)

    return z_score > 3


def get_history(metric, limit=30):

    conn = sqlite3.connect("monitoring.db")

    rows = conn.execute(
        f"""
        SELECT {metric}
        FROM system_metrics
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()

    return [row[0] for row in rows]


def check_metric(metric, current_value):

    values = get_history(metric)

    return detect_anomaly(values, current_value)