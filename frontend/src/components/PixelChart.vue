<template>
  <div class="chart-container">

    <!-- ── Header ── -->
    <div class="pixel-header">
      <div class="pixel-meta">
        <span class="pixel-id-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>
          </svg>
          Pixel {{ pixelData?.pixel_id || '—' }}
        </span>
        <span class="pixel-coords" v-if="pixelData">
          {{ pixelData.latitude?.toFixed(5) }}°N, {{ pixelData.longitude?.toFixed(5) }}°E
        </span>
      </div>
    </div>

    <!-- ── Controls ── -->
    <div class="chart-controls">
      <div class="control-group">
        <label>Indicator</label>
        <div class="select-wrapper">
          <select v-model="selectedLayer" class="select">
            <option value="savi">SAVI – Soil Adjusted Vegetation Index</option>
            <option value="kc">Kc – Crop Coefficient</option>
            <option value="cwr">CWR – Crop Water Requirement</option>
            <option value="iwr">IWR – Irrigation Water Requirement</option>
            <option value="etc">ETc – Crop Evapotranspiration</option>
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

      <div class="chart-type-badge">
        <svg v-if="mode === 'monthly'" width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2">
          <path d="M3 3v18h18"/><path d="M3 15s3-6 6-6 6 6 9 3"/>
        </svg>
      </div>
    </div>

    <!-- ── Loading ── -->
    <div v-if="!pixelData" class="loading-overlay">
      <div class="spinner"></div>
      <span>Fetching pixel timeseries…</span>
    </div>

    <!-- ── Error ── -->
    <div v-else-if="error" class="error-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ error }}
    </div>

    <!-- ── No Data ── -->
    <div v-else-if="recordCount === 0" class="error-box no-data-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 3h18v18H3z"/><path d="M9 9l6 6M15 9l-6 6"/>
      </svg>
      No data stored for <strong>{{ selectedLayer.toUpperCase() }}</strong> at this pixel yet.
    </div>

    <!-- ── Chart ── -->
    <div v-else class="chart-wrapper">
      <canvas ref="chartCanvas" class="chart"></canvas>
    </div>

    <!-- ── Record count hint ── -->
    <div class="record-hint" v-if="pixelData && recordCount > 0">
      {{ recordCount }} observations · {{ seasonCount }} season(s)
    </div>

  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import Chart from 'chart.js/auto'

// ── Canvas background plugin (same as DataChart) ──────────────────────────
const canvasBackgroundPlugin = {
  id: 'canvasBackgroundPlugin',
  beforeDraw(chartInstance) {
    const { ctx, width, height } = chartInstance
    ctx.save()
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, width, height)
    ctx.restore()
  }
}
Chart.register(canvasBackgroundPlugin)

// ── Props ─────────────────────────────────────────────────────────────────
const props = defineProps({
  pixelData: { type: Object, default: null },        // full /api/pixel-timeseries response
  initialLayer: { type: String, default: 'savi' },
})

// ── State ─────────────────────────────────────────────────────────────────
const chartCanvas = ref(null)
let chart = null

const selectedLayer = ref(props.initialLayer || 'savi')
const mode = ref('monthly')
const error = ref(null)

// ── Layer metadata (same units as DataChart / info panel) ─────────────────
const LAYER_CONFIG = {
  savi: { full_name: 'SAVI',  unit: '' },
  kc:   { full_name: 'Kc',    unit: '' },
  cwr:  { full_name: 'CWR',   unit: 'mm/day' },
  iwr:  { full_name: 'IWR',   unit: 'mm/day' },
  etc:  { full_name: 'ETc',   unit: 'mm/day' },
}

// Season runs Nov–Apr; ordering for x-axis in cumulative view
const SEASON_MONTH_ORDER = ['11', '12', '01', '02', '03', '04']
const MONTH_NAMES_SHORT = {
  '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
  '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
  '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

// Multi-season colour palette — matches DataChart's YEAR_COLORS
const SEASON_COLORS = [
  '#0f4c81', '#1f7a5c', '#d97706', '#c2410c',
  '#0f766e', '#b91c1c', '#7c3aed', '#4b5563',
  '#0284c7', '#65a30d',
]

// ── Helpers ───────────────────────────────────────────────────────────────

/** Return the season string (e.g. '2024-25') for a date string 'YYYY-MM-DD'. */
function getSeasonId(dateStr) {
  const [y, m] = dateStr.split('-').map(Number)
  if (m >= 11) return `${y}-${String(y + 1).slice(-2)}`
  if (m <= 4)  return `${y - 1}-${String(y).slice(-2)}`
  return null // off-season (May–Oct)
}

/** Group {date, value} records by 'YYYY-MM', return monthly averages sorted. */
function buildMonthlyAvg(records) {
  const grouped = {}
  records.forEach(r => {
    const key = r.date.substring(0, 7)
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(r.value)
  })
  return Object.keys(grouped).sort().map(k => ({
    monthKey: k,
    value: grouped[k].reduce((a, b) => a + b, 0) / grouped[k].length,
  }))
}

/** Build per-season monthly-average arrays (for cumulative multi-line chart). */
function buildSeasonData(records) {
  // seasons[sid][mm] = [values…]
  const seasons = {}
  records.forEach(r => {
    const sid = getSeasonId(r.date)
    if (!sid) return
    const mm = r.date.substring(5, 7)
    if (!SEASON_MONTH_ORDER.includes(mm)) return
    if (!seasons[sid]) seasons[sid] = {}
    if (!seasons[sid][mm]) seasons[sid][mm] = []
    seasons[sid][mm].push(r.value)
  })

  return Object.keys(seasons).sort().map(sid => {
    const monthlyAvg = SEASON_MONTH_ORDER.map(mm => {
      const vals = seasons[sid][mm]
      return vals && vals.length > 0
        ? vals.reduce((a, b) => a + b, 0) / vals.length
        : null
    })
    // Running cumulative (skip nulls but don't reset)
    let cum = 0
    const cumulative = monthlyAvg.map(v => {
      if (v === null) return null
      cum += v
      return Math.round(cum * 10000) / 10000
    })
    return { season: sid, monthly: monthlyAvg, cumulative }
  })
}

// ── Computed helpers ──────────────────────────────────────────────────────
const currentRecords = computed(() => {
  return props.pixelData?.timeseries?.[selectedLayer.value] || []
})

const recordCount = computed(() => currentRecords.value.length)

const seasonCount = computed(() => {
  const sids = new Set(
    currentRecords.value.map(r => getSeasonId(r.date)).filter(Boolean)
  )
  return sids.size
})

// ── Chart rendering ───────────────────────────────────────────────────────
async function buildChart() {
  error.value = null

  if (!props.pixelData) return
  if (recordCount.value === 0) return   // handled in template

  await nextTick()
  if (!chartCanvas.value) return

  if (chart) { chart.destroy(); chart = null }

  const cfg = LAYER_CONFIG[selectedLayer.value] || { full_name: selectedLayer.value, unit: '' }
  const unitLabel = cfg.unit
    ? `${cfg.full_name} (${cfg.unit})`
    : cfg.full_name

  const textColor   = '#222'
  const gridColor   = 'rgba(60,60,60,0.08)'
  const tooltipBg   = '#fff'
  const tooltipBorder = '#222'

  if (mode.value === 'monthly') {
    renderMonthly({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  } else {
    renderCumulative({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  }
}

// ── Monthly: single continuous timeline ──────────────────────────────────
function renderMonthly({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  const monthly = buildMonthlyAvg(currentRecords.value)
  if (monthly.length === 0) {
    error.value = 'No monthly data to display'
    return
  }

  const labels = monthly.map(m => {
    const [y, mo] = m.monthKey.split('-')
    return `${MONTH_NAMES_SHORT[mo]} ${y}`
  })
  const values = monthly.map(m => Math.round(m.value * 10000) / 10000)

  const color = '#3b9fd9'
  const ctx = chartCanvas.value.getContext('2d')
  const gradient = ctx.createLinearGradient(0, 0, 0, 420)
  gradient.addColorStop(0, color + '33')
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
        borderWidth: 2.8,
        tension: 0.35,
        pointRadius: 3.5,
        pointHoverRadius: 7,
        pointBackgroundColor: color,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        fill: true,
        spanGaps: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        canvasBackgroundPlugin: { color: '#fff' },
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
            boxWidth: 24,
            padding: 16,
          },
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
              return v === null ? ' No data' : ` ${v.toFixed(4)}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 24,
          },
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
          },
          title: {
            display: true,
            text: unitLabel,
            color: textColor,
            font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
          },
        },
      },
    },
  })
}

// ── Cumulative: one line per season ──────────────────────────────────────
function renderCumulative({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  const seasonData = buildSeasonData(currentRecords.value)
  if (seasonData.length === 0) {
    error.value = 'No seasonal data to display'
    return
  }

  const ctx = chartCanvas.value.getContext('2d')
  const xLabels = SEASON_MONTH_ORDER.map(mm => MONTH_NAMES_SHORT[mm])

  const datasets = seasonData.map((s, idx) => {
    const color = SEASON_COLORS[idx % SEASON_COLORS.length]
    return {
      label: s.season,
      data: s.cumulative,
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 2.6,
      tension: 0.42,
      pointRadius: 3,
      pointHoverRadius: 8,
      pointBackgroundColor: color,
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      fill: false,
      spanGaps: false,
    }
  })

  chart = new Chart(ctx, {
    type: 'line',
    data: { labels: xLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        canvasBackgroundPlugin: { color: '#fff' },
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
            boxWidth: 28,
            padding: 16,
            usePointStyle: true,
            pointStyle: 'circle',
          },
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
              return v === null
                ? `  ${ctx.dataset.label}: No data`
                : `  ${ctx.dataset.label}: ${v.toFixed(4)}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
          },
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
          },
          title: {
            display: true,
            text: `Cumulative ${unitLabel}`,
            color: textColor,
            font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
          },
        },
      },
    },
  })
}

// ── Watchers & lifecycle ──────────────────────────────────────────────────
watch(() => props.pixelData, () => { buildChart() })
watch(selectedLayer,          () => { buildChart() })
watch(mode,                   () => { buildChart() })

onMounted(() => { buildChart() })
onUnmounted(() => { if (chart) { chart.destroy(); chart = null } })
</script>

<style scoped>
/* ── Container ── */
.chart-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1.25rem 1.5rem 0.75rem;
  gap: 0;
  background: #fff;
  color: #1b485f;
  font-family: 'Inter', 'Segoe UI', sans-serif;
}

/* ── Pixel header ── */
.pixel-header {
  margin-bottom: 0.85rem;
}
.pixel-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.pixel-id-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(59, 159, 217, 0.1);
  border: 1px solid rgba(59, 159, 217, 0.3);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.78rem;
  font-weight: 700;
  color: #1b5fa8;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
}
.pixel-coords {
  font-size: 0.77rem;
  color: #607d8b;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Controls (reuse DataChart styles exactly) ── */
.chart-controls {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1rem;
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
.select-wrapper { position: relative; }
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
.select:focus { border-color: #2b6cb0; box-shadow: 0 0 0 4px rgba(43,108,176,0.12); }
.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #8899aa;
}
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

/* ── Loading ── */
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

/* ── Error / no-data ── */
.error-box {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  color: #f87171;
  font-size: 0.9rem;
  background: rgba(127, 29, 29, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  margin: 0.5rem 0;
}
.no-data-box {
  color: #64748b;
  background: rgba(100, 116, 139, 0.08);
  border-color: rgba(100, 116, 139, 0.25);
}

/* ── Chart wrapper (reuse DataChart) ── */
.chart-wrapper {
  flex: 1;
  min-height: 0;
  height: 0;
  position: relative;
  background: #fff;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 16px;
  padding: 0.75rem;
}
.chart {
  position: absolute !important;
  top: 0; left: 0;
  width: 100% !important;
  height: 100% !important;
}

/* ── Record hint ── */
.record-hint {
  font-size: 0.72rem;
  color: #94a3b8;
  text-align: right;
  padding: 4px 2px 0;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .chart-container { padding: 1rem; }
  .chart-controls { flex-direction: column; align-items: flex-start; gap: 0.75rem; }
  .control-group { width: 100%; }
  .select { min-width: 0; width: 100%; }
  .chart-type-badge { margin-left: 0; }
}
</style>