function adjustColor(color, amount) {
    return '#' + color.replace(/^#/, '').replace(/../g, color =>
        ('0' + Math.min(255, Math.max(0, parseInt(color, 16) + amount)).toString(16)).slice(-2)
    );
}

function buildDashboard(dash_data, elementId) {
    const defaultColor = '#4264e3';
    const colorVariation = 2 * 50; // variação da cor
    const traceColor = adjustColor(defaultColor, colorVariation);

    const data = {
        ...dash_data,
        type: 'bar',
        marker: {
            color: traceColor,
            line: {
                width: 0.5
            }
        }
    }

    const layout = {
        title: dash_data.title,
        font: { size: 11 },
    };

    const config = { responsive: true }
    Plotly.newPlot(elementId, [data], layout, config);
}

function initDashboards(data) {
    const parent = document.getElementById('dashboards');

    data.forEach((item, index) => {
        const dash = document.createElement('div')
        dash.className = 'dash box'
        dash.id = `dash-${index}`
        parent.appendChild(dash);
        buildDashboard(item, dash.id);
    });
}

function initCounters(counters) {
    const container = document.getElementById('counters');

    const existingBoxes = container.querySelectorAll('.counter-box');
    existingBoxes.forEach(box => box.remove());

    counters.forEach((count, index) => {
        const box = document.createElement('div');
        box.className = 'box counter-box';

        const counter = document.createElement('div');
        counter.className = 'counter';

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = count.title;

        const value = document.createElement('div');
        value.className = 'value';
        value.id = `counter-${index}`; // Add unique ID for updating later
        value.textContent = count.value.toLocaleString('pt-BR');

        counter.appendChild(title);
        counter.appendChild(value);
        box.appendChild(counter);

        container.insertBefore(box, document.querySelector('.box-large'));
    });
}

async function init() {
    const counters = window.counters;
    const dashboards = window.dashboards;    
    initCounters(counters);
    initDashboards(dashboards);
}

init();