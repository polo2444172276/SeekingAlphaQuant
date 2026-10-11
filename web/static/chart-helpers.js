function renderTimeChart(canvasId, points, opts) {
  opts = opts || {};
  const canvas = document.getElementById(canvasId);
  if (!canvas || !points || !points.length) return;

  const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const gridColor = isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.08)";
  const textColor = isDark ? "#c9d1d9" : "#1f2328";
  const lineColor = opts.color || (isDark ? "#58a6ff" : "#0969da");

  return new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        {
          data: points,
          borderColor: lineColor,
          backgroundColor: lineColor,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHitRadius: 10,
          tension: 0.15,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: { xAxisKey: "x", yAxisKey: "y" },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => (items[0] ? items[0].label : ""),
            label: (item) => (opts.valueLabel || "Value") + ": " + item.formattedValue,
          },
        },
      },
      scales: {
        x: {
          type: "category",
          ticks: { color: textColor, maxTicksLimit: 6, autoSkip: true },
          grid: { color: gridColor },
        },
        y: {
          ticks: { color: textColor },
          grid: { color: gridColor },
        },
      },
    },
  });
}
