from flask import Flask, render_template, jsonify
import psutil
import sqlite3
from datetime import datetime
from anomaly import check_metric

app = Flask(__name__)

previous_anomaly = None

def init_db():

    conn = sqlite3.connect("monitoring.db")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            cpu REAL,
            memory REAL,
            disk REAL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            resource TEXT,
            value REAL
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():

    return render_template("index.html")


@app.route("/api/system")
def system_info():

    # Get current values
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent


    # Check against previous history
    cpu_anomaly = check_metric("cpu", cpu)
    memory_anomaly = check_metric("memory", memory)
    disk_anomaly = check_metric("disk", disk)


    # Determine anomaly
    anomaly = (
        cpu_anomaly
        or memory_anomaly
        or disk_anomaly
    )


    if cpu_anomaly:

        anomaly_type = "cpu"

    elif memory_anomaly:

        anomaly_type = "memory"

    elif disk_anomaly:

        anomaly_type = "disk"

    else:

        anomaly_type = None

    global previous_anomaly

    if anomaly_type and anomaly_type != previous_anomaly:

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        value = {
            "cpu": cpu,
            "memory": memory,
            "disk": disk
        }[anomaly_type]

        conn = sqlite3.connect("monitoring.db")

        conn.execute("""
            INSERT INTO anomaly_logs
            (timestamp, resource, value)
            VALUES (?, ?, ?)
        """, (
            timestamp,
            anomaly_type,
            value
        ))

        conn.commit()
        conn.close()


    previous_anomaly = anomaly_type


    # Save current measurement
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = sqlite3.connect("monitoring.db")

    conn.execute("""
        INSERT INTO system_metrics
        (timestamp, cpu, memory, disk)
        VALUES (?, ?, ?, ?)
    """, (
        timestamp,
        cpu,
        memory,
        disk
    ))

    conn.commit()
    conn.close()


    return jsonify({

        "cpu": cpu,

        "memory": memory,

        "disk": disk,

        "anomaly": anomaly,

        "anomaly_type": anomaly_type

    })


@app.route("/api/history")
def history():

    conn = sqlite3.connect("monitoring.db")

    rows = conn.execute("""
        SELECT timestamp, cpu, memory, disk
        FROM system_metrics
        ORDER BY id DESC
        LIMIT 30
    """).fetchall()

    conn.close()

    rows.reverse()


    return jsonify([

        {
            "timestamp": row[0],
            "cpu": row[1],
            "memory": row[2],
            "disk": row[3]
        }

        for row in rows

    ])

@app.route("/api/anomalies")
def anomalies():

    conn = sqlite3.connect("monitoring.db")

    rows = conn.execute("""
        SELECT timestamp, resource, value
        FROM anomaly_logs
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return jsonify([
        {
            "timestamp": row[0],
            "resource": row[1],
            "value": row[2]
        }
        for row in rows
    ])

if __name__ == "__main__":

    init_db()

    app.run(debug=True)