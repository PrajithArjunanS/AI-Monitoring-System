from flask import Flask, render_template, jsonify
import psutil
import sqlite3
from datetime import datetime
from anomaly import check_metric

app = Flask(__name__)

previous_anomaly = None
previous_disk_io = {}
PROCESS_COLLECTION_INTERVAL = 6
TOP_PROCESSES = 10
last_process_snapshot_at = None
process_cpu_trackers = {}

PROCESS_INSPECTION_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    PermissionError,
    OSError,
)


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


def sample_process_usage():
    """Collect non-blocking CPU and memory samples for running processes."""
    global process_cpu_trackers

    sampled_processes = []
    active_trackers = {}

    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            pid = process.info["pid"]

            if pid == 0:
                continue

            create_time = process.info["create_time"]
            process_key = (pid, create_time)
            tracker = process_cpu_trackers.get(process_key)

            if tracker is None:
                # The first non-blocking call establishes psutil's CPU baseline.
                tracker = psutil.Process(pid)
                tracker.cpu_percent(interval=None)
                cpu_percent = 0.0
            else:
                cpu_percent = tracker.cpu_percent(interval=None)

            active_trackers[process_key] = tracker
            sampled_processes.append({
                "pid": pid,
                "process_name": process.info["name"] or "Unknown process",
                "create_time": create_time,
                "cpu": cpu_percent,
                "memory": process.memory_percent(),
            })
        except PROCESS_INSPECTION_ERRORS:
            continue

    # Drop exited processes so PID reuse cannot inherit an old CPU baseline.
    process_cpu_trackers = active_trackers

    return sampled_processes


def select_top_processes(processes):
    """Return the top CPU and memory consumers, deduplicated by process instance."""
    top_cpu = sorted(processes, key=lambda process: process["cpu"], reverse=True)
    top_memory = sorted(
        processes,
        key=lambda process: process["memory"],
        reverse=True,
    )

    selected = {}
    for process in top_cpu[:TOP_PROCESSES] + top_memory[:TOP_PROCESSES]:
        selected[(process["pid"], process["create_time"])] = process

    return list(selected.values())


def save_process_snapshot(timestamp, processes):
    """Persist a limited process snapshot at the configured collection interval."""
    global last_process_snapshot_at

    current_time = datetime.now().timestamp()

    if last_process_snapshot_at is None:
        # Allow one collection interval for non-blocking CPU samples to warm up.
        last_process_snapshot_at = current_time
        return

    if current_time - last_process_snapshot_at < PROCESS_COLLECTION_INTERVAL:
        return

    last_process_snapshot_at = current_time
    selected_processes = select_top_processes(processes)

    if not selected_processes:
        return

    conn = sqlite3.connect("monitoring.db")
    conn.executemany(
        """
        INSERT INTO process_metrics
        (timestamp, pid, process_name, create_time, cpu, memory)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                timestamp,
                process["pid"],
                process["process_name"],
                process["create_time"],
                process["cpu"],
                process["memory"],
            )
            for process in selected_processes
        ],
    )
    conn.commit()
    conn.close()

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            pid INTEGER,
            process_name TEXT,
            create_time REAL,
            cpu REAL,
            memory REAL
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_process_metrics_timestamp
        ON process_metrics(timestamp)
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
    process_snapshot = sample_process_usage()

    # Reuse this timestamp for both the system metric and its process snapshot.
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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

    save_process_snapshot(timestamp, process_snapshot)

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


@app.route("/api/processes")
def processes():

    conn = sqlite3.connect("monitoring.db")

    rows = conn.execute("""
        SELECT timestamp, pid, process_name, create_time, cpu, memory
        FROM process_metrics
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return jsonify([
        {
            "timestamp": row[0],
            "pid": row[1],
            "process_name": row[2],
            "create_time": row[3],
            "cpu": row[4],
            "memory": row[5],
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
