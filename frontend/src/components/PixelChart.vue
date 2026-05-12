<template>
  <div class="chart-container" :class="[{ compact }, theme === 'glass' ? 'glass' : 'light']">

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
      <div class="control-group layer-control">
        <label for="pixel-layer-select">Indicator</label>
        <div class="select-wrapper">
          <select id="pixel-layer-select" v-model="selectedLayer" class="select" aria-label="Select graph indicator">
            <option
              v-for="key in layerKeys"
              :key="key"
              :value="key"
            >
              {{ LAYER_CONFIG[key].full_name }}
            </option>
          </select>
          <span class="select-arrow" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </span>
        </div>
      </div>

      <div class="control-group view-control">
        <label>View</label>
        <div class="toggle-switch">
          <button class="toggle-option" :class="{ active: mode === 'monthly' }" @click="mode = 'monthly'">
            Timeline
          </button>
          <button class="toggle-option" :class="{ active: mode === 'cumulative' }" @click="mode = 'cumulative'">
            Cumulative
          </button>
        </div>
      </div>

      <div class="chart-toolbar" aria-label="Chart zoom controls">
        <button
          class="chart-tool"
          type="button"
          @click="adjustChartZoom(-0.2)"
          :disabled="chartZoom <= 1"
          title="Zoom out"
          aria-label="Zoom out"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
            <circle cx="11" cy="11" r="7"/><path d="M8 11h6"/><path d="m20 20-3.5-3.5"/>
          </svg>
        </button>
        <span class="chart-zoom-value">{{ Math.round(chartZoom * 100) }}%</span>
        <button
          class="chart-tool"
          type="button"
          @click="adjustChartZoom(0.2)"
          :disabled="chartZoom >= 3"
          title="Zoom in"
          aria-label="Zoom in"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
            <circle cx="11" cy="11" r="7"/><path d="M8 11h6"/><path d="M11 8v6"/><path d="m20 20-3.5-3.5"/>
          </svg>
        </button>
        <button
          class="chart-tool"
          type="button"
          @click="resetChartZoom"
          :disabled="chartZoom === 1"
          title="Reset zoom"
          aria-label="Reset zoom"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/>
          </svg>
        </button>
      </div>
    </div>

    

    <!-- ── Loading ── -->
    <div v-if="!pixelData" class="loading-overlay">
      <div class="chart-skeleton-line short"></div>
      <div class="chart-skeleton-panel">
        <span v-for="n in 8" :key="n"></span>
      </div>
      <div class="chart-skeleton-line"></div>
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
    <div v-else class="chart-wrapper" :class="{ panning: isChartPanning }">
      <div
        ref="chartViewport"
        class="chart-viewport"
        @wheel="handleChartWheel"
        @pointerdown="startChartPan"
        @pointermove="moveChartPan"
        @pointerup="stopChartPan"
        @pointercancel="stopChartPan"
        @pointerleave="stopChartPan"
      >
        <div class="chart-scroll-spacer" :style="{ width: `${chartCanvasWidth}px` }">
          <canvas ref="chartCanvas" class="chart"></canvas>
        </div>
      </div>
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
    const color = chartInstance.options?.plugins?.canvasBackgroundPlugin?.color || '#fff'
    ctx.save()
    ctx.fillStyle = color
    ctx.fillRect(0, 0, width, height)
    ctx.restore()
  }
}
Chart.register(canvasBackgroundPlugin)

// ── Props ─────────────────────────────────────────────────────────────────
const props = defineProps({
  pixelData: { type: Object, default: null },        // full /api/pixel-timeseries response
  initialLayer: { type: String, default: 'savi' },
  modelLayer: { type: String, default: null },
  modelMode: { type: String, default: null },
  modelZoom: { type: Number, default: null },
  theme: { type: String, default: 'light' },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelLayer', 'update:modelMode', 'update:modelZoom'])
const theme = computed(() => props.theme)
const compact = computed(() => props.compact)

// ── State ─────────────────────────────────────────────────────────────────
const chartCanvas = ref(null)
const chartViewport = ref(null)
let chart = null
let chartViewportObserver = null
let chartLayoutFrame = null

const selectedLayer = ref(props.modelLayer || props.initialLayer || 'savi')
const mode = ref(props.modelMode || 'monthly')
const error = ref(null)
const chartZoom = ref(clamp(Number(props.modelZoom) || 1, 1, 3))
const chartViewportWidth = ref(0)
const isChartPanning = ref(false)
let chartPanStart = null

// ── Layer metadata (same units as DataChart / info panel) ─────────────────
const LAYER_CONFIG = {
  savi: { full_name: 'SAVI',  unit: '' },
  kc:   { full_name: 'KC',    unit: '' },
  cwr:  { full_name: 'CWR',   unit: 'mm/day' },
  iwr:  { full_name: 'IWR',   unit: 'mm/day' },
  etc:  { full_name: 'ETC',   unit: 'mm/day' },
}
const layerKeys = Object.keys(LAYER_CONFIG)

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

/** Return actual raster observations sorted by acquisition date. */
function buildObservationSeries(records) {
  return [...records]
    .filter(r => r.date && r.value !== null && r.value !== undefined)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(r => ({
      date: r.date,
      value: Number(r.value),
    }))
}

function formatDateLabel(dateStr) {
  const [y, mo, d] = dateStr.split('-')
  return `${MONTH_NAMES_SHORT[mo]} ${Number(d)}, ${y}`
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

const valueStats = computed(() => {
  const values = buildObservationSeries(currentRecords.value)
    .map(r => r.value)
    .filter(v => Number.isFinite(v))

  if (values.length === 0) return null
  const latest = values[values.length - 1]
  const min = Math.min(...values)
  const max = Math.max(...values)
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length
  const format = v => Number(v).toFixed(4)

  return {
    latest: format(latest),
    min: format(min),
    max: format(max),
    mean: format(mean),
  }
})

const observationCount = computed(() => buildObservationSeries(currentRecords.value).length)

const chartCanvasWidth = computed(() => {
  const viewport = Math.max(320, chartViewportWidth.value || 0)
  const points = Math.max(1, mode.value === 'monthly' ? observationCount.value : SEASON_MONTH_ORDER.length)
  const pointWidth = mode.value === 'monthly' ? 42 : 120
  const naturalWidth = mode.value === 'monthly' ? points * pointWidth : viewport
  return Math.max(viewport, Math.round(naturalWidth * chartZoom.value))
})

// ── Chart rendering ───────────────────────────────────────────────────────
function destroyChart() {
  if (chart) {
    chart.destroy()
    chart = null
  }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function measureChartViewport() {
  if (!chartViewport.value) return
  chartViewportWidth.value = Math.floor(chartViewport.value.clientWidth)
}

function attachChartViewportObserver() {
  if (!chartViewport.value) return
  if (chartViewportObserver) chartViewportObserver.disconnect()

  measureChartViewport()
  if (typeof ResizeObserver === 'undefined') return

  chartViewportObserver = new ResizeObserver(entries => {
    const entry = entries[0]
    chartViewportWidth.value = Math.floor(entry.contentRect.width)
    scheduleChartLayout()
  })
  chartViewportObserver.observe(chartViewport.value)
}

function xTickLimit(labelCount) {
  const width = chartCanvasWidth.value || chartViewportWidth.value || 800
  const target = mode.value === 'monthly' ? 92 : 72
  return Math.min(labelCount, Math.max(6, Math.floor(width / target)))
}

function scheduleChartLayout() {
  if (!chart) return
  if (chartLayoutFrame) cancelAnimationFrame(chartLayoutFrame)
  chartLayoutFrame = requestAnimationFrame(() => {
    chartLayoutFrame = null
    if (!chart) return
    const labelCount = chart.data?.labels?.length || 0
    if (chart.options?.scales?.x?.ticks) {
      chart.options.scales.x.ticks.maxTicksLimit = xTickLimit(labelCount)
    }
    chart.resize()
    chart.update('none')
  })
}

function adjustChartZoom(delta) {
  chartZoom.value = clamp(Math.round((chartZoom.value + delta) * 10) / 10, 1, 3)
  nextTick(scheduleChartLayout)
}

function resetChartZoom() {
  chartZoom.value = 1
  nextTick(() => {
    if (chartViewport.value) {
      chartViewport.value.scrollTo({ left: 0, behavior: 'smooth' })
    }
    scheduleChartLayout()
  })
}

function handleChartWheel(event) {
  if (!chartViewport.value) return

  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    const oldWidth = chartCanvasWidth.value
    const oldZoom = chartZoom.value
    const delta = event.deltaY < 0 ? 0.15 : -0.15
    const nextZoom = clamp(Math.round((oldZoom + delta) * 20) / 20, 1, 3)
    if (nextZoom === oldZoom) return

    const rect = chartViewport.value.getBoundingClientRect()
    const cursorX = event.clientX - rect.left
    const ratio = oldWidth > 0
      ? (chartViewport.value.scrollLeft + cursorX) / oldWidth
      : 0

    chartZoom.value = nextZoom
    nextTick(() => {
      if (!chartViewport.value) return
      const nextLeft = ratio * chartCanvasWidth.value - cursorX
      chartViewport.value.scrollLeft = Math.max(0, nextLeft)
      scheduleChartLayout()
    })
    return
  }

  if (event.shiftKey && Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
    event.preventDefault()
    chartViewport.value.scrollBy({ left: event.deltaY, behavior: 'smooth' })
  }
}

function startChartPan(event) {
  if (event.button !== 0 || !chartViewport.value) return
  if (chartViewport.value.scrollWidth <= chartViewport.value.clientWidth + 1) return

  isChartPanning.value = true
  chartPanStart = {
    pointerId: event.pointerId,
    x: event.clientX,
    scrollLeft: chartViewport.value.scrollLeft,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function moveChartPan(event) {
  if (!isChartPanning.value || !chartPanStart || event.pointerId !== chartPanStart.pointerId) return
  event.preventDefault()
  chartViewport.value.scrollLeft = chartPanStart.scrollLeft - (event.clientX - chartPanStart.x)
}

function stopChartPan(event) {
  if (!isChartPanning.value) return
  const target = event?.currentTarget
  const pointerId = chartPanStart?.pointerId
  if (pointerId !== undefined && target?.hasPointerCapture?.(pointerId)) {
    target.releasePointerCapture(pointerId)
  }
  isChartPanning.value = false
  chartPanStart = null
}

async function buildChart() {
  error.value = null
  destroyChart()

  if (!props.pixelData) return
  if (recordCount.value === 0) return   // handled in template

  await nextTick()
  attachChartViewportObserver()
  if (!chartCanvas.value) return

  const cfg = LAYER_CONFIG[selectedLayer.value] || { full_name: selectedLayer.value, unit: '' }
  const unitLabel = cfg.unit
    ? `${cfg.full_name} (${cfg.unit})`
    : cfg.full_name

  const isGlass = props.theme === 'glass'
  const textColor = isGlass ? '#eaf6fc' : '#222'
  const gridColor = isGlass ? 'rgba(205,225,238,0.14)' : 'rgba(60,60,60,0.08)'
  const tooltipBg = isGlass ? 'rgba(8,15,22,0.96)' : '#fff'
  const tooltipBorder = isGlass ? 'rgba(130,185,220,0.4)' : '#222'
  const canvasBg = isGlass ? 'rgba(7,14,20,0.42)' : '#fff'

  if (mode.value === 'monthly') {
    renderMonthly({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg })
  } else {
    renderCumulative({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg })
  }
}

// ── Timeline: one point for each available raster date ───────────────────
function renderMonthly({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg }) {
  const observations = buildObservationSeries(currentRecords.value)
  if (observations.length === 0) {
    error.value = 'No raster observations to display'
    return
  }

  const labels = observations.map(o => formatDateLabel(o.date))
  const values = observations.map(o => Math.round(o.value * 10000) / 10000)
  const densePoints = values.length > 140

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
        borderWidth: densePoints ? 2.2 : 2.8,
        tension: 0.35,
        pointRadius: densePoints ? 2.2 : 3.5,
        pointHoverRadius: densePoints ? 6 : 7,
        pointBackgroundColor: color,
        pointBorderColor: '#fff',
        pointBorderWidth: densePoints ? 1.5 : 2,
        fill: true,
        spanGaps: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8, right: 12, bottom: 6, left: 4 } },
      plugins: {
        canvasBackgroundPlugin: { color: canvasBg },
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
            maxTicksLimit: xTickLimit(labels.length),
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
function renderCumulative({ textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg }) {
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
      layout: { padding: { top: 8, right: 12, bottom: 6, left: 4 } },
      plugins: {
        canvasBackgroundPlugin: { color: canvasBg },
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
            maxTicksLimit: xTickLimit(xLabels.length),
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
watch(() => props.pixelData, () => { buildChart() }, { flush: 'post' })
watch(() => props.initialLayer, layer => {
  if (!props.modelLayer && layer && layer !== selectedLayer.value) selectedLayer.value = layer
})
watch(() => props.modelLayer, layer => {
  if (layer && layer !== selectedLayer.value) selectedLayer.value = layer
})
watch(() => props.modelMode, nextMode => {
  if (nextMode && nextMode !== mode.value) mode.value = nextMode
})
watch(() => props.modelZoom, nextZoom => {
  const normalized = clamp(Number(nextZoom) || 1, 1, 3)
  if (normalized !== chartZoom.value) chartZoom.value = normalized
})
watch(selectedLayer, layer => {
  emit('update:modelLayer', layer)
  buildChart()
}, { flush: 'post' })
watch(mode, nextMode => {
  emit('update:modelMode', nextMode)
  buildChart()
}, { flush: 'post' })
watch(chartZoom, nextZoom => {
  emit('update:modelZoom', nextZoom)
  nextTick(scheduleChartLayout)
}, { flush: 'post' })
watch(chartCanvasWidth, () => { nextTick(scheduleChartLayout) }, { flush: 'post' })

onMounted(() => {
  window.addEventListener('resize', measureChartViewport)
  buildChart()
})
onUnmounted(() => {
  window.removeEventListener('resize', measureChartViewport)
  if (chartLayoutFrame) cancelAnimationFrame(chartLayoutFrame)
  if (chartViewportObserver) chartViewportObserver.disconnect()
  destroyChart()
})
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
.chart-container.glass {
  padding: 0;
  background: transparent;
  color: #eaf6fc;
}
.chart-container.compact {
  gap: 0;
}

/* ── Pixel header ── */
.pixel-header {
  margin-bottom: 0.85rem;
}
.chart-container.compact .pixel-header {
  margin-bottom: 0.65rem;
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
.chart-container.glass .pixel-id-badge {
  background: rgba(59, 159, 217, 0.14);
  border-color: rgba(59, 159, 217, 0.36);
  color: #92cdf8;
}
.pixel-coords {
  font-size: 0.77rem;
  color: #607d8b;
  font-family: 'JetBrains Mono', monospace;
}
.chart-container.glass .pixel-coords {
  color: #9db8c9;
}

/* ── Controls (reuse DataChart styles exactly) ── */
.chart-controls {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.chart-container.compact .chart-controls {
  margin-bottom: 0.75rem;
}
.control-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.layer-control {
  flex: 1 1 230px;
  align-items: flex-start;
  flex-direction: column;
  gap: 0.45rem;
  max-width: 310px;
}
.view-control {
  flex: 0 1 auto;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.45rem;
}
.control-group label {
  font-size: 0.73rem;
  font-weight: 600;
  color: #0d1012;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}
.chart-container.glass .control-group label {
  color: #c7dbe7;
}
.layer-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}
.layer-tab {
  min-width: 0;
  height: 38px;
  border: 1px solid rgba(180, 205, 222, 0.12);
  border-radius: 10px;
  color: #a8bfd0;
  background: rgba(255, 255, 255, 0.055);
  font-size: 0.82rem;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}
.layer-tab:hover {
  transform: translateY(-1px);
  border-color: rgba(120, 180, 220, 0.28);
  color: #f4fbff;
}
.layer-tab.active {
  color: #041015;
  border-color: transparent;
  box-shadow: 0 12px 22px rgba(0, 0, 0, 0.18);
}
.layer-tab.savi.active { background: linear-gradient(135deg, #6ee787, #3bbd52); }
.layer-tab.kc.active   { background: linear-gradient(135deg, #70b7ff, #3679df); }
.layer-tab.cwr.active  { background: linear-gradient(135deg, #ffd36c, #f59e0b); }
.layer-tab.iwr.active  { background: linear-gradient(135deg, #d59cff, #9b5de5); }
.layer-tab.etc.active  { background: linear-gradient(135deg, #70f1f5, #19b6d2); }
.select-wrapper {
  position: relative;
  width: 100%;
}
.select {
  width: 100%;
  height: 40px;
  padding: 0.45rem 2.35rem 0.45rem 0.9rem;
  border: 1px solid rgba(180, 205, 222, 0.16);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.095), rgba(255, 255, 255, 0.035)),
    rgba(7, 14, 20, 0.62);
  backdrop-filter: blur(16px);
  font-size: 0.86rem;
  font-weight: 800;
  color: #f0f4f8;
  outline: none;
  cursor: pointer;
  appearance: none;
  min-width: 0;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}
.select option {
  background: #101922;
  color: #eaf6fc;
}
.select:hover { border-color: rgba(59, 159, 217, 0.45); }
.select:focus {
  border-color: rgba(59, 159, 217, 0.72);
  box-shadow: 0 0 0 4px rgba(59, 159, 217, 0.14);
}
.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #98c8e7;
  display: inline-flex;
}
.toggle-switch {
  display: flex;
  background: rgba(40, 95, 150, 0.1);
  border-radius: 30px;
  padding: 3px;
  gap: 2px;
}
.chart-container.glass .toggle-switch {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(180, 205, 222, 0.1);
}
.toggle-option {
  height: 32px;
  padding: 0 0.95rem;
  border: none;
  background: transparent;
  border-radius: 30px;
  font-size: 0.82rem;
  font-weight: 700;
  color: #8899aa;
  cursor: pointer;
  transition: all 0.2s;
}
.toggle-option.active {
  background: #2f855a;
  color: #f0f4f8;
  box-shadow: 0 6px 16px rgba(47, 133, 90, 0.3);
}
.chart-container.glass .toggle-option.active {
  background: #3b9fd9;
  box-shadow: 0 8px 20px rgba(59, 159, 217, 0.25);
}
.chart-toolbar {
  height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border: 1px solid rgba(180, 205, 222, 0.12);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.055);
}
.chart-tool {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 10px;
  color: #b9d8eb;
  background: rgba(255, 255, 255, 0.055);
  cursor: pointer;
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, opacity 0.18s ease;
}
.chart-tool:hover:not(:disabled) {
  transform: translateY(-1px);
  color: #ffffff;
  background: rgba(59, 159, 217, 0.22);
}
.chart-tool:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}
.chart-zoom-value {
  width: 44px;
  text-align: center;
  color: #9fb7c6;
  font-size: 0.72rem;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
}

.chart-container.glass .chart-type-badge {
  background: rgba(59, 159, 217, 0.12);
  border-color: rgba(59, 159, 217, 0.24);
  color: #91d5ff;
}

/* ── Loading ── */
.loading-overlay {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 0.85rem;
  color: #8899aa;
  font-size: 0.9rem;
}
.chart-container.glass .loading-overlay {
  color: #9fb7c6;
}
.chart-skeleton-line,
.chart-skeleton-panel,
.chart-skeleton-panel span {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
}
.chart-skeleton-line {
  height: 14px;
  max-width: 100%;
}
.chart-skeleton-line.short {
  width: 42%;
}
.chart-skeleton-panel {
  height: min(280px, 46vh);
  display: grid;
  grid-template-columns: repeat(8, minmax(18px, 1fr));
  align-items: end;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(180, 205, 222, 0.1);
}
.chart-skeleton-panel span {
  min-height: 52px;
  height: 58%;
}
.chart-skeleton-panel span:nth-child(2n) { height: 46%; }
.chart-skeleton-panel span:nth-child(3n) { height: 68%; }
.chart-skeleton-line::after,
.chart-skeleton-panel::after,
.chart-skeleton-panel span::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.14), transparent);
  animation: shimmer 1.35s ease-in-out infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes shimmer { to { transform: translateX(100%); } }

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
.chart-container.glass .error-box {
  color: #fecaca;
  background: rgba(127, 29, 29, 0.16);
  border-color: rgba(248, 113, 113, 0.25);
}
.no-data-box {
  color: #64748b;
  background: rgba(100, 116, 139, 0.08);
  border-color: rgba(100, 116, 139, 0.25);
}
.chart-container.glass .no-data-box {
  color: #a8bfd0;
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(180, 205, 222, 0.12);
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
  padding: 0;
  overflow: hidden;
}
.chart-container.glass .chart-wrapper {
  background: rgba(7, 14, 20, 0.38);
  border-color: rgba(180, 205, 222, 0.12);
  border-radius: 14px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 12px 28px rgba(1, 10, 17, 0.12);
}
.chart-viewport {
  width: 100%;
  height: 100%;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
  cursor: grab;
  scrollbar-color: rgba(59, 159, 217, 0.58) rgba(255, 255, 255, 0.06);
  scrollbar-width: thin;
}
.chart-wrapper.panning .chart-viewport {
  cursor: grabbing;
  user-select: none;
}
.chart-viewport::-webkit-scrollbar {
  height: 10px;
}
.chart-viewport::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.045);
  border-radius: 999px;
}
.chart-viewport::-webkit-scrollbar-thumb {
  background: linear-gradient(90deg, rgba(59, 159, 217, 0.72), rgba(111, 231, 135, 0.58));
  border-radius: 999px;
  border: 2px solid rgba(7, 14, 20, 0.38);
}
.chart-scroll-spacer {
  position: relative;
  min-width: 100%;
  height: 100%;
  transition: width 0.24s ease;
}
.chart {
  position: absolute !important;
  inset: 0;
  width: 100% !important;
  height: 100% !important;
}

.pixel-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.stat-card {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 12px;
  background: rgba(40, 95, 150, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.stat-card span {
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.stat-card strong {
  color: #1b485f;
  font-size: 0.95rem;
  font-family: 'JetBrains Mono', monospace;
}
.chart-container.glass .stat-card {
  border-color: rgba(180, 205, 222, 0.1);
  background: rgba(255, 255, 255, 0.055);
}
.chart-container.glass .stat-card span {
  color: #8ba8bb;
}
.chart-container.glass .stat-card strong {
  color: #74f08b;
}

/* ── Record hint ── */
.record-hint {
  font-size: 0.72rem;
  color: #94a3b8;
  text-align: right;
  padding: 4px 2px 0;
}
.chart-container.glass .record-hint {
  color: #8ba8bb;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .chart-container { padding: 1rem; }
  .chart-container.glass { padding: 0; }
  .chart-controls { flex-direction: column; align-items: flex-start; gap: 0.75rem; }
  .control-group { width: 100%; }
  .layer-control { max-width: none; }
  .view-control { width: 100%; }
  .toggle-switch { width: 100%; }
  .toggle-option { flex: 1; }
  .select { min-width: 0; width: 100%; }
  .chart-toolbar { width: 100%; justify-content: center; }
  .chart-type-badge { margin-left: 0; }
  .layer-tabs { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .pixel-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 480px) {
  .layer-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .layer-tab { height: 36px; font-size: 0.78rem; }
  .pixel-stats { gap: 8px; }
}
</style>
