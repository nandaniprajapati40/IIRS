<template>
  <div :class="{ dark: isDark }">

    <!-- ════ HOME PAGE ════ -->
    <Home
      v-if="currentView === 'home'"
      @launch="showDashboard"
      @faqs="showFAQs"
    />

    <!-- ════ FAQS PAGE ════ -->
    <FAQsView
      v-else-if="currentView === 'faqs'"
      @launch="showDashboard"
    />

    <!-- ════ DASHBOARD ════ -->
    <div v-else-if="currentView === 'dashboard'" class="dashboard-shell">

      <!-- Header -->
      <header class="dash-header">
        <button @click="sidebarOpen = !sidebarOpen" class="icon-btn menu-btn">
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
          </svg>
        </button>

        <img src="/assets/iirs.png" class="dash-logo" onerror="this.style.display='none'" />
        <img src="/assets/isro.png" class="dash-logo" onerror="this.style.display='none'" />
        <div class="header-divider"></div>

        <div class="header-titles">
          <p class="header-title">Crop Irrigation Water Requirements · Udham Singh Nagar</p>
          <!-- <p class="header-sub">CWR → PET model &nbsp;·&nbsp; IWR → Rainfall model &nbsp;·&nbsp; SARIMAX(1,1,1) 15-day</p> -->
        </div>

        <div class="header-right">
          <!-- Calendar Button -->
          <button class="calendar-btn" @click="calendarOpen = !calendarOpen" :class="{ active: calendarOpen }">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
              <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
            </svg>
            <span>{{ selectedCalendarDate ? formatDisplayDate(selectedCalendarDate) : 'Select Date' }}</span>
          </button>

          <!-- <button @click="isDark = !isDark" class="icon-btn theme-btn">{{ isDark ? '☀️' : '🌙' }}</button> -->
          <button @click="showHome" class="home-btn">⌂ Home</button>
        </div>
      </header>

      <!-- Body -->
      <div class="dash-body">

        <!-- Sidebar -->
        <aside class="sidebar-panel" :class="sidebarOpen ? 'open' : 'closed'">
          <div class="sidebar-content">

            <p class="sidebar-section-label">Map Layers</p>

            <div v-for="layer in layerDefs" :key="layer.key">
              <div
                class="layer-card"
                :class="{ active: layers[layer.key] }"
                @click="layers[layer.key] = !layers[layer.key]"
              >
                <div class="layer-left">
                  <span class="layer-ico">{{ layer.icon }}</span>
                  <div>
                    <p class="layer-key">{{ layer.key.toUpperCase() }}</p>
                    <p class="layer-name">{{ layer.name }}</p>
                  </div>
                </div>
                <div class="toggle-track" :class="{ on: layers[layer.key] }">
                  <div class="toggle-thumb" :class="{ on: layers[layer.key] }"></div>
                </div>
              </div>

              <div v-if="layers[layer.key]" class="legend-strip">
                <div class="legend-labels-horizontal">
                  <span>{{ layer.minLabel }}</span>
                  <span>{{ layer.midLabel }}</span>
                  <span>{{ layer.maxLabel }}</span>
                </div>
                <div
                  class="legend-bar-horizontal"
                  :class="`legend-grad-${layer.key}`"
                  @mousemove="(e) => showLegendValue(e, layer.key)"
                  @mouseleave="legendValue = null"
                  @click="filterByLegendRange($event, layer.key)"
                ></div>
              </div>
            </div>

            <!-- Opacity control -->
            <div class="ctrl-card">
              <div class="ctrl-row">
                <span>Layer Opacity</span>
                <span class="ctrl-val">{{ Math.round(opacity * 100) }}%</span>
              </div>
              <input type="range" v-model="opacity" min="0" max="1" step="0.05" class="range-slider" />
            </div>

          </div>
        </aside>

        <!-- Map area -->
        <div class="map-area">
          <MapView
            ref="mapViewRef"
            :layers="layers"
            :forecastDays="forecastDays"
            :slot="currentslot"
            :opacity="Number(opacity)"
            :selectedDate="selectedCalendarDate"
            :isDark="isDark"
            @calendar-open="calendarOpen = true"
            :availableDates="availableDates" 
          />
          <div v-if="legendValue" class="legend-tooltip"
            :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }">
            {{ legendValue }}
          </div>
        </div>

      </div>

      <!-- ════ CALENDAR OVERLAY ════ -->
      <Teleport to="body">
        <div v-if="calendarOpen" class="cal-backdrop" @click.self="calendarOpen = false">
          <div class="cal-panel">
            <div class="cal-header">
              <div class="cal-title-row">
                <svg width="16" height="16" fill="none" stroke="#00D4A8" viewBox="0 0 24 24">
                  <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
                  <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                <span class="cal-title">Sentinel Acquisition Calendar</span>
                <button class="cal-close" @click="calendarOpen = false">×</button>
              </div>
              <p class="cal-subtitle">
                Rolling 60-day window · 
                <span class="cal-range">{{ windowStart }} → {{ windowEnd }}</span>
              </p>
              <div class="cal-legend-row">
                <span class="cal-legend-dot dot-data"></span><span>Data available</span>
                <span class="cal-legend-dot dot-selected"></span><span>Selected</span>
                <span class="cal-legend-dot dot-today"></span><span>Today</span>
                <span class="cal-legend-dot dot-empty"></span><span>No data</span>
              </div>
            </div>

            <!-- Loading state -->
            <div v-if="calLoading" class="cal-loading">
              <div class="cal-spinner"></div>
              <span>Fetching available dates…</span>
            </div>

            <!-- Calendar grid -->
            <div v-else class="cal-scroll">
              <div v-for="month in calMonths" :key="month.key" class="cal-month">
                <p class="cal-month-label">{{ month.label }}</p>
                <div class="cal-grid">
                  <!-- Day-of-week headers -->
                  <div v-for="d in ['Su','Mo','Tu','We','Th','Fr','Sa']" :key="d" class="cal-dow">{{ d }}</div>
                  <!-- Empty leading cells -->
                  <div v-for="n in month.startOffset" :key="'e'+n" class="cal-day cal-day-empty"></div>
                  <!-- Actual days -->
                  <div
                    v-for="day in month.days"
                    :key="day.iso"
                    class="cal-day"
                    :class="{
                      'cal-day-has-data':  day.hasData,
                      'cal-day-selected':  day.iso === selectedCalendarDate,
                      'cal-day-today':     day.isToday,
                      'cal-day-future':    day.isFuture,
                      'cal-day-clickable': day.hasData,
                    }"
                    :title="day.hasData ? 'Data available — ' + day.layers.join(', ') : day.isFuture ? 'Future date' : 'No data'"
                    @click="day.hasData && selectCalendarDate(day.iso)"
                  >
                    <span class="cal-day-num">{{ day.day }}</span>
                    <span v-if="day.hasData" class="cal-day-dot"></span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Footer: selected date info -->
            <div class="cal-footer" v-if="selectedCalendarDate">
              <div class="cal-sel-info">
                <svg width="13" height="13" fill="none" stroke="#00D4A8" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke-width="2"/>
                  <path stroke-linecap="round" stroke-width="2" d="M12 8v4l3 3"/>
                </svg>
                <span>Selected: <strong>{{ formatDisplayDate(selectedCalendarDate) }}</strong></span>
                <span class="cal-sel-layers" v-if="selectedDateLayers.length">
                  · Layers: {{ selectedDateLayers.join(', ').toUpperCase() }}
                </span>
              </div>
              <button class="cal-clear-btn" @click="selectedCalendarDate = null">Clear</button>
            </div>
          </div>
        </div>
      </Teleport>

    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, watch } from 'vue'
import Home from './components/Home.vue'
import MapView from './components/MapView.vue'
import FAQsView from './components/FAQsView.vue'

const currentView = ref('home')
const isDark = ref(true)
const sidebarOpen = ref(true)
const mapViewRef = ref(null)

// Navigation functions
function showFAQs() {
  currentView.value = 'faqs'
}

function showHome() {
  currentView.value = 'home'
}

function showDashboard() {
  currentView.value = 'dashboard'
}

const layers = reactive({ savi: false, kc: false, cwr: false, iwr: false })
const forecastDays = ref('today')
const opacity = ref(1.0)

const legendValue = ref(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

// ── Calendar + Slot State ─────────────────────────────────────
const calendarOpen = ref(false)
const calLoading = ref(false)
const availableDates = ref([])
const selectedCalendarDate = ref(null)
const currentslot = ref('today')

const API_BASE = 'http://localhost:8000'

// Fetch available dates from backend whenever calendar is opened
watch(calendarOpen, async (open) => {
  if (!open) return
  calLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/history`)
    const data = await res.json()
    availableDates.value = (data.slots || []).map(s => ({
      date: s.date,
      layers: Object.keys(s.obs_means || {}).filter(k => s.obs_means[k] !== null),
      slot: s.slot
    }))
  } catch (e) {
    console.error('Calendar fetch error:', e)
    availableDates.value = []
  } finally {
    calLoading.value = false
  }
})

const dateToSlotMap = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => map.set(d.date, d.slot))
  return map
})

onMounted(async () => {
  try {
    const res = await fetch(`${API_BASE}/api/history`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()

    availableDates.value = (data.slots || []).map(s => ({
      date: s.date,
      slot: s.slot,
      layers: Object.keys(s.obs_means || {}).filter(k => s.obs_means[k] !== null)
    }))

    if (availableDates.value.length > 0) {
      const latest = availableDates.value[0]
      selectedCalendarDate.value = latest.date
      currentslot.value = latest.slot || 'today'
    }
  } catch (e) {
    console.error('Initial history fetch error:', e)
    availableDates.value = []
  }
})

function selectCalendarDate(iso) {
  selectedCalendarDate.value = iso
  currentslot.value = dateToSlotMap.value.get(iso) || 'today'
  calendarOpen.value = false
}

function formatDisplayDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

// Build rolling 60-day window [today-59 .. today]
const today = ref(new Date())
const windowEndDate = computed(() => {
  if (!today.value) return null
  return new Date(today.value)
})

const windowStartDate = computed(() => {
  if (!today.value) return null
  const d = new Date(today.value)
  d.setDate(d.getDate() - 59)
  return d
})

const windowEnd = computed(() => {
  if (!windowEndDate.value) return null
  return windowEndDate.value.toISOString().slice(0, 10)
})

const windowStart = computed(() => {
  if (!windowStartDate.value) return null
  return windowStartDate.value.toISOString().slice(0, 10)
})

const availableDateSet = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => {
    map.set(d.date, {
      layers: Array.isArray(d.layers) ? d.layers : [],
      slot: d.slot
    })
  })
  return map
})

// Layers for the selected date
const selectedDateLayers = computed(() => {
  if (!selectedCalendarDate.value) return []
  const dateInfo = availableDateSet.value.get(selectedCalendarDate.value)
  return dateInfo ? dateInfo.layers : []
})

// Build month structures for the 60-day window
const calMonths = computed(() => {
  const months = []
  if (!windowStartDate.value || !windowEndDate.value) return months
  
  const cursor = new Date(windowStartDate.value)
  const end = new Date(windowEndDate.value)
  const todayISO = today.value ? today.value.toLocaleDateString('en-CA') : null

  let currentMonth = null

  while (cursor <= end) {
    const y = cursor.getFullYear()
    const m = cursor.getMonth()
    const mk = `${y}-${m}`

    if (!currentMonth || currentMonth.monthNum !== m || currentMonth.year !== y) {
      if (currentMonth) months.push(currentMonth)
      const firstOfMonth = new Date(y, m, 1)
      currentMonth = {
        key: mk,
        label: firstOfMonth.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }),
        year: y,
        monthNum: m,
        startOffset: firstOfMonth.getDay(),
        days: [],
      }
    }

    const iso = cursor.toLocaleDateString('en-CA')
    const dateInfo = availableDateSet.value.get(iso)
    const hasData = !!dateInfo
    const isFuture = cursor > today.value

    currentMonth.days.push({
      iso,
      day: cursor.getDate(),
      hasData,
      layers: hasData ? dateInfo.layers : [],
      isToday: iso === todayISO,
      isFuture,
    })

    cursor.setDate(cursor.getDate() + 1)
  }

  if (currentMonth) months.push(currentMonth)
  return months
})

// ── Layer defs ──────────────────────────────────────────────────────────
const layerDefs = [
  { key:'savi', name:'Soil Adjusted Vegetation Index', maxLabel:'1.0',   midLabel:'0.0',  minLabel:'-1.0', icon:'🌿' },
  { key:'kc', name:'Crop Coefficient (FAO-56)',       maxLabel:'1.15',  midLabel:'0.7',  minLabel:'0.30', icon:'💧' },
  { key:'cwr', name:'Crop Water Requirement (mm)',     maxLabel:'10 mm', midLabel:'5 mm', minLabel:'0 mm', icon:'💦' },
  { key:'iwr', name:'Irrigation Water Requirement (mm)', maxLabel:'10 mm', midLabel:'5 mm', minLabel:'0 mm', icon:'🚿' },
]

const legendBreakpoints = {
  savi:[-1,-0.8,-0.6,-0.4,-0.2,0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1],
  kc:  [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5],
  cwr: [0,1,2,3,4,4.5,5,5.5,6,6.5,7,7.5,8,8.5,9,9.5,10],
  iwr: [0,1,2,3,4,5,6,7,8,9,10],
}
const legendRanges = {
  savi:{min:-1,max:1}, kc:{min:0,max:1.5}, cwr:{min:0,max:10}, iwr:{min:0,max:10},
}

function updateTooltipPos(e) { 
  tooltipX.value = e.clientX + 12
  tooltipY.value = e.clientY - 10 
}

function showLegendValue(e, layer) {
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  const b = legendBreakpoints[layer]
  const idx = Math.min(b.length - 2, Math.max(0, Math.floor(pct * (b.length - 1))))
  legendValue.value = `${layer.toUpperCase()}: ${b[idx]} – ${b[idx + 1] || b[idx]}`
  tooltipX.value = e.clientX + 12
  tooltipY.value = e.clientY - 10
}

function filterByLegendRange(e, layer) {
  if (!mapViewRef.value?.applyFilter) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  const r = legendRanges[layer]
  const v = r.min + pct * (r.max - r.min)
  const d = layer === 'savi' ? 0.2 : layer === 'kc' ? 0.3 : 1.5
  mapViewRef.value.applyFilter(layer, Math.max(r.min, v - d), Math.min(r.max, v + d))
}

</script>

<style>
/* Keep all the existing CSS from your App.vue - it remains unchanged */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

/* ── Global accent token ────────────────────────────────── */
:root {
  --accent-teal-glow: #00D4A8;
  --accent-teal-glow-10: rgba(0, 212, 168, 0.10);
  --accent-teal-glow-15: rgba(0, 212, 168, 0.15);
  --accent-teal-glow-20: rgba(0, 212, 168, 0.20);
  --accent-teal-glow-25: rgba(0, 212, 168, 0.25);
  --accent-teal-glow-30: rgba(0, 212, 168, 0.30);
  --accent-teal-glow-35: rgba(0, 212, 168, 0.35);
  --accent-teal-glow-40: rgba(0, 212, 168, 0.40);
  --accent-teal-glow-50: rgba(0, 212, 168, 0.50);
  --accent-teal-glow-60: rgba(0, 212, 168, 0.60);
}

/* ── Shell layout ───────────────────────────────────────── */
.dashboard-shell {
  font-family: 'Space Grotesk', sans-serif;
  background: #060E1A;
  color: #E8F4FD;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  /* subtle ambient glow from the teal accent */
  box-shadow: inset 0 0 120px -60px var(--accent-teal-glow-10);
}

/* ── Header ─────────────────────────────────────────────── */
.dash-header {
  height: 64px;
  background: #040F24;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
  flex-shrink: 0;
  z-index: 100;
}

.dash-logo { height: 38px; object-fit: contain; flex-shrink: 0; }
.header-divider {
  width: 1px; height: 32px;
  background: rgba(255,255,255,0.1); flex-shrink: 0;
}
.header-titles {
  position: absolute; left:50%; transform:translateX(-50%);
  text-align:center; min-width:0; overflow:hidden;
}
.header-title {
  font-size:0.85rem; color: var(--accent-teal-glow); font-family:'JetBrains Mono',monospace;
  font-weight:600; text-transform:uppercase; letter-spacing:0.06em;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin:0 0 4px;
  text-shadow: 0 0 18px var(--accent-teal-glow-40);
}
.header-sub {
  font-size:0.7rem; color:#6B8BAD; font-family:'JetBrains Mono',monospace;
  font-weight:400; white-space:nowrap; margin:0;
}
.header-right { margin-left:auto; display:flex; align-items:center; gap:12px; flex-shrink:0; }

/* ── Calendar button ─────────────────────────────────────── */
.calendar-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 50px;
  border: 1px solid var(--accent-teal-glow-30);
  background: var(--accent-teal-glow-10);
  color: var(--accent-teal-glow);
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.calendar-btn:hover,
.calendar-btn.active {
  background: var(--accent-teal-glow-15);
  border-color: var(--accent-teal-glow-60);
  box-shadow: 0 0 18px var(--accent-teal-glow-20);
}

/* ── Buttons ─────────────────────────────────────────────── */
.icon-btn {
  width:38px; height:38px; border-radius:10px;
  display:flex; align-items:center; justify-content:center;
  background:transparent; border:none; cursor:pointer;
  color:#6B8BAD; font-size:1rem; transition:all 0.2s; flex-shrink:0;
}
.icon-btn:hover { color:#fff; background:rgba(255,255,255,0.08); }
.theme-btn { font-size:1.1rem; }

.home-btn {
  padding:6px 16px; border-radius:10px; font-size:0.8rem;
  font-family:'JetBrains Mono',monospace; font-weight:500;
  color:#6B8BAD; background:transparent; border:1px solid transparent;
  cursor:pointer; transition:all 0.2s; white-space:nowrap;
}
.home-btn:hover { color: var(--accent-teal-glow); border-color: var(--accent-teal-glow-30); background: var(--accent-teal-glow-10); }

/* ── Body ───────────────────────────────────────────────── */
.dash-body { flex:1; display:flex; overflow:hidden; min-height:0; }

/* ── Sidebar ─────────────────────────────────────────────── */
.sidebar-panel {
  background:#010a1c; border-right:1px solid rgba(255,255,255,0.07);
  overflow-y:auto; overflow-x:hidden;
  transition:width 0.3s cubic-bezier(0.4,0,0.2,1); flex-shrink:0; z-index:40;
}
.sidebar-panel.open  { width:300px; }
.sidebar-panel.closed { width:0; }
.sidebar-panel::-webkit-scrollbar { width:4px; }
.sidebar-panel::-webkit-scrollbar-thumb { background: var(--accent-teal-glow-20); border-radius:2px; }

.sidebar-content { padding:20px; min-width:280px; }

.sidebar-section-label {
  font-size:0.75rem; color:#6B8BAD; font-family:'JetBrains Mono',monospace;
  font-weight:600; text-transform:uppercase; letter-spacing:0.12em;
  margin:0 0 16px; padding-bottom:10px;
  border-bottom:1px solid rgba(255,255,255,0.06);
}

/* ── Layer cards ─────────────────────────────────────────── */
.layer-card {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 14px; border-radius:12px;
  border:1px solid rgba(255,255,255,0.07);
  background:rgba(255,255,255,0.025);
  cursor:pointer; transition:all 0.2s; margin-bottom:8px;
}
.layer-card:hover { border-color:rgba(255,255,255,0.14); transform:translateY(-1px); }
.layer-card.active { border-color: var(--accent-teal-glow-35); background: var(--accent-teal-glow-10); }
.layer-left { display:flex; align-items:center; gap:12px; }
.layer-ico { font-size:1.3rem; width:32px; text-align:center; }
.layer-key { font-size:0.9rem; font-weight:700; color:#E8F4FD; line-height:1.2; margin:0; }
.layer-name { font-size:0.7rem; color:#6B8BAD; margin:2px 0 0; line-height:1.4; }

/* ── Toggle ──────────────────────────────────────────────── */
.toggle-track {
  width:44px; height:22px; border-radius:12px;
  background:#2A3B55; transition:background 0.2s;
  position:relative; flex-shrink:0;
}
.toggle-track.on { background: var(--accent-teal-glow); box-shadow: 0 0 10px var(--accent-teal-glow-40); }
.toggle-thumb {
  position:absolute; top:2px; left:2px;
  width:18px; height:18px; border-radius:50%;
  background:white; transition:all 0.2s; box-shadow:0 2px 4px rgba(0,0,0,0.3);
}
.toggle-thumb.on { left:24px; }

/* Legend horizontal strip */
.legend-strip {
  display: flex;flex-direction: column;gap: 8px;padding: 10px 12px 14px;margin: 0 10px 10px 10px;background: rgba(0, 0, 0, 0.2);border-radius: 8px;
}

.legend-labels-horizontal {
  display: flex;justify-content: space-between;width: 100%;padding: 0 4px;
}

.legend-labels-horizontal span {
  font-size: 0.65rem;color: #6B8BAD;font-family: 'JetBrains Mono', monospace;font-weight: 500;
}

.legend-bar-horizontal {
  width: 100%;height: 28px;border-radius: 6px;cursor: pointer;transition: transform 0.2s;
}

.legend-bar-horizontal:hover {
  transform: scaleY(1.1);
}

/* Horizontal gradients */
.legend-grad-savi {
  background: linear-gradient(to right, #8B0000 0%, #FF4500 20%, #FFD700 45%, #32CD32 65%, #006400 100%);
}

.legend-grad-kc {
  background: linear-gradient(to right, #FFD700 0%, #90EE90 35%, #32CD32 60%, #8B4513 100%);
}

.legend-grad-cwr {
  background: linear-gradient(to right, #FF4444 0%, #FFA500 25%, #FFFF00 50%, #0000CD 80%, #4B0082 100%);
}

.legend-grad-iwr {
  background: linear-gradient(to right, #E0F7FA 0%, #4DD0E1 30%, #00BCD4 55%, #00695C 80%, #1A237E 100%);
}

/* Tooltip positioning for horizontal legend */
.legend-tooltip {
  position: fixed;background: rgba(0,0,0,0.95);color: #E8F4FD;font-size: 0.75rem;padding: 6px 14px;border-radius: 8px;pointer-events: none;z-index: 9999;font-family: 'JetBrains Mono', monospace;font-weight: 500;border: 1px solid rgba(0,212,168,0.3);box-shadow: 0 4px 12px rgba(0,0,0,0.5);white-space: nowrap;
}

/* ── Control cards ───────────────────────────────────────── */
.ctrl-card { margin-top:16px; padding:14px 16px; border-radius:12px; border:1px solid rgba(255,255,255,0.07); background:rgba(255,255,255,0.025); }
.ctrl-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-size:0.85rem; color:#6B8BAD; }
.ctrl-val { color: var(--accent-teal-glow); font-weight:700; font-family:'JetBrains Mono',monospace; font-size:0.85rem; }
.ctrl-label { font-size:0.7rem; color:#6B8BAD; font-family:'JetBrains Mono',monospace; font-weight:600; text-transform:uppercase; letter-spacing:0.1em; margin:0 0 8px; }
.ctrl-info { font-size:0.75rem; color:#6B8BAD; line-height:1.6; margin:0; }
.ctrl-info em { color:#8AACCC; font-style:normal; font-weight:500; }
.ctrl-info strong { color: var(--accent-teal-glow); font-weight:700; }

.range-slider {
  width:100%; height:5px; border-radius:3px; appearance:none;
  background:#2A3B55; cursor:pointer; outline:none;
}
.range-slider::-webkit-slider-thumb {
  appearance:none; width:18px; height:18px; border-radius:50%;
  background: var(--accent-teal-glow); cursor:pointer;
  box-shadow: 0 0 10px var(--accent-teal-glow-40); transition:transform 0.2s;
}
.range-slider::-webkit-slider-thumb:hover { transform:scale(1.2); box-shadow: 0 0 16px var(--accent-teal-glow-60); }

/* ── Map area ────────────────────────────────────────────── */
.map-area { flex:2; position:relative; overflow:hidden; min-width:0; min-height:0; }

/* ════════════════════════════════════════════════════════════
   CALENDAR OVERLAY
   ════════════════════════════════════════════════════════════ */
.cal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.65);
  backdrop-filter: blur(4px);
  z-index: 5000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 72px;
  animation: calFadeIn 0.18s ease;
}
@keyframes calFadeIn { from{opacity:0} to{opacity:1} }

.cal-panel {
  background: #040F24;
  border: 1px solid var(--accent-teal-glow-25);
  border-radius: 20px;
  width: min(720px, 96vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 70px rgba(0,0,0,0.7), 0 0 0 1px var(--accent-teal-glow-10), 0 0 40px -10px var(--accent-teal-glow-20);
  overflow: hidden;
  animation: calSlideDown 0.2s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes calSlideDown {
  from { opacity:0; transform:translateY(-18px); }
  to   { opacity:1; transform:translateY(0); }
}

/* Header */
.cal-header {
  padding: 18px 22px 14px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  flex-shrink: 0;
}
.cal-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.cal-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #E8F4FD;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
  flex: 1;
}
.cal-close {
  width: 28px; height: 28px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 50%;
  color: #6B8BAD;
  font-size: 1.1rem;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
  line-height: 1;
}
.cal-close:hover { background: var(--accent-teal-glow-15); color: var(--accent-teal-glow); border-color: var(--accent-teal-glow-40); }

.cal-subtitle {
  font-size: 0.72rem;
  color: #6B8BAD;
  font-family: 'JetBrains Mono', monospace;
  margin: 0 0 10px;
}
.cal-range { color: #8AACCC; font-weight: 600; }

.cal-legend-row {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 0.7rem;
  color: #6B8BAD;
  font-family: 'JetBrains Mono', monospace;
  flex-wrap: wrap;
}
.cal-legend-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.dot-data     { background: var(--accent-teal-glow); box-shadow: 0 0 8px var(--accent-teal-glow-60); }
.dot-selected { background: #fff; border: 2px solid var(--accent-teal-glow); }
.dot-today    { background: transparent; border: 2px solid #FFD700; }
.dot-empty    { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); }

/* Scroll area */
.cal-scroll {
  overflow-y: auto;
  flex: 1;
  padding: 16px 22px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  scrollbar-width: thin;
  scrollbar-color: var(--accent-teal-glow-20) transparent;
}
.cal-scroll::-webkit-scrollbar { width: 4px; }
.cal-scroll::-webkit-scrollbar-thumb { background: var(--accent-teal-glow-20); border-radius: 2px; }

/* Month block */
.cal-month {}
.cal-month-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--accent-teal-glow);
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 10px;
}

/* 7-column grid */
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
}
.cal-dow {
  font-size: 0.62rem;
  color: #4A6A8A;
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
  padding: 4px 0;
  font-weight: 600;
  text-transform: uppercase;
}
.cal-day-empty { height: 38px; }

.cal-day {
  position: relative;
  height: 38px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.05);
  transition: all 0.15s;
  user-select: none;
}
.cal-day-num {
  font-size: 0.78rem;
  font-family: 'JetBrains Mono', monospace;
  color: #4A6A8A;
  line-height: 1;
}
.cal-day-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--accent-teal-glow);
  box-shadow: 0 0 5px var(--accent-teal-glow-50);
  margin-top: 2px;
  flex-shrink: 0;
}

/* Has data */
.cal-day-has-data {
  background: var(--accent-teal-glow-10);
  border-color: var(--accent-teal-glow-25);
}
.cal-day-has-data .cal-day-num { color: #C8DFF0; }
.cal-day-clickable { cursor: pointer; }
.cal-day-clickable:hover {
  background: var(--accent-teal-glow-20);
  border-color: var(--accent-teal-glow-50);
  transform: scale(1.06);
  box-shadow: 0 0 10px var(--accent-teal-glow-20);
}

/* Selected */
.cal-day-selected {
  background: var(--accent-teal-glow-25) !important;
  border-color: var(--accent-teal-glow) !important;
  box-shadow: 0 0 16px var(--accent-teal-glow-35);
}
.cal-day-selected .cal-day-num { color: var(--accent-teal-glow); font-weight: 700; }

/* Today */
.cal-day-today {
  border-color: rgba(255,215,0,0.5);
}
.cal-day-today .cal-day-num { color: #FFD700; }

/* Future */
.cal-day-future {
  opacity: 0.35;
  cursor: not-allowed;
}

/* Loading */
.cal-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 48px 22px;
  color: #6B8BAD;
  font-size: 0.82rem;
  font-family: 'JetBrains Mono', monospace;
}
.cal-spinner {
  width: 22px; height: 22px;
  border: 2px solid var(--accent-teal-glow-20);
  border-top-color: var(--accent-teal-glow);
  border-radius: 50%;
  animation: calSpin 0.8s linear infinite;
}
@keyframes calSpin { to { transform: rotate(360deg); } }

/* Footer */
.cal-footer {
  padding: 12px 22px;
  border-top: 1px solid rgba(255,255,255,0.07);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.cal-sel-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  color: #8AACCC;
  font-family: 'JetBrains Mono', monospace;
  flex-wrap: wrap;
}
.cal-sel-info strong { color: var(--accent-teal-glow); }
.cal-sel-layers { color: #6B8BAD; }
.cal-clear-btn {
  padding: 5px 14px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: #6B8BAD;
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.cal-clear-btn:hover { color: #FF6B6B; border-color: rgba(255,107,107,0.4); background: rgba(255,107,107,0.07); }

/* ── Responsive ──────────────────────────────────────────── */
@media (max-width:1024px) {
  .header-titles { position:static; transform:none; margin-left:auto; }
  .header-title { font-size:0.8rem; }
  .header-sub { font-size:0.65rem; }
}
@media (max-width:768px) {
  .dash-header { height:58px; padding:0 12px; gap:10px; }
  .dash-logo { height:32px; }
  .header-divider { height:24px; }
  .header-titles { display:none; }
  .sidebar-panel.open { width:260px; }
  .sidebar-content { padding:16px; min-width:240px; }
  .layer-card { padding:10px 12px; }
  .layer-ico { font-size:1.1rem; width:28px; }
  .layer-key { font-size:0.8rem; }
  .layer-name { font-size:0.65rem; }
  .cal-panel { width: 98vw; max-height: 90vh; }
  .cal-header { padding: 14px 16px 12px; }
  .cal-scroll { padding: 12px 16px; }
  .cal-footer { padding: 10px 16px; }
}
@media (max-width:640px) {
  .calendar-btn span:last-child { display: none; }
  .calendar-btn { padding: 6px 10px; }
  .home-btn { padding:4px 12px; font-size:0.7rem; }
  .icon-btn { width:34px; height:34px; }
  .sidebar-panel.open { width:240px; }
  .sidebar-content { padding:14px; min-width:220px; }
  .legend-strip { height:70px; }
  .cal-day { height: 34px; }
}
@media (max-width:480px) {
  .dash-header { gap:6px; }
  .dash-logo { height:26px; }
  .home-btn { padding:4px 8px; font-size:0.65rem; }
  .icon-btn { width:32px; height:32px; }
  .sidebar-panel.open { width:220px; }
  .sidebar-content { padding:12px; min-width:200px; }
  .layer-card { padding:8px 10px; }
  .layer-ico { font-size:1rem; width:24px; }
  .layer-key { font-size:0.75rem; }
  .layer-name { font-size:0.6rem; }
  .toggle-track { width:38px; height:20px; }
  .toggle-thumb { width:16px; height:16px; }
  .toggle-thumb.on { left:20px; }
  .legend-strip { height:60px; gap:6px; }
  .legend-labels span { font-size:0.55rem; }
  .legend-bar { width:16px; }
  .ctrl-card { padding:12px; }
  .ctrl-row { font-size:0.75rem; }
  .ctrl-info { font-size:0.7rem; }
  .cal-day { height: 30px; }
  .cal-dow { font-size: 0.55rem; }
  .cal-day-num { font-size: 0.68rem; }
  .cal-grid { gap: 2px; }
}
</style>