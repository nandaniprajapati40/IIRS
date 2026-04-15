<template>
  <div class="chart-container">
    <!-- Controls -->
    <div class="chart-controls">
      <div class="control-group">
        <label>Layer</label>
        <div class="select-wrapper">
          <select v-model="selectedLayer" class="select">
            <option value="savi">SAVI - Soil Adjusted Vegetation Index</option>
            <option value="kc">Kc - Crop Coefficient</option>
            <option value="cwr">CWR - Crop Water Requirement</option>
            <option value="iwr">IWR - Irrigation Water Requirement</option>
          </select>
          <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>

      <div class="control-group">
        <label>Mode</label>
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

// Vivid colors that pop on dark AND light backgrounds
const YEAR_COLORS = [
  '#38bdf8', // sky blue
  '#f472b6', // pink
  '#4ade80', // green
  '#fb923c', // orange
  '#a78bfa', // violet
  '#facc15', // yellow
  '#34d399', // emerald
  '#f87171', // red
  '#60a5fa', // blue
  '#e879f9', // fuchsia
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

  const isDark = props.isDark
  const textColor  = isDark ? '#cbd5e1' : '#1e293b'
  const gridColor  = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'
  const tooltipBg  = isDark ? '#0f172a' : '#ffffff'
  const unitLabel  = `${data.layer_config?.full_name || data.layer || 'Value'} (${data.layer_config?.unit || ''})`

  if (mode.value === 'monthly') {
    renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, unitLabel, isDark })
  } else {
    renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, unitLabel, isDark })
  }
}

// ─── Monthly: single continuous time-series line ──────────────────────────────
function renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, unitLabel }) {
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

  const color = '#38bdf8'  // bright sky blue — visible on dark bg
  const gradient = ctx.createLinearGradient(0, 0, 0, 420)
  gradient.addColorStop(0, color + '66')
  gradient.addColorStop(1, color + '00')

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: unitLabel,
        data: values,
        borderColor: color,
        backgroundColor: gradient,
        borderWidth: 2.5,
        tension: 0.35,
        pointRadius: 3.5,
        pointHoverRadius: 7,
        pointBackgroundColor: color,
        pointBorderColor: '#ffffff',
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
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: { color: textColor, font: { size: 12 }, boxWidth: 24, padding: 16 }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: textColor,
          bodyColor: textColor,
          borderColor: gridColor,
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
            font: { size: 10 },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 24
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 11 } },
          title: { display: true, text: unitLabel, color: textColor, font: { size: 12 } }
        }
      }
    }
  })
}

// ─── Cumulative: multi-series spline, one line per year ───────────────────────
function renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, unitLabel }) {
  if (!data.data || data.data.length === 0) {
    error.value = 'No cumulative data available'
    return
  }

  const datasets = data.data.map((yearData, idx) => {
    const color = YEAR_COLORS[idx % YEAR_COLORS.length]
    return {
      label: String(yearData.year),
      data: yearData.cumulative ?? [],
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 2.5,
      tension: 0.45,
      pointRadius: 4,
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
      labels: data.month_names || [],
      datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: textColor,
            font: { size: 12 },
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
          borderColor: gridColor,
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
          ticks: { color: textColor, font: { size: 11 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 11 } },
          title: {
            display: true,
            text: `Cumulative ${unitLabel}`,
            color: textColor,
            font: { size: 12 }
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
  padding: 1.5rem;
  gap: 0;
  background: transparent;
}

/* ── Controls ── */
.chart-controls {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.control-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: #64748b;
  white-space: nowrap;
}

:global(.dark) .control-group label {
  color: #94a3b8;
}

/* Select */
.select-wrapper {
  position: relative;
}

.select {
  padding: 0.45rem 2.25rem 0.45rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 30px;
  background: #ffffff;
  font-size: 0.875rem;
  color: #1e293b;
  outline: none;
  cursor: pointer;
  appearance: none;
  min-width: 260px;
  transition: border-color 0.2s;
}

.select:hover { border-color: #3b82f6; }

:global(.dark) .select {
  background: #1e293b;
  border-color: #334155;
  color: #e2e8f0;
}

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #64748b;
}

/* Toggle */
.toggle-switch {
  display: flex;
  background: #f1f5f9;
  border-radius: 30px;
  padding: 3px;
  gap: 2px;
}

:global(.dark) .toggle-switch {
  background: #334155;
}

.toggle-option {
  padding: 0.4rem 1rem;
  border: none;
  background: transparent;
  border-radius: 30px;
  font-size: 0.875rem;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

:global(.dark) .toggle-option { color: #94a3b8; }

.toggle-option.active {
  background: #ffffff;
  color: #2563eb;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.12);
}

:global(.dark) .toggle-option.active {
  background: #1e293b;
  color: #60a5fa;
}

/* Badge */
.chart-type-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto;
  padding: 0.35rem 0.85rem;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
  color: #2563eb;
}

:global(.dark) .chart-type-badge {
  background: #1e3a5f;
  border-color: #1e40af;
  color: #93c5fd;
}

/* Loading */
.loading-overlay {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: #64748b;
  font-size: 0.9rem;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
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
  color: #ef4444;
  font-size: 0.9rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 12px;
  padding: 1.5rem;
  margin: 1rem 0;
}

:global(.dark) .error-box {
  background: #3b0f0f;
  border-color: #7f1d1d;
}

/* Chart */
.chart-wrapper {
  flex: 1;
  min-height: 0;
  height: 0;          
  position: relative;
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
  .chart-container { padding: 1rem; }

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