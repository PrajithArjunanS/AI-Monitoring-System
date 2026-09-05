import sqlite3
import csv
import os

DB_PATH = "monitoring.db"
DATA_DIR = "data"

# Create data folder if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()


def export_table(table_name):
    output_file = os.path.join(DATA_DIR, f"{table_name}.csv")

    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    # Get column names automatically
    columns = [description[0] for description in cursor.description]

    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow(columns)
        writer.writerows(rows)

    print(f"{table_name}: {len(rows)} records exported → {output_file}")


# Export tables
export_table("system_metrics")
export_table("process_metrics")
export_table("anomaly_logs")

conn.close()

print("\nExport completed successfully.")