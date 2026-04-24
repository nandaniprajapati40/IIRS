<template>
  <div :class="{ dark: isDark }">

    <!-- ════ HOME PAGE ════ -->
    <Home
      v-if="currentView === 'home'"
      :is-dark="isDark"
      @launch="showDashboard"
      @faqs="showFAQs"
      @toggle-theme="isDark = !isDark"
    />

    <!-- ════ FAQS PAGE ════ -->
    <FAQsView
      v-else-if="currentView === 'faqs'"
      @launch="showDashboard"
      @home="showHome"
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
        <button @click="showHome" class="home-btn">🏠</button>
        <img src="/assets/iirs.png" class="dash-logo" onerror="this.style.display='none'" />
        <img src="/assets/isro.png" class="dash-logo" onerror="this.style.display='none'" />
        <div class="header-divider"></div>

        <div class="header-titles">
          <p class="header-title">Crop Irrigation Water Requirements · Udham Singh Nagar</p>
        </div>

        <div class="header-right">
          <!-- Weather Widget Button -->
          <button class="weather-card" @click="toggleWeather">
            <span class="wc-icon">{{ selectedWeatherEntry ? getWeatherEmoji(selectedWeatherEntry.weathercode) : '🌤️' }}</span>
            <div class="wc-center">
              <span class="wc-location">📍 {{ userLocationName }}</span>
              <span class="wc-date">{{ formatDisplayDate(activeWeatherDate || todayISO) }}</span>
            </div>
            <span class="wc-temp">{{ selectedWeatherEntry ? Math.round(selectedWeatherEntry.tempMax) + '°C' : '--' }}</span>
          </button>

          <button class="trend-btn" @click="chartVisible = !chartVisible" :class="{ active: chartVisible }">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 19h16M7 16V9M12 16V5M17 16v-7"/>
            </svg>
            <span>{{ chartVisible ? 'Back' : 'Crop trends' }}</span>
          </button>

          <!-- Calendar Button -->
          <button class="calendar-btn" @click="calendarOpen = !calendarOpen" :class="{ active: calendarOpen }">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
              <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
            </svg>
                    <span>{{ selectedCalendarDate ? formatDisplayDate(selectedCalendarDate) : 'Today' }}</span>
          </button>
        </div>
      </header>

      <!-- Body -->
      <div class="dash-body">
        <!-- Sidebar -->
        <aside class="sidebar-panel" :class="sidebarOpen ? 'open' : 'closed'">
          <div class="sidebar-content">
            <p class="sidebar-section-label">Map Layers</p>
            <div v-for="layer in layerDefs" :key="layer.key">
              <div class="layer-card" :class="{ active: layers[layer.key] }" @click="layers[layer.key] = !layers[layer.key]">
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
                <div class="legend-bar-horizontal" :class="`legend-grad-${layer.key}`" @mousemove="(e) => showLegendValue(e, layer.key)" @mouseleave="legendValue = null" @click="filterByLegendRange($event, layer.key)"></div>
              </div>
            </div>
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
            :weatherSummary="mapWeatherSummary"
            :isDark="isDark"
            :chartVisible="chartVisible"
            @calendar-open="calendarOpen = true"
            :availableDates="availableDates"
            @location-selected="handleLocationSelected"
            @open-weather="weatherOpen = true"
            @update:chart-visible="chartVisible = $event"
          />
          <div v-if="legendValue" class="legend-tooltip" :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }">
            {{ legendValue }}
          </div>
        </div>
      </div>

      <!-- ════ SENTINEL CALENDAR OVERLAY ════ -->
      <Teleport to="body">
        <div v-if="calendarOpen" class="calendar-float-panel">
          <div class="cal-panel">
            <div class="cal-header">
              <div class="cal-title-row">
                <svg width="16" height="16" fill="none" stroke="#00D4A8" viewBox="0 0 24 24">
                  <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
                  <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                <span class="cal-title">Field Data Calendar</span>
                <button class="cal-close" @click="calendarOpen = false">×</button>
              </div>
              <p class="cal-subtitle">Available data dates are highlighted.</p>
            </div>

            <div v-if="calLoading" class="cal-loading">
              <div class="cal-spinner"></div>
              <span>Fetching available dates…</span>
            </div>

            <div v-else class="cal-scroll">
              <div v-for="month in calMonths" :key="month.key" class="cal-month">
                <p class="cal-month-label">{{ month.label }}</p>
                <div class="cal-grid">
                  <div v-for="d in ['Su','Mo','Tu','We','Th','Fr','Sa']" :key="d" class="cal-dow">{{ d }}</div>
                  <div v-for="n in month.startOffset" :key="'e'+n" class="cal-day cal-day-empty"></div>
                  <div v-for="day in month.days" :key="day.iso" class="cal-day" :class="{
                      'cal-day-has-data': day.hasData,
                      'cal-day-has-forecast': day.hasForecast,
                      'cal-day-selected': day.iso === selectedCalendarDate,
                      'cal-day-today': day.isToday,
                      'cal-day-future': day.isFuture,
                      'cal-day-past': day.isPast,
                      'cal-day-clickable': day.isSelectable,
                    }" :title="getCalendarDayTitle(day)" @click="day.isSelectable && selectCalendarDate(day.iso)">
                    <span class="cal-day-num">{{ day.day }}</span>
                    <span v-if="day.hasData" class="cal-day-dot"></span>
                    <span v-else-if="day.hasForecast" class="cal-day-dot cal-day-dot-forecast"></span>
                  </div>
                </div>
              </div>
            </div>

            <div class="cal-footer" v-if="selectedCalendarDate">
              <div class="cal-sel-info">
                <span>Selected: <strong>{{ formatDisplayDate(selectedCalendarDate) }}</strong></span>
                <span class="cal-sel-badge" v-if="selectedDateLayers.length">Data available</span>
                <span class="cal-sel-badge cal-sel-badge-forecast" v-else-if="selectedDateHasForecast">Forecast</span>
                <span class="cal-sel-badge cal-sel-badge-past" v-if="selectedDateIsPast">Historical</span>
              </div>
              <button class="cal-clear-btn" @click="clearCalendarSelection">Clear</button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- ════ WEATHER OVERLAY (Enhanced) ════ -->
      <Teleport to="body">
        <div v-if="weatherOpen" class="weather-panel-wrapper">
          <div class="weather-panel">
            <div class="weather-header">
              <div class="weather-title-row">
                <span class="weather-main-icon">{{ selectedWeatherEntry ? getWeatherEmoji(selectedWeatherEntry.weathercode) : '🌤️' }}</span>
                <div class="weather-title-meta">
                  <div class="weather-title">
                    {{ selectedWeatherEntry ? Math.round(selectedWeatherEntry.tempMax) + '°C' : '--' }}
                    <span class="weather-today-label">
                      {{ selectedWeatherEntry
                          ? formatWeatherFullDate(selectedWeatherEntry.date)
                          : 'Weather Forecast' }}
                    </span>
                  </div>
                  <div class="weather-loc-row">
                    📍 {{ userLocationName }}
                    <button class="weather-locate-btn" @click="relocateWeather" :disabled="weatherLoading" title="Use my current location">
                      <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="3" stroke-width="2"/>
                        <path stroke-linecap="round" stroke-width="2" d="M12 2v3M12 19v3M2 12h3M19 12h3"/>
                      </svg>
                      Locate
                    </button>
                  </div>
                </div>
                <button class="cal-close" @click="weatherOpen = false">×</button>
              </div>
            </div>

            <div v-if="weatherLoading" class="cal-loading">
              <div class="cal-spinner"></div>
              <span>{{ selectedDateIsPast ? 'Fetching historical weather...' : 'Fetching forecast...' }}</span>
            </div>

            <div v-else-if="weatherData" class="weather-content">
              <!-- Selected Day Hero -->
              <div class="weather-today-card" v-if="selectedWeatherEntry">
                <div class="today-left">
                  <span class="today-temp">{{ Math.round(selectedWeatherEntry.tempMax) }}°C</span>
                  <span class="today-desc">{{ getWeatherDesc(selectedWeatherEntry.weathercode) }}</span>
                  <span class="today-date-label">{{ formatWeatherFullDate(selectedWeatherEntry.date) }}</span>
                </div>
                <div class="today-right">
                  <div class="today-meta">
                    <span>↑ {{ Math.round(selectedWeatherEntry.tempMax) }}° ↓ {{ Math.round(selectedWeatherEntry.tempMin) }}°</span>
                    <span>💧 Rain: {{ selectedWeatherEntry.precip }} mm</span>
                    <span>💨 Wind: {{ selectedWeatherEntry.windspeed }} km/h</span>
                    <span>☀️ UV: {{ selectedWeatherEntry.uvindex }}</span>
                  </div>
                </div>
              </div>

              <!-- Forecast Cards -->
              <p class="forecast-label">
                {{ selectedDateIsPast ? 'Historical + ' : '' }}{{ weatherEntries.length }}-Day Forecast
              </p>
              <div class="forecast-grid">
                <div v-for="(entry, i) in weatherEntries" :key="entry.date" class="forecast-day-card" :class="{ 'fc-card-selected': selectedWeatherDateIndex === i }" @click="selectWeatherEntry(entry.date, i)">
                  <span class="fc-day">{{ entry.date === todayISO ? 'Today' : formatWeatherDay(entry.date) }}</span>
                  <span class="fc-icon">{{ getWeatherEmoji(entry.weathercode) }}</span>
                  <span class="fc-temp">{{ Math.round(entry.tempMax) }}°</span>
                  <span class="fc-precip" v-if="entry.precip > 0">💧 {{ entry.precip }}mm</span>
                </div>
              </div>

              <!-- Data Sources -->
              <div class="wth-sources-section">
                <div class="wth-sources-inline">
                  <a
                    v-for="(src, index) in weatherSources"
                    :key="src.name"
                    :href="src.url"
                    target="_blank"
                    rel="noopener"
                    class="wth-source-inline-link"
                  >
                    {{ src.name }}<span v-if="index < weatherSources.length - 1" class="wth-source-sep">•</span>
                  </a>
                </div>
                <p class="wth-update-note">Last updated: {{ weatherFetchedAt || '—' }} · Coords: {{ weatherLat.toFixed(4) }}, {{ weatherLon.toFixed(4) }}</p>
              </div>
            </div>
            <div v-else class="weather-error">
              <p>Unable to load weather data.</p>
              <button @click="fetchWeather()" class="retry-btn">Retry</button>
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

function showFAQs()      { currentView.value = 'faqs' }
function showHome()      { currentView.value = 'home' }
function showDashboard() { currentView.value = 'dashboard' }

const layers     = reactive({ savi: false, kc: false, cwr: false, iwr: false })
const forecastDays = ref('today')
const opacity    = ref(1.0)
const chartVisible = ref(false)
const legendValue = ref(null)
const tooltipX   = ref(0)
const tooltipY   = ref(0)

// Sentinel Calendar State
const calendarOpen          = ref(false)
const calLoading            = ref(false)
const availableDates        = ref([])
const selectedCalendarDate  = ref(null)
const currentslot           = ref('today')
const API_BASE              = 'http://localhost:8000'
const todayISO = formatLocalISO(new Date())

// Weather State
const weatherOpen             = ref(false)
const weatherLoading          = ref(false)
const weatherData             = ref(null)
const weatherFetchedAt        = ref(null)
const userLocationName        = ref('Udham Singh Nagar')
const weatherLat              = ref(28.98)
const weatherLon              = ref(79.40)
const selectedWeatherDateIndex = ref(0)
const activeWeatherDate       = ref(null)
const WEATHER_FORECAST_DAYS   = 7

const weatherSources = [
  { name: 'Open-Meteo', desc: 'Daily forecast including temperature, rain, wind, UV', url: 'https://open-meteo.com', icon: '🌤️' },
  { name: 'Nominatim', desc: 'Converts coordinates to readable location names', url: 'https://nominatim.openstreetmap.org', icon: '🗺️' },
  { name: 'W3C Geolocation', desc: 'Detects your current location via browser', url: 'https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API', icon: '📡' },
]

const weatherEntries = computed(() => {
  if (!weatherData.value) return []
  const d = weatherData.value.daily
  return d.time.map((date, i) => ({
    date,
    weathercode: d.weathercode[i],
    tempMax:     d.temperature_2m_max[i],
    tempMin:     d.temperature_2m_min[i],
    precip:      d.precipitation_sum[i] ?? 0,
    windspeed:   d.windspeed_10m_max?.[i] ?? '—',
    uvindex:     d.uv_index_max?.[i] ?? '—',
  }))
})

const selectedWeatherEntry = computed(() => weatherEntries.value[selectedWeatherDateIndex.value] ?? null)
const mapWeatherSummary = computed(() => ({
  date: activeWeatherDate.value || todayISO,
  dateLabel: activeWeatherDate.value ? formatWeatherFullDate(activeWeatherDate.value) : 'Today',
  location: userLocationName.value || 'Selected Location'
}))

// Geocoding
async function reverseGeocode(lat, lon) {
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1`, { headers: { 'Accept-Language': 'en' } })
    const data = await res.json()
    const addr = data.address
    return addr.city || addr.town || addr.village || addr.suburb || addr.district || addr.county || 'Selected Location'
  } catch { return `${lat.toFixed(2)}, ${lon.toFixed(2)}` }
}

// Fetch Weather from Open-Meteo (forecast only)
async function fetchWeather(lat = null, lon = null) {
  weatherLoading.value = true
  try {
    if (lat === null || lon === null) {
      try {
        const pos = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 6000 }))
        lat = pos.coords.latitude
        lon = pos.coords.longitude
        weatherLat.value = lat
        weatherLon.value = lon
        userLocationName.value = await reverseGeocode(lat, lon)
      } catch {
        lat = weatherLat.value
        lon = weatherLon.value
        userLocationName.value = 'Udham Singh Nagar'
      }
    }
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max&timezone=auto&forecast_days=${WEATHER_FORECAST_DAYS}`
    const res = await fetch(url)
    weatherData.value = await res.json()
    weatherFetchedAt.value = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
    syncSelectedWeatherDate()
  } catch (e) {
    console.error('Weather fetch error:', e)
    weatherData.value = null
  } finally { weatherLoading.value = false }
}

// Fetch historical weather from Open-Meteo archive for a past date + 7 day forecast
async function fetchHistoricalWeather(lat, lon, historyDate) {
  weatherLoading.value = true
  try {
    // Format dates for API
    const startDate = historyDate // e.g., "2026-04-15"
    const endDate = historyDate   // Single day for historical
    
    // Fetch historical data for the selected date
    const historyUrl = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}&start_date=${startDate}&end_date=${endDate}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max&timezone=auto`
    const historyRes = await fetch(historyUrl)
    const historyData = await historyRes.json()
    
    // Fetch 7-day forecast from the day after the selected date
    const nextDay = new Date(historyDate)
    nextDay.setDate(nextDay.getDate() + 1)
    const forecastStart = nextDay.toISOString().split('T')[0]
    const forecastUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max&timezone=auto&forecast_days=7`
    const forecastRes = await fetch(forecastUrl)
    const forecastData = await forecastRes.json()
    
    // Combine historical + forecast data
    if (historyData.daily && forecastData.daily) {
      // Combine the arrays
      const combinedTime = [...historyData.daily.time, ...forecastData.daily.time]
      const combinedWeathercode = [...historyData.daily.weathercode, ...forecastData.daily.weathercode]
      const combinedTempMax = [...historyData.daily.temperature_2m_max, ...forecastData.daily.temperature_2m_max]
      const combinedTempMin = [...historyData.daily.temperature_2m_min, ...forecastData.daily.temperature_2m_min]
      const combinedPrecip = [...(historyData.daily.precipitation_sum || []), ...(forecastData.daily.precipitation_sum || [])]
      const combinedWindspeed = [...(historyData.daily.windspeed_10m_max || []), ...(forecastData.daily.windspeed_10m_max || [])]
      
      // UV index only available in forecast, add null for historical
      const combinedUvIndex = [...Array(historyData.daily.time.length).fill(null), ...(forecastData.daily.uv_index_max || [])]
      
      weatherData.value = {
        daily: {
          time: combinedTime,
          weathercode: combinedWeathercode,
          temperature_2m_max: combinedTempMax,
          temperature_2m_min: combinedTempMin,
          precipitation_sum: combinedPrecip,
          windspeed_10m_max: combinedWindspeed,
          uv_index_max: combinedUvIndex
        }
      }
      weatherFetchedAt.value = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
      syncSelectedWeatherDate()
    }
  } catch (e) {
    console.error('Historical weather fetch error:', e)
    weatherData.value = null
  } finally { weatherLoading.value = false }
}

async function relocateWeather() {
  weatherData.value = null
  userLocationName.value = 'Locating…'
  await fetchWeather()
}

async function toggleWeather() {
  calendarOpen.value = false
  weatherOpen.value = !weatherOpen.value
  if (!weatherOpen.value) return
  if (!weatherData.value) {
    await fetchWeather()
    return
  }
  syncSelectedWeatherDate()
}

// FIX 1: Handle location selected from map.
// Only update coordinates/name and prefetch data in the background.
// Do NOT force the weather panel open — the user controls that via the header button.
async function handleLocationSelected({ lat, lon }) {
  weatherLat.value = lat
  weatherLon.value = lon
  userLocationName.value = await reverseGeocode(lat, lon)
  await fetchWeather(lat, lon)
}

// Weather helpers
function getWeatherEmoji(code) {
  if (code === 0) return '☀️'
  if (code <= 3) return '⛅'
  if (code <= 48) return '🌫️'
  if (code <= 55) return '🌧️'
  if (code <= 65) return '🌦️'
  if (code <= 75) return '❄️'
  if (code <= 82) return '🌦️'
  if (code <= 99) return '⛈️'
  return '🌤️'
}

function getWeatherDesc(code) {
  const map = { 0:'Clear Sky',1:'Mainly Clear',2:'Partly Cloudy',3:'Overcast',45:'Foggy',48:'Depositing Rime Fog',51:'Light Drizzle',53:'Moderate Drizzle',55:'Dense Drizzle',61:'Slight Rain',63:'Moderate Rain',65:'Heavy Rain',71:'Slight Snowfall',73:'Moderate Snowfall',75:'Heavy Snowfall',95:'Thunderstorm',96:'Thunderstorm + Hail',99:'Thunderstorm + Hail' }
  return map[code] || 'Cloudy'
}

function formatWeatherDay(dateStr) { return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short' }) }
function formatLocalISO(date) {
  return date.toLocaleDateString('en-CA')
}
function formatWeatherFullDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const targetDate = new Date(d)
  targetDate.setHours(0, 0, 0, 0)
  
  if (targetDate.toDateString() === today.toDateString()) return 'Today'
  
  const diff = Math.round((targetDate - today) / 86400000)
  
  if (diff < 0) {
    // Past date - show as "X days ago" or the date
    const absDiff = Math.abs(diff)
    if (absDiff === 1) return 'Yesterday'
    if (absDiff <= 7) return `${absDiff} days ago`
    return d.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })
  }
  
  if (diff === 1) return 'Tomorrow'
  return d.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })
}

function selectWeatherEntry(date, index) {
  activeWeatherDate.value = date
  selectedWeatherDateIndex.value = index
}

// Sentinel Calendar helpers
const today = ref(new Date())
const forecastDateSet = computed(() => new Set(weatherEntries.value.map(entry => entry.date)))
const windowEndDate = computed(() => {
  if (weatherEntries.value.length === 0) return new Date(today.value)
  return new Date(`${weatherEntries.value[weatherEntries.value.length - 1].date}T00:00:00`)
})
const windowStartDate = computed(() => { const d = new Date(today.value); d.setDate(d.getDate() - 59); return d })
const windowEnd = computed(() => formatLocalISO(windowEndDate.value))
const windowStart = computed(() => formatLocalISO(windowStartDate.value))

const availableDateSet = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => map.set(d.date, { layers: Array.isArray(d.layers) ? d.layers : [], slot: d.slot }))
  return map
})

const dateToSlotMap = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => map.set(d.date, d.slot))
  return map
})

const selectedDateLayers = computed(() => availableDateSet.value.get(selectedCalendarDate.value)?.layers ?? [])
const selectedDateHasForecast = computed(() => forecastDateSet.value.has(selectedCalendarDate.value))
const selectedDateIsPast = computed(() => {
  if (!selectedCalendarDate.value) return false
  const selected = new Date(selectedCalendarDate.value + 'T00:00:00')
  const todayDate = new Date(today.value)
  todayDate.setHours(0, 0, 0, 0)
  return selected < todayDate
})

const calMonths = computed(() => {
  const months = []
  if (!windowStartDate.value || !windowEndDate.value) return months
  const cursor = new Date(windowStartDate.value)
  const end = new Date(windowEndDate.value)
  const todayISO = today.value.toLocaleDateString('en-CA')
  let cur = null
  while (cursor <= end) {
    const y = cursor.getFullYear(), m = cursor.getMonth()
    const mk = `${y}-${m}`
    if (!cur || cur.monthNum !== m || cur.year !== y) {
      if (cur) months.push(cur)
      cur = { key: mk, label: new Date(y, m, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }), year: y, monthNum: m, startOffset: new Date(y, m, 1).getDay(), days: [] }
    }
    const iso = cursor.toLocaleDateString('en-CA')
    const dateInfo = availableDateSet.value.get(iso)
    const hasForecast = forecastDateSet.value.has(iso)
    const isPast = cursor < today.value
    cur.days.push({
      iso,
      day: cursor.getDate(),
      hasData: !!dateInfo,
      hasForecast,
      isSelectable: !!dateInfo || hasForecast || isPast,
      layers: dateInfo?.layers ?? [],
      isToday: iso === todayISO,
      isFuture: cursor > today.value,
      isPast
    })
    cursor.setDate(cursor.getDate() + 1)
  }
  if (cur) months.push(cur)
  return months
})

function selectCalendarDate(iso) {
  selectedCalendarDate.value = iso
  currentslot.value = dateToSlotMap.value.get(iso) || 'today'
  calendarOpen.value = false
  
  // Check if selected date is in the past
  const selectedDate = new Date(iso + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const isPastDate = selectedDate < today
  
  if (isPastDate) {
    // Fetch historical weather for past date + 7 day forecast
    fetchHistoricalWeather(weatherLat.value, weatherLon.value, iso)
    activeWeatherDate.value = iso
  } else {
    // For today/future, use forecast
    activeWeatherDate.value = forecastDateSet.value.has(iso) ? iso : todayISO
    syncSelectedWeatherDate()
  }

  if (forecastDateSet.value.has(iso) || isPastDate) {
    weatherOpen.value = true
  }
}

function syncSelectedWeatherDate() {
  if (weatherEntries.value.length === 0) {
    selectedWeatherDateIndex.value = 0
    return
  }

  const targetDate = activeWeatherDate.value && forecastDateSet.value.has(activeWeatherDate.value)
    ? activeWeatherDate.value
    : todayISO

  const index = weatherEntries.value.findIndex(entry => entry.date === targetDate)
  selectedWeatherDateIndex.value = index === -1 ? 0 : index
  activeWeatherDate.value = weatherEntries.value[selectedWeatherDateIndex.value]?.date ?? todayISO
}

function getCalendarDayTitle(day) {
  if (day.hasData) return `Data available - ${day.layers.join(', ')}`
  if (day.hasForecast) return 'Weather forecast available'
  if (day.isFuture) return 'Future date'
  return 'No data'
}

function formatDisplayDate(iso) {
  if (!iso) return ''
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function clearCalendarSelection() {
  selectedCalendarDate.value = null
  currentslot.value = 'today'
  activeWeatherDate.value = todayISO
  syncSelectedWeatherDate()
}

// On mount: fetch history and weather
onMounted(async () => {
  try {
    const res = await fetch(`${API_BASE}/api/history`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    availableDates.value = (data.slots || []).map(s => ({ date: s.date, slot: s.slot, layers: Object.keys(s.obs_means || {}).filter(k => s.obs_means[k] !== null) }))
    if (availableDates.value.length > 0) {
      const latest = availableDates.value[0]
      selectedCalendarDate.value = latest.date
      currentslot.value = latest.slot || 'today'
    }
  } catch (e) { console.error('Initial history fetch error:', e); availableDates.value = [] }
  await fetchWeather()
})

watch(weatherOpen, async (open) => {
  if (!open) return
  if (!weatherData.value) {
    await fetchWeather()
    return
  }
  syncSelectedWeatherDate()
})

watch(calendarOpen, async (open) => {
  if (!open) return
  weatherOpen.value = false
  calLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/history`)
    const data = await res.json()
    availableDates.value = (data.slots || []).map(s => ({ date: s.date, slot: s.slot, layers: Object.keys(s.obs_means || {}).filter(k => s.obs_means[k] !== null) }))
  } catch { availableDates.value = [] }
  finally { calLoading.value = false }
})

// Layer definitions
const layerDefs = [
  { key:'savi', name:'Soil Adjusted Vegetation Index', maxLabel:'1.0', midLabel:'0.0', minLabel:'-1.0', icon:'🌿' },
  { key:'kc', name:'Crop Coefficient (FAO-56)', maxLabel:'1.15', midLabel:'0.7', minLabel:'0.30', icon:'💧' },
  { key:'cwr', name:'Crop Water Requirement (mm)', maxLabel:'10 mm', midLabel:'5 mm', minLabel:'0 mm', icon:'💦' },
  { key:'iwr', name:'Irrigation Water Requirement (mm)', maxLabel:'10 mm', midLabel:'5 mm', minLabel:'0 mm', icon:'🚿' },
]

const legendBreakpoints = { savi: [-1,-0.8,-0.6,-0.4,-0.2,0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1], kc: [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5], cwr: [0,1,2,3,4,4.5,5,5.5,6,6.5,7,7.5,8,8.5,9,9.5,10], iwr: [0,1,2,3,4,5,6,7,8,9,10] }
const legendRanges = { savi:{min:-1,max:1}, kc:{min:0,max:1.5}, cwr:{min:0,max:10}, iwr:{min:0,max:10} }

function showLegendValue(e, layer) {
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  const b = legendBreakpoints[layer]
  const idx = Math.min(b.length - 2, Math.max(0, Math.floor(pct * (b.length - 1))))
  legendValue.value = `${layer.toUpperCase()}: ${b[idx]} – ${b[idx + 1] ?? b[idx]}`
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
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --brand-primary: #2f855a;
  --brand-primary-10: rgba(47, 133, 90, 0.1);
  --brand-primary-16: rgba(47, 133, 90, 0.16);
  --brand-primary-24: rgba(47, 133, 90, 0.24);
  --brand-primary-32: rgba(47, 133, 90, 0.32);
  --brand-primary-45: rgba(47, 133, 90, 0.45);
  --brand-accent: #2b6cb0;
  --brand-accent-soft: #7fb3d5;
  --brand-surface: #102235;
  --brand-surface-2: #142b40;
  --brand-surface-3: #1b354d;
  --brand-border: rgba(179, 205, 224, 0.18);
  --brand-text: #edf4f8;
  --brand-text-soft: #b9cada;
  --brand-text-muted: #88a0b8;
  --brand-warning: #d69e2e;
}

.dashboard-shell {
  font-family: 'Space Grotesk', sans-serif;
  background:
    radial-gradient(circle at top left, rgba(43, 108, 176, 0.16), transparent 28%),
    linear-gradient(180deg, #0b1827 0%, #102133 46%, #0d1a29 100%);
  color: var(--brand-text);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.dash-header { height: 64px; background: rgba(10, 24, 38, 0.94); border-bottom: 1px solid var(--brand-border); display: flex; align-items: center; padding: 0 16px; gap: 12px; flex-shrink: 0; z-index: 100; backdrop-filter: blur(14px); }
.dash-logo { height: 38px; object-fit: contain; flex-shrink: 0; }
.header-divider { width:1px; height:32px; background:var(--brand-border); flex-shrink:0; }
.header-titles { position:absolute; left:50%; transform:translateX(-50%); text-align:center; }
.header-title { font-size:.82rem; color:#93c5aa; font-family:'JetBrains Mono',monospace; font-weight:600; text-transform:uppercase; letter-spacing:.08em; white-space:nowrap; margin:0; }
.header-right { margin-left:auto; display:flex; align-items:center; gap:12px; flex-shrink:0; }
.trend-btn { display:flex; align-items:center; gap:8px; padding:8px 14px; border-radius:50px; border:1px solid var(--brand-border); background:rgba(255,255,255,.06); color:var(--brand-text-soft); font-size:.75rem; font-family:'JetBrains Mono',monospace; font-weight:600; cursor:pointer; transition:all .2s; white-space:nowrap; }
.trend-btn:hover { border-color:var(--brand-primary-45); color:#d8e7f1; background:rgba(255,255,255,.09); }
.trend-btn.active { border-color:var(--brand-primary); color:#dff3e7; background:var(--brand-primary-16); box-shadow:0 10px 24px rgba(47, 133, 90, 0.12); }
.calendar-btn { display:flex; align-items:center; gap:8px; padding:6px 14px; border-radius:50px; border:1px solid rgba(127, 179, 213, 0.28); background:rgba(127, 179, 213, 0.12); color:#d3e5f2; font-size:.75rem; font-family:'JetBrains Mono',monospace; font-weight:600; cursor:pointer; transition:all .2s; white-space:nowrap; }
.calendar-btn:hover, .calendar-btn.active { background:rgba(127, 179, 213, 0.18); border-color:rgba(127, 179, 213, 0.46); }
.icon-btn { width:38px; height:38px; border-radius:10px; display:flex; align-items:center; justify-content:center; background:transparent; border:none; cursor:pointer; color:var(--brand-text-muted); transition:all .2s; flex-shrink:0; }
.icon-btn:hover { color:#fff; background:rgba(255,255,255,.08); }

.home-btn 
{ padding:8px 16px;
   border-radius:10px; 
   font-size:.9rem;
    font-family:'JetBrains Mono',monospace;
    font-weight:500; 
    color:var(--brand-text-muted); 
   background:transparent; 
   border:1px solid transparent;
    cursor:pointer; 
    white-space:nowrap; }
.home-btn:hover { color:#cbe6d7; border-color:var(--brand-primary-32); background:var(--brand-primary-10); }
.dash-body { flex:1; display:flex; overflow:hidden; min-height:0; }
.sidebar-panel { background:linear-gradient(180deg, rgba(10, 24, 38, 0.98), rgba(18, 39, 58, 0.96)); border-right:1px solid var(--brand-border); overflow-y:auto; transition:width .3s; flex-shrink:0; z-index:40; }
.sidebar-panel.open { width:300px; }
.sidebar-panel.closed { width:0; }
.sidebar-content { padding:20px; min-width:280px; }
.sidebar-section-label { font-size:.75rem; color:var(--brand-text-muted); font-family:'JetBrains Mono',monospace; font-weight:600; text-transform:uppercase; letter-spacing:.12em; margin:0 0 16px; padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,.06); }
.layer-card { display:flex; align-items:center; justify-content:space-between; padding:12px 14px; border-radius:14px; border:1px solid rgba(185, 202, 218, 0.12); background:rgba(255,255,255,.04); cursor:pointer; margin-bottom:10px; box-shadow: inset 0 1px 0 rgba(255,255,255,.02); }
.layer-card.active { border-color:var(--brand-primary-32); background:linear-gradient(135deg, rgba(47, 133, 90, 0.14), rgba(127, 179, 213, 0.08)); }
.layer-left { display:flex; align-items:center; gap:12px; }
.layer-ico { font-size:1.3rem; }
.layer-key { font-size:.9rem; font-weight:700; margin:0; }
.layer-name { font-size:.72rem; color:var(--brand-text-muted); margin:2px 0 0; line-height:1.35; }
.toggle-track { width:44px; height:22px; border-radius:12px; background:#415a71; position:relative; flex-shrink:0; }
.toggle-track.on { background:var(--brand-primary); }
.toggle-thumb { position:absolute; top:2px; left:2px; width:18px; height:18px; border-radius:50%; background:white; transition:all .2s; }
.toggle-thumb.on { left:24px; }
.legend-strip { padding:10px 12px 14px; margin:0 10px 10px; background:rgba(8, 20, 32, 0.44); border:1px solid rgba(185, 202, 218, 0.08); border-radius:12px; }
.legend-labels-horizontal { display:flex; justify-content:space-between; margin-bottom:4px; }
.legend-labels-horizontal span { font-size:.65rem; color:var(--brand-text-muted); font-family:'JetBrains Mono',monospace; }
.legend-bar-horizontal { width:100%; height:28px; border-radius:6px; cursor:pointer; }
.legend-grad-savi { background:linear-gradient(to right,#8B0000,#FF4500,#FFD700,#32CD32,#006400); }
.legend-grad-kc { background:linear-gradient(to right,#FFD700,#90EE90,#32CD32,#8B4513); }
.legend-grad-cwr { background:linear-gradient(to right,#FF4444,#FFA500,#FFFF00,#0000CD,#4B0082); }
.legend-grad-iwr { background:linear-gradient(to right,#E0F7FA,#4DD0E1,#00BCD4,#00695C,#1A237E); }
.legend-tooltip { position:fixed; background:rgba(8, 18, 30, 0.96); color:var(--brand-text); font-size:.75rem; padding:6px 14px; border-radius:8px; pointer-events:none; z-index:9999; font-family:'JetBrains Mono',monospace; white-space:nowrap; border:1px solid var(--brand-border); }
.ctrl-card { margin-top:16px; padding:14px 16px; border-radius:14px; border:1px solid rgba(185, 202, 218, 0.12); background:rgba(255,255,255,.04); }
.ctrl-row { display:flex; justify-content:space-between; margin-bottom:10px; font-size:.85rem; color:var(--brand-text-muted); }
.ctrl-val { color:#cfe9da; font-weight:700; }
.range-slider { width:100%; height:5px; border-radius:3px; appearance:none; background:#415a71; }
.range-slider::-webkit-slider-thumb { appearance:none; width:18px; height:18px; border-radius:50%; background:var(--brand-primary); cursor:pointer; border:2px solid #f7fbfd; }
.map-area { flex:2; position:relative; overflow:hidden; min-width:0; min-height:0; }

/* Overlay styles */
.calendar-float-panel {
  position: fixed;
  top: 60px;
  right: 40px;
  z-index: 5000;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  pointer-events: none;
}
.calendar-float-panel .cal-panel {
  pointer-events: auto;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 24px;
  width: min(420px, 96vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: calSlideDown .2s;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
}
@keyframes calSlideDown { from{opacity:0;transform:translateY(-18px)} to{opacity:1;transform:translateY(0)} }
@keyframes slideInWeatherRight { from{opacity:0;transform:translateX(30px)} to{opacity:1;transform:translateX(0)} }
@keyframes calSpin { to{transform:rotate(360deg)} }
.cal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: flex-end;
  justify-content: flex-start;
  padding: 84px 24px 24px 324px;
  background: linear-gradient(180deg, rgba(4, 10, 18, 0.08), rgba(4, 10, 18, 0.26));
}
.cal-header { padding:18px 22px 14px; border-bottom:1px solid rgba(0,0,0,0.08); background:linear-gradient(180deg, rgba(0,0,0,0.02), rgba(0,0,0,0)); }
.cal-title-row { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.cal-title { font-size:1rem; font-weight:700; flex:1; color:#1a202c; }
.cal-close { width:30px; height:30px; background:rgba(0,0,0,0.04); border:1px solid rgba(0,0,0,0.1); border-radius:50%; color:#4a5568; cursor:pointer; display:flex; align-items:center; justify-content:center; }
.cal-close:hover { background:rgba(18, 209, 184, 0.14); color:#ddfaf3; border-color:rgba(18, 209, 184, 0.24); }

/* ─── WEATHER PANEL WRAPPER (Side Panel) ─── */
.weather-panel-wrapper {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  pointer-events: none;
}
.cal-subtitle { font-size:.76rem; color:#4a5568; margin:0; }
.cal-scroll { overflow-y:auto; flex:1; padding:18px 22px 20px; display:flex; flex-direction:column; gap:24px; }
.cal-month-label { font-size:.92rem; font-weight:700; color:#1a202c; margin:0 0 10px; }
.cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
.cal-dow { font-size:.66rem; color:#4a5568; text-align:center; padding:4px 0; letter-spacing:.04em; }
.cal-day { height:46px; border-radius:12px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#f7fafc; border:1px solid rgba(0, 0, 0, 0.08); transition:all .18s ease; }
.cal-day-num { font-size:.82rem; color:#2d3748; }
.cal-day-dot { width:7px; height:7px; border-radius:50%; background:#2f855a; margin-top:4px; box-shadow:0 0 0 4px rgba(47, 133, 90, 0.12); }
.cal-day-dot-forecast { background:#3182ce; box-shadow:none; }
.cal-day-has-data { background:linear-gradient(180deg, #c6f6d5 0%, #9ae6b4 100%); border-color:rgba(47, 133, 90, 0.34); box-shadow:inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(47, 133, 90, 0.05); }
.cal-day-has-data .cal-day-num { color:#1a202c; font-weight:700; }
.cal-day-has-forecast { background:rgba(66, 153, 225, 0.12); border-color:rgba(49, 130, 206, 0.24); }
.cal-day-has-forecast .cal-day-num { color:#1a365d; }
.cal-day-clickable { cursor:pointer; }
.cal-day-clickable:hover { transform:translateY(-1px); border-color:rgba(47, 133, 90, 0.4); }
.cal-day-selected { background:linear-gradient(180deg, #48bb78 0%, #38a169 100%)!important; border-color:#2f855a!important; box-shadow:0 0 0 1px rgba(47, 133, 90, 0.3), 0 10px 24px rgba(0, 0, 0, 0.15); }
.cal-day-selected .cal-day-num { color:#ffffff; font-weight:800; }
.cal-day-today { border-color:rgba(237, 137, 54, 0.8); }
.cal-day-empty { background:transparent; border-color:transparent; }
.cal-day-future { opacity:.5; cursor:not-allowed; }
.cal-day-past { opacity:.75; }
.cal-loading { display:flex; justify-content:center; gap:14px; padding:48px; color:#4a5568; }
.cal-spinner { width:22px; height:22px; border:2px solid rgba(47, 133, 90, 0.18); border-top-color:var(--brand-primary); border-radius:50%; animation:calSpin .8s linear infinite; }
.cal-footer { padding:12px 22px; border-top:1px solid rgba(0,0,0,0.08); display:flex; justify-content:space-between; gap:12px; background:rgba(247, 250, 252, 0.8); }
.cal-sel-info { display:flex; gap:8px; font-size:.8rem; color:#2d3748; align-items:center; flex-wrap:wrap; }
.cal-sel-badge { padding:3px 8px; border-radius:999px; background:rgba(47, 133, 90, 0.14); border:1px solid rgba(47, 133, 90, 0.24); color:#22543d; font-size:.68rem; }
.cal-sel-badge-forecast { background:rgba(49, 130, 206, 0.14); border-color:rgba(49, 130, 206, 0.24); color:#1a365d; }
.cal-sel-badge-past { background:rgba(128, 90, 213, 0.14); border-color:rgba(128, 90, 213, 0.24); color:#44337a; }
.cal-clear-btn { padding:7px 14px; border-radius:10px; border:1px solid rgba(0, 0, 0, 0.12); background:rgba(255,255,255,0.8); color:#2d3748; cursor:pointer; }
.cal-clear-btn:hover { background:rgba(255,255,255,.08); }
.weather-panel { background:linear-gradient(180deg, #102235 0%, #132a40 100%); border:1px solid var(--brand-border); border-radius:24px; width:min(520px,96vw); max-height:88vh; display:flex; flex-direction:column; overflow:hidden; animation:slideInWeatherRight .28s ease; box-shadow:0 28px 70px rgba(4, 10, 18, 0.46); pointer-events: all; margin-right: 20px; margin-bottom: 20px; }
.weather-header { padding:18px 20px 14px; border-bottom:1px solid rgba(255,255,255,.06); }
.weather-title-row { display:flex; align-items:center; gap:14px; }
.weather-main-icon { font-size:2rem; }
.weather-title-meta { flex:1; }
/* FIX 3: .weather-title was missing a flex layout so the date label rendered
   inline next to the temperature. Display as column so temp sits above label. */
.weather-title { font-size:1rem; font-weight:700; color:#fff; display:flex; flex-direction:column; gap:2px; }
.weather-today-label { font-size:.72rem; font-weight:400; color:var(--brand-text-muted); }
.weather-loc-row { display:flex; align-items:center; gap:8px; font-size:.75rem; color:var(--brand-text-muted); flex-wrap:wrap; }
.weather-locate-btn { display:flex; align-items:center; gap:4px; padding:4px 10px; border-radius:20px; border:1px solid rgba(47, 133, 90, 0.26); background:rgba(47, 133, 90, 0.12); color:#dcefe4; font-size:.65rem; cursor:pointer; }
.weather-content { overflow-y:auto; flex:1; padding:18px 20px; }
.weather-today-card { background:linear-gradient(135deg, rgba(17, 78, 105, 0.34), rgba(47, 133, 90, 0.18)); border:1px solid rgba(127, 179, 213, 0.24); border-radius:18px; padding:16px; display:flex; justify-content:space-between; margin-bottom:20px; box-shadow: inset 0 1px 0 rgba(255,255,255,.03); }
.today-left { display:flex; flex-direction:column; gap:4px; }
.today-temp { font-size:2.2rem; font-weight:700; color:#d8f0e1; line-height:1; }
.today-desc { font-size:.9rem; color:#edf4f8; }
.today-date-label { font-size:.72rem; color:var(--brand-text-soft); }
.today-meta { display:flex; flex-direction:column; gap:6px; font-size:.74rem; color:var(--brand-text-soft); text-align:right; }
.forecast-label { font-size:.74rem; color:var(--brand-text-soft); text-transform:uppercase; margin:0 0 10px; letter-spacing:.06em; }
.forecast-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:6px; margin-bottom:20px; }
.forecast-day-card { background:rgba(255,255,255,.04); border:1px solid rgba(185, 202, 218, 0.08); border-radius:14px; padding:10px 8px; display:flex; flex-direction:column; align-items:center; gap:5px; cursor:pointer; transition:all .18s ease; }
.forecast-day-card:hover { transform:translateY(-1px); border-color:rgba(127, 179, 213, 0.2); }
.fc-card-selected { background:rgba(47, 133, 90, 0.14)!important; border-color:rgba(47, 133, 90, 0.28)!important; }
.fc-day { font-size:.62rem; color:var(--brand-text-muted); }
.fc-icon { font-size:1.1rem; }
.fc-temp { font-size:.82rem; font-weight:700; color:#fff; }
.fc-precip { font-size:.6rem; color:#8fd3ff; }
.wth-sources-section { margin-top:20px; padding-top:12px; border-top:1px solid rgba(255,255,255,.07); }
.wth-sources-inline { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:0; }
.wth-source-inline-link { font-size:.7rem; color:rgba(190, 205, 219, 0.72); text-decoration:none; transition:color .18s ease; }
.wth-source-inline-link:hover { color:#dce9f2; text-decoration:underline; }
.wth-source-sep { display:inline-block; margin:0 8px; color:rgba(190, 205, 219, 0.48); }
.wth-update-note { font-size:.64rem; color:var(--brand-text-muted); text-align:right; margin:8px 0 0; }
.weather-error { padding:40px; text-align:center; }
.retry-btn { margin-top:12px; padding:6px 16px; border-radius:10px; border:1px solid var(--brand-primary-32); background:var(--brand-primary-10); color:#dcefe4; cursor:pointer; }
.weather-card { display:flex; align-items:center; gap:10px; padding:8px 14px; border-radius:50px; background:rgba(255,255,255,.06); border:1px solid var(--brand-border); cursor:pointer; transition:all .25s; }
.weather-card:hover { background:rgba(255,255,255,.1); border-color:rgba(127, 179, 213, 0.22); }
.wc-icon { font-size:1.2rem; line-height:1; }
.wc-center { display:flex; flex-direction:column; line-height:1.2; }
.wc-location { font-size:.7rem; color:var(--brand-text-soft); }
.wc-date { font-size:.65rem; color:#dcefe4; font-weight:600; }
.wc-temp { font-size:.95rem; font-weight:700; color:#f7fbfd; }
@media (max-width:768px) {
  .header-titles { display:none; }
  .sidebar-panel.open { width:260px; }
  .forecast-grid { grid-template-columns:repeat(4,1fr); }
  .header-right { gap:8px; }
  .trend-btn { padding:8px 12px; }
  .cal-backdrop { padding:76px 16px 16px 16px; align-items:flex-end; justify-content:center; }
  .calendar-float-panel { top:76px; right:16px; }
  .weather-panel-wrapper { align-items: flex-end; justify-content: flex-end; padding: 76px 16px 16px; }
  .weather-panel { width: calc(100% - 32px); max-width: 420px; margin: 0; margin-bottom: 16px; }
}
@media (max-width:480px) {
  .calendar-btn span:last-child, .trend-btn span:last-child { display:none; }
  .forecast-grid { grid-template-columns:repeat(2,1fr); }
  .trend-btn { padding:8px 10px; }
  .cal-backdrop { padding:72px 10px 10px; }
  .calendar-float-panel { top:72px; right:10px; left:10px; justify-content:center; }
  .weather-panel-wrapper { padding: 72px 10px 10px; }
  .weather-panel { width: calc(100% - 20px); max-width: 100%; margin: 0; margin-bottom: 10px; }
}
</style>
