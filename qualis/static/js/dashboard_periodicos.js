async function getJson(api_url) {
  let formData = new FormData(document.getElementById('form_filters'));
  let urlParams = new URLSearchParams(formData);
  let url = api_url + '?' + urlParams.toString();
  const response = await fetch(url);
  const data = await response.json();
  return data;
}

function adjustColor(color, amount) {
  return '#' + color.replace(/^#/, '').replace(/../g, color =>
    ('0' + Math.min(255, Math.max(0, parseInt(color, 16) + amount)).toString(16)).slice(-2)
  );
}

function getLegendLayout(chartType) {
  if (window.innerWidth > 768) {
    return {};
  }

  return {
    legend: {
      orientation: 'h',
      x: 0.5,
      xanchor: 'center',
      y: 1.10,
      yanchor: 'top',
      font: {
        size: 10,
      },
      itemwidth: 60,
    },
    margin: {
      t: 52,
      r: 12,
      b: chartType === 'pais' ? 88 : 20,
      l: 44,
    },
  };
}

function initQualiDash(data) {
  const dataQuali = data.qualis_dash;
  const defaultColor = '#4264e3';

  const traces = dataQuali.traces.map((trace, index) => {
    const colorVariation = (index + 1) * 50; // variação da cor
    const traceColor = adjustColor(defaultColor, colorVariation);

    return {
      type: 'bar',
      name: trace.name,
      marker: {
        color: traceColor,
      },
      x: trace.x,
      y: trace.y,
    }
  })

  const layout = {
    title: {
      text: window.innerWidth > 768 ? 'Por Qualis' : 'Qualis',
      x: 0.5,
      xanchor: 'center',
      y: window.innerWidth > 768 ? undefined : 0.99,
      pad: {
        t: 0,
        b: 2,
      },
    },
    font: { size: 12 },
    barmode: 'stack',
    xaxis: {
      automargin: true,
      title: {
        text: window.innerWidth > 768 ? 'Qualis' : '',
        font: {
          size: 12,
          color: '#7f7f7f'
        }
      },
    },
    yaxis: {
      title: {
        text: 'Frequência',
        font: {
          size: 12,
          color: '#7f7f7f'
        }
      }
    }
  };

  Object.assign(layout, getLegendLayout('qualis'));

  const config = { responsive: true, showTips: false }
  Plotly.newPlot('qualis-dash', traces, layout, config);
}

function initPaisDash(data) {
  const paisData = data.pais_dash;
  const defaultColor = '#4769e5';

  const traces = paisData.traces.map((trace, index) => {
    const colorVariation = (index + 1) * 50; // variação da cor
    const traceColor = adjustColor(defaultColor, colorVariation);

    return {
      type: 'bar',
      name: trace.name,
      marker: {
        color: traceColor,
      },
      x: trace.x,
      y: trace.y,
    }
  })

  const layout = {
    title: {
      text: window.innerWidth > 768 ? 'Por Países' : 'Países',
      x: 0.5,
      xanchor: 'center',
      y: window.innerWidth > 768 ? undefined : 0.99,
      pad: {
        t: 0,
        b: 2,
      },
    },
    barmode: 'stack',
    font: { size: 12 },
    xaxis: {
      automargin: true,
      tickangle: 90,
    },
  };

  Object.assign(layout, getLegendLayout('pais'));

  const config = { responsive: true, showTips: false }
  Plotly.newPlot('pais-dash', traces, layout, config);
}

function initCounters(data) {
  const container = document.getElementById('counters');
  const counters = data.counters;

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

async function initDashboards() {
  const data = await getJson(window.url_pesquisa);
  const dashboards = data.dashboards;

  initQualiDash(dashboards);
  initPaisDash(dashboards);
  initCounters(data);
}

initDashboards();

function hasActiveFilters() {
  const assunto = document.getElementById('assunto_id').value;
  const areaCnpq = document.getElementById('area_cnpq_id').value;
  const topico = $('#topico_id').val();
  return Boolean(assunto || areaCnpq || topico);
}

function updateClearFiltersButton() {
  const clearBtn = document.getElementById('clear_dashboard_filters');
  if (hasActiveFilters()) {
    clearBtn.classList.add('is-visible');
  } else {
    clearBtn.classList.remove('is-visible');
  }
}

function refreshDashboardsWithFilters() {
  initDashboards();
  updateClearFiltersButton();
}

document.getElementById('assunto_id').addEventListener("change", function () {
  refreshDashboardsWithFilters();
});

document.getElementById('area_cnpq_id').addEventListener("change", function () {
  refreshDashboardsWithFilters();
});

$('#topico_id').select2({
  placeholder: 'Todos',
  allowClear: true,
  width: '100%',
  ajax: {
    url: window.url_topicos,
    dataType: 'json',
    delay: 250,
    data: function (params) {
      return {
        q: params.term || ''
      };
    },
    processResults: function (data) {
      return data;
    }
  },
  language: {
    noResults: function () { return 'Nenhum tópico encontrado'; },
    searching: function () { return 'Buscando...'; }
  }
});

$('#topico_id').on('change', function () {
  refreshDashboardsWithFilters();
});

document.getElementById('clear_dashboard_filters').addEventListener('click', function () {
  document.getElementById('assunto_id').value = '';
  document.getElementById('area_cnpq_id').value = '';
  $('#topico_id').val(null).trigger('change.select2');
  refreshDashboardsWithFilters();
});

updateClearFiltersButton();
