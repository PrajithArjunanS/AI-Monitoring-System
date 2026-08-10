from flask import Flask, render_template, jsonify
import psutil

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/system")
def system_info():
    return jsonify({
        "cpu": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent
    })

if __name__ == "__main__":
    app.run(debug=True)