const history = {
    cpu: [],
    memory: [],
    disk: []
};

const MAX_POINTS = 40;


function updateGauge(id, value) {

    const length = 251.3;

    const offset =
        length - (length * value / 100);

    document.getElementById(id)
        .style.strokeDashoffset = offset;
}


function getStatus(value) {

    if (value < 50) {
        return "Low Usage";
    }

    if (value < 80) {
        return "Moderate Usage";
    }

    return "High Usage";
}


function updateMetric(name, value) {

    document.getElementById(name)
        .textContent =
        value.toFixed(1) + "%";

    updateGauge(
        name + "-gauge",
        value
    );

    document.getElementById(name + "-status")
        .textContent =
        getStatus(value);

    document.getElementById(name + "-activity")
        .textContent =
        value.toFixed(1) + "%";
}


function updateProcessAttribution(processes) {

    ["cpu", "memory", "disk"].forEach(resource => {

        const process = processes[resource];
        const element = document.getElementById(resource + "-process");

        element.textContent = process
            ? `${process.name} · PID ${process.pid}`
            : resource === "disk"
                ? "No recent disk activity"
                : "Unavailable";

    });

}


function updateHistory(name, value) {

    history[name].push(value);

    if (history[name].length > MAX_POINTS) {
        history[name].shift();
    }
}


function createSparkline(values) {

    const width = 600;
    const height = 70;

    if (values.length === 0) {
        return "";
    }

    if (values.length === 1) {
        return `${width / 2},${height / 2}`;
    }

    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);

    let range = maxValue - minValue;

    if (range < 2) {
        range = 2;
    }

    const padding = range * 0.25;

    const min = minValue - padding;
    const max = maxValue + padding;

    return values.map((value, index) => {

        const x =
            (index / (values.length - 1)) * width;

        const y =
            height -
            ((value - min) / (max - min)) * height;

        return `${x},${y}`;

    }).join(" ");
}


function updateChart() {

    document.getElementById("cpu-line")
        .setAttribute(
            "points",
            createSparkline(history.cpu)
        );

    document.getElementById("memory-line")
        .setAttribute(
            "points",
            createSparkline(history.memory)
        );

    document.getElementById("disk-line")
        .setAttribute(
            "points",
            createSparkline(history.disk)
        );
}


function updateAnomalyStatus(data) {

    const onlineStatus =
        document.querySelector(".online");

    const onlineText =
        onlineStatus.lastChild;


    const cpuStatus =
        document.getElementById("cpu-status");

    const memoryStatus =
        document.getElementById("memory-status");

    const diskStatus =
        document.getElementById("disk-status");


    document
        .querySelectorAll(".metric-card")
        .forEach(card => {

            card.classList.remove("anomaly");

        });


    if (data.anomaly) {

        onlineStatus.classList.add(
            "anomaly-online"
        );

        onlineText.textContent =
            " Anomaly Detected";


        if (data.anomaly_type === "cpu") {

            cpuStatus.textContent =
                "Anomaly Detected";

            cpuStatus
                .closest(".metric-card")
                .classList.add("anomaly");

        }


        if (data.anomaly_type === "memory") {

            memoryStatus.textContent =
                "Anomaly Detected";

            memoryStatus
                .closest(".metric-card")
                .classList.add("anomaly");

        }


        if (data.anomaly_type === "disk") {

            diskStatus.textContent =
                "Anomaly Detected";

            diskStatus
                .closest(".metric-card")
                .classList.add("anomaly");

        }

    }

    else {

        onlineStatus.classList.remove(
            "anomaly-online"
        );

        onlineText.textContent =
            " System Online";


        cpuStatus.textContent =
            getStatus(
                parseFloat(
                    document.getElementById("cpu")
                        .textContent
                )
            );

        memoryStatus.textContent =
            getStatus(
                parseFloat(
                    document.getElementById("memory")
                        .textContent
                )
            );

        diskStatus.textContent =
            getStatus(
                parseFloat(
                    document.getElementById("disk")
                        .textContent
                )
            );

    }
}


async function loadHistory() {

    try {

        const response =
            await fetch("/api/history");

        const data =
            await response.json();


        data.forEach(item => {

            history.cpu.push(item.cpu);

            history.memory.push(item.memory);

            history.disk.push(item.disk);

        });


        history.cpu =
            history.cpu.slice(-MAX_POINTS);

        history.memory =
            history.memory.slice(-MAX_POINTS);

        history.disk =
            history.disk.slice(-MAX_POINTS);


        updateChart();

    }

    catch (error) {

        console.log(
            "Unable to load monitoring history."
        );

    }
}


async function getSystemData() {

    try {

        const response =
            await fetch("/api/system");

        const data =
            await response.json();


        const cpu = data.cpu;
        const memory = data.memory;
        const disk = data.disk;


        updateMetric(
            "cpu",
            cpu
        );

        updateMetric(
            "memory",
            memory
        );

        updateMetric(
            "disk",
            disk
        );


        updateProcessAttribution(data.top_processes);

        updateHistory(
            "cpu",
            cpu
        );

        updateHistory(
            "memory",
            memory
        );

        updateHistory(
            "disk",
            disk
        );


        updateChart();


        updateAnomalyStatus(data);


        document.getElementById("updated")
            .textContent =
            new Date().toLocaleTimeString();

    }

    catch (error) {

        console.log(
            "Unable to fetch system data."
        );

    }
}


async function startMonitoring() {

    await loadHistory();

    await getSystemData();

    setInterval(
        getSystemData,
        2000
    );

}


async function loadAnomalies() {

    try {

        const response =
            await fetch("/api/anomalies");

        const data =
            await response.json();


        const list =
            document.getElementById(
                "anomaly-list"
            );

        const count =
            document.getElementById(
                "anomaly-count"
            );


        count.textContent =
            data.length;


        if (data.length === 0) {

            list.innerHTML = `
                <div class="no-anomalies">
                    No anomalies detected
                </div>
            `;

            return;
        }


        list.innerHTML =
            data.map(item => {

                const processDetails = item.resource === "cpu" && item.process_name
                    ? `
                        <div class="anomaly-process">
                            <span class="anomaly-process-name">${escapeHtml(item.process_name)}</span>
                        </div>
                    `
                    : "";

                return `
                    <div class="anomaly-item">

                        <div class="anomaly-item-header">

                            <div class="anomaly-resource">

                                <span class="anomaly-dot"></span>

                                ${item.resource.toUpperCase()}

                            </div>

                            <span class="anomaly-value">
                                ${item.value.toFixed(1)}%
                            </span>

                        </div>

                        <div class="anomaly-time">
                            ${item.timestamp}
                        </div>

                        ${processDetails}

                    </div>
                `;

            }).join("");

    }

    catch (error) {

        console.log(
            "Unable to load anomaly history."
        );

    }
}


function escapeHtml(value) {

    const element = document.createElement("div");
    element.textContent = value;
    return element.innerHTML;

}


async function clearAnomalies() {

    const button = document.getElementById("clear-anomalies");
    button.disabled = true;

    try {

        const response = await fetch("/api/anomalies/clear", {
            method: "POST"
        });

        if (!response.ok) {
            throw new Error("Unable to clear anomaly history.");
        }

        await loadAnomalies();

    }

    catch (error) {

        console.log("Unable to clear anomaly history.");

    }

    finally {

        button.disabled = false;

    }

}


startMonitoring();

loadAnomalies();

document.getElementById("clear-anomalies").addEventListener(
    "click",
    clearAnomalies
);

setInterval(
    loadAnomalies,
    2000
);
