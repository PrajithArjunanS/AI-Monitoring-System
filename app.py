from flask import Flask, render_template, jsonify
import psutil
import sqlite3
from datetime import datetime
from anomaly import check_metric

app = Flask(__name__)

previous_anomaly = None
previous_disk_io = {}


def get_top_cpu_process():
    """Return the process using the most CPU since the last sample."""
    top_process = None

    for process in psutil.process_iter(["pid", "name"]):
        if process.info["pid"] == 0:
            continue

        try:
            cpu_percent = process.cpu_percent(interval=None)
            if top_process is None or cpu_percent > top_process["cpu_percent"]:
                top_process = {
                    "name": process.info["name"] or "Unknown process",
                    "pid": process.info["pid"],
                    "cpu_percent": cpu_percent,
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return top_process


def get_top_memory_process():
    """Return the process holding the largest amount of physical memory."""
    top_process = None

    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        if process.info["pid"] == 0:
            continue

        try:
            memory_bytes = process.info["memory_info"].rss
            if top_process is None or memory_bytes > top_process["memory_bytes"]:
                top_process = {
                    "name": process.info["name"] or "Unknown process",
                    "pid": process.info["pid"],
                    "memory_bytes": memory_bytes,
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return top_process


def get_top_disk_process():
    """Return the process with the greatest disk I/O since the last sample."""
    global previous_disk_io

    top_process = None
    current_disk_io = {}

    for process in psutil.process_iter(["pid", "name"]):
        if process.info["pid"] == 0:
            continue

        try:
            io_counters = process.io_counters()
            total_bytes = io_counters.read_bytes + io_counters.write_bytes
            pid = process.info["pid"]
            current_disk_io[pid] = total_bytes
            io_delta = max(0, total_bytes - previous_disk_io.get(pid, total_bytes))

            if top_process is None or io_delta > top_process["io_delta"]:
                top_process = {
                    "name": process.info["name"] or "Unknown process",
                    "pid": pid,
                    "io_delta": io_delta,
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    previous_disk_io = current_disk_io

    if top_process and top_process["io_delta"] == 0:
        return None

    return top_process

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
            value REAL,
            process_name TEXT
        )
    """)

    columns = [row[1] for row in conn.execute("PRAGMA table_info(anomaly_logs)")]
    if "process_name" not in columns:
        conn.execute("ALTER TABLE anomaly_logs ADD COLUMN process_name TEXT")

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
    top_cpu_process = get_top_cpu_process()
    top_memory_process = get_top_memory_process()
    top_disk_process = get_top_disk_process()


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

        process_name = None
        if anomaly_type == "cpu" and top_cpu_process:
            process_name = (
                f'{top_cpu_process["name"]} '
                f'(PID {top_cpu_process["pid"]}, '
                f'{top_cpu_process["cpu_percent"]:.1f}% process CPU)'
            )

        conn = sqlite3.connect("monitoring.db")

        conn.execute("""
            INSERT INTO anomaly_logs
            (timestamp, resource, value, process_name)
            VALUES (?, ?, ?, ?)
        """, (
            timestamp,
            anomaly_type,
            value,
            process_name
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

        "anomaly_type": anomaly_type,

        "top_processes": {
            "cpu": top_cpu_process,
            "memory": top_memory_process,
            "disk": top_disk_process,
        }

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
        SELECT timestamp, resource, value, process_name
        FROM anomaly_logs
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return jsonify([
        {
            "timestamp": row[0],
            "resource": row[1],
            "value": row[2],
            "process_name": row[3]
        }
        for row in rows
    ])


@app.route("/api/anomalies/clear", methods=["POST"])
def clear_anomalies():

    conn = sqlite3.connect("monitoring.db")
    conn.execute("DELETE FROM anomaly_logs")
    conn.commit()
    conn.close()

    return jsonify({"success": True})

if __name__ == "__main__":

    init_db()

    app.run(debug=True)
