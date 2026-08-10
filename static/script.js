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


getSystemData();

setInterval(
    getSystemData,
    2000
);