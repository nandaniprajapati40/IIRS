<template>
  <div class="chart-container">
    <!-- Controls -->
    <div class="chart-controls">
      <div class="control-group">
        <label>Indicator</label>
        <div class="select-wrapper">
          <select v-model="selectedLayer" class="select">
            <option value="savi">SAVI - Soil Adjusted Vegetation Index</option>
            <option value="kc">Kc - Crop Coefficient</option>
            <option value="cwr">CWR - Crop Water Requirement</option>
            <option value="iwr">IWR - Irrigation Water Requirement</option>
            <option value="etc">ETC - Evapotranspiration</option>
          </select>
          <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>

      <div class="control-group">
        <label>View</label>
        <div class="toggle-switch">
          <button class="toggle-option" :class="{ active: mode === 'monthly' }" @click="mode = 'monthly'">
            Monthly
          </button>
          <button class="toggle-option" :class="{ active: mode === 'cumulative' }" @click="mode = 'cumulative'">
            Cumulative
          </button>
        </div>
      </div>

      <!-- Chart type badge -->
      <div class="chart-type-badge">
        <svg v-if="mode === 'monthly'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 3v18h18"/>
          <path d="M3 15s3-6 6-6 6 6 9 3"/>
        </svg>
        <!-- <span>{{ mode === 'monthly' }}</span> -->
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <span>Loading chart data…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ error }}
    </div>

    <!-- Chart -->
    <div v-else class="chart-wrapper">
      <canvas ref="chartCanvas" class="chart"></canvas>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import Chart from 'chart.js/auto'

const canvasBackgroundPlugin = {
  id: 'canvasBackgroundPlugin',
  beforeDraw(chartInstance) {
    const { ctx, width, height } = chartInstance
    ctx.save()
    ctx.fillStyle = '#fff'; // Light background
    ctx.fillRect(0, 0, width, height)
    ctx.restore()
  }
}

Chart.register(canvasBackgroundPlugin)

const props = defineProps({
  isDark: { type: Boolean, default: true },
  title: { type: String, default: 'Wheat Crop Parameters - Historical Data' },
  initialLayer: { type: String, default: 'savi' },
  showBoundaryData: { type: Boolean, default: true }
})

const chartCanvas = ref(null)
let chart = null

const selectedLayer = ref(props.initialLayer || 'savi')
const mode = ref('monthly')
const loading = ref(false)
const error = ref(null)

// API Base URL - make sure this matches your backend
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const YEAR_COLORS = [
  '#0f4c81',
  '#1f7a5c',
  '#d97706',
  '#c2410c',
  '#0f766e',
  '#b91c1c',
  '#7c3aed',
  '#4b5563',
  '#0284c7',
  '#65a30d',
]

// ─── Fetch from FastAPI ────────────────────────────────────────────────────────
async function fetchChart() {
  loading.value = true
  error.value = null

  try {
    // Fix: Ensure layer name is correct (not 'swai' typo)
    const layerParam = selectedLayer.value.toLowerCase()
    const url = `${API_BASE}/api/graph/seasonal-chart?layer=${layerParam}&mode=${mode.value}`
    
    console.log('Fetching chart data from:', url)
    
    const res = await fetch(url)
    
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail?.detail || `HTTP ${res.status}: ${res.statusText}`)
    }
    
    const data = await res.json()
    console.log('Chart data received:', data)
    
    if (!data.years || data.years.length === 0) {
      throw new Error('No historical data available for this layer')
    }
    
    loading.value = false   // ← show canvas BEFORE nextTick
    await nextTick()        // ← canvas is now in DOM
    renderChart(data)       // ← canvas.value is valid
  } catch (err) {
    console.error('Chart fetch error:', err)
    error.value = err.message || 'Failed to load chart data.'
    loading.value = false   // ← ensure spinner clears on error too
  }
}

// ─── Render Logic ─────────────────────────────────────────────────────────────
function renderChart(data) {
  if (!chartCanvas.value) {
    console.warn('Chart canvas not ready')
    return
  }

  const ctx = chartCanvas.value.getContext('2d')
  if (chart) {
    chart.destroy()
    chart = null
  }

  // Light theme colors
  const textColor = '#222';
  const gridColor = 'rgba(60, 60, 60, 0.08)';
  const tooltipBg = '#fff';
  const tooltipBorder = '#222';
  const unitLabel  = `${data.layer_config?.full_name || data.layer || 'Value'} (${data.layer_config?.unit || ''})`

  if (mode.value === 'monthly') {
    renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  } else {
    renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  }
}

// ─── Monthly: single continuous time-series line ──────────────────────────────
function renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  // Build flat time-series labels like "Jan 2021", "Feb 2021", …
  const labels = []
  const values = []

  data.years?.forEach(year => {
    const yearData = data.data?.find(d => d.year === year)
    data.months?.forEach((month, mIdx) => {
      labels.push(`${data.month_names?.[mIdx]?.slice(0, 3) || ''} ${year}`)
      values.push(yearData?.monthly?.[mIdx] ?? null)
    })
  })

  if (labels.length === 0) {
    error.value = 'No data points available'
    return
  }


  const color = '#3b9fd9';
  const gradient = ctx.createLinearGradient(0, 0, 0, 420);
  gradient.addColorStop(0, color + '22'); // lighter fill
  gradient.addColorStop(1, color + '00');

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: unitLabel,
        data: values,
        borderColor: color,
        backgroundColor: gradient,
        borderWidth: 2.8,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 7,
        pointBackgroundColor: color,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        fill: true,
        spanGaps: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        canvasBackgroundPlugin: {
          color: '#fff'
        },
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' },
            boxWidth: 24,
            padding: 16
          }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: textColor,
          bodyColor: textColor,
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y
              return v === null ? ' No data' : ` ${v.toFixed(3)}`
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 24
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          },
          title: {
            display: true,
            text: unitLabel,
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' }
          }
        }
      }
    }
  })
}

// ─── Cumulative: multi-series spline, one line per year ───────────────────────
function renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  if (!data.data || data.data.length === 0) {
    error.value = 'No cumulative data available'
    return
  }

  // Reorder data to start from November-December
  const monthOrder = ['November', 'December', 'January', 'February', 'March', 'April']
  const monthIndices = monthOrder.map(month => data.month_names?.indexOf(month) ?? -1).filter(idx => idx !== -1)

  const reorderedLabels = monthOrder
  const reorderedDatasets = data.data.map((yearData, idx) => {
    const color = YEAR_COLORS[idx % YEAR_COLORS.length]
    const reorderedData = monthIndices.map(monthIdx => yearData.cumulative?.[monthIdx] ?? null)
    return {
      label: String(yearData.year),
      data: reorderedData,
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 2.6,
      tension: 0.42,
      pointRadius: 3,
      pointHoverRadius: 8,
      pointBackgroundColor: color,
      pointBorderColor: '#ffffff',
      pointBorderWidth: 2,
      fill: false,
      spanGaps: false
    }
  })

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: reorderedLabels,
      datasets: reorderedDatasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        canvasBackgroundPlugin: {
          color: '#fff'
        },
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' },
            boxWidth: 28,
            padding: 16,
            usePointStyle: true,
            pointStyle: 'circle'
          }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: textColor,
          bodyColor: textColor,
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y
              return v === null ? `  ${ctx.dataset.label}: No data` : `  ${ctx.dataset.label}: ${v.toFixed(3)}`
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          },
          title: {
            display: true,
            text: `Cumulative ${unitLabel}`,
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' }
          }
        }
      }
    }
  })
}

// ─── Watchers & Lifecycle ─────────────────────────────────────────────────────
watch(() => selectedLayer.value, () => {
  fetchChart()
})

watch(() => mode.value, () => {
  fetchChart()
})

watch(() => props.isDark, () => {
  if (chart) {
    fetchChart() // Re-render with new theme
  }
})

onMounted(() => {
  fetchChart()
})

onUnmounted(() => {
  if (chart) {
    chart.destroy()
    chart = null
  }
})
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 0.85rem;
  gap: 0;
  background: #fff;
  color: #1b485f;
  font-family: 'Inter', 'Segoe UI', sans-serif;
  border-radius: 12px;
}

/* ── Controls ── */
.chart-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.control-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0d1012;
  white-space: nowrap;
}

/* Select */
.select-wrapper {
  position: relative;
}

.select {
  padding: 0.45rem 2.25rem 0.45rem 1rem;
  border: 1px solid rgba(200, 210, 220, 0.2);
  border-radius: 30px;
  background: #0d1319;
  font-size: 0.875rem;
  color: #f0f4f8;
  outline: none;
  cursor: pointer;
  appearance: none;
  min-width: 260px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.select:hover { border-color: #2f855a; }
.select:focus { border-color: #2b6cb0; box-shadow: 0 0 0 4px rgba(43, 108, 176, 0.12); }

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #8899aa;
}

/* Toggle */
.toggle-switch {
  display: flex;
  background: rgba(40, 95, 150, 0.1);
  border-radius: 30px;
  padding: 3px;
  gap: 2px;
}

.toggle-option {
  padding: 0.4rem 1rem;
  border: none;
  background: transparent;
  border-radius: 30px;
  font-size: 0.875rem;
  font-weight: 500;
  color: #8899aa;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-option.active {
  background: #2f855a;
  color: #f0f4f8;
  box-shadow: 0 6px 16px rgba(47, 133, 90, 0.3);
}

/* Badge */
.chart-type-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto;
  padding: 0.35rem 0.85rem;
  background: rgba(47, 133, 90, 0.15);
  border: 1px solid rgba(47, 133, 90, 0.3);
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
  color: #3b9fd9;
}

/* Loading */
.loading-overlay {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: #8899aa;
  font-size: 0.9rem;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(200, 210, 220, 0.2);
  border-top-color: #2f855a;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* Error */
.error-box {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  color: #f87171;
  font-size: 0.9rem;
  background: rgba(127, 29, 29, 0.2);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  margin: 1rem 0;
}

:global(.dark) .error-box {
  background: rgba(127, 29, 29, 0.3);
  border-color: rgba(248, 113, 113, 0.4);
}

/* Chart */
.chart-wrapper {
  flex: 1;
  min-height: 0;
  height: 0;
  position: relative;
  background: #fff;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 10px;
  padding: 0.25rem;
}

.chart {
  position: absolute !important;
  top: 0;
  left: 0;
  width: 100% !important;
  height: 100% !important;
}

/* Responsive */
@media (max-width: 768px) {
  .chart-container { padding: 0.65rem; }

  .chart-controls {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .control-group { width: 100%; }

  .select { min-width: 0; width: 100%; }

  .chart-type-badge { margin-left: 0; }
}
</style>
