<!-- MapView.vue -->

<template>
  <div class="map-container">
    <div id="map" ref="mapEl" class="map"></div>

    <!-- Map Style Dropdown -->
    <div class="map-style-dropdown">
      <button class="dropdown-toggle" @click="toggleStyleDropdown">
        <span class="style-icon">{{ currentStyle.icon }}</span>
        <span class="style-name">{{ currentMapStyle }}</span>
        <span class="dropdown-arrow">▼</span>
      </button>

      <div class="dropdown-menu" v-show="isStyleDropdownOpen">
        <button v-for="style in mapStyles" :key="style.name" class="dropdown-item"
          :class="{ active: currentMapStyle === style.name }" @click="selectMapStyle(style.name)">
          <span class="style-icon">{{ style.icon }}</span>
          <span class="style-name">{{ style.name }}</span>
          <span class="check-mark" v-if="currentMapStyle === style.name">✓</span>
        </button>
      </div>
    </div>

    <!-- Kc Forecast Window Selector (shown only when Kc layer is active) -->
    <div class="forecast-window-bar" v-if="props.layers.kc">
    </div>

    <!-- Info Panel (shown on map click / My Location) -->
    <div class="info-panel" v-if="pointData" :class="{ 'light': !isDarkMode }">
      <h3>📍 Selected Point</h3>

      <!-- Sentinel acquisition date + coordinates -->
      <div class="meta-row">
        <span class="meta-icon">🛰️</span>
        <span class="meta-label">Date</span>
        <span class="meta-val sentinel-date">
          {{ slotToDateMap[props.slot] || pointData.acquisition_date }}
        </span>
      </div>
      <div class="meta-row">
        <span class="meta-icon">🌐</span>
        <span class="meta-label">Location</span>
        <span class="meta-val coord-val">
          {{ pointData.lat?.toFixed(5) }}°N,&nbsp;{{ pointData.lon?.toFixed(5) }}°E
        </span>
      </div>
      <div class="meta-row weather-row" @click="weatherVisible = true">
        <span class="meta-icon">🌤️</span>
        <span class="meta-label">Weather</span>
        <span class="meta-val weather-link">
          <span class="weather-date-line">{{ props.weatherSummary?.dateLabel || 'Today' }}</span>
          <span class="weather-location-line">{{ props.weatherSummary?.location || 'Selected Location' }}</span>
        </span>
      </div>

      <!-- No active layer hint -->
      <p v-if="activeLayers.length === 0" class="nodata-hint">
        Enable a layer in the sidebar to see values.
      </p>

      <!-- Per-layer value cards -->
      <div v-for="layer in activeLayers" :key="layer.name" class="value-section">
        <h4>{{ layer.displayName }}</h4>

        <div class="forecast-grid">
          <!-- Observed (satellite pixel / current) -->
          <div class="fc-item" :class="{ 'fc-item--active': selectedWindow === null && layer.name === 'kc' }"
               @click="layer.name === 'kc' && selectForecastWindow(null)">
            <span class="fc-label observed-label">Today</span>
            <span v-if="pointData.values?.[layer.name] != null"
                  class="value" :style="getValueStyle(layer.name, pointData.values[layer.name])">
              {{ format(pointData.values[layer.name]) }}
              <em class="unit">{{ layerUnit(layer.name) }}</em>
            </span>
            <span v-else class="nodata-chip">No data</span>
          </div>

          <!-- 5/10/15-day forecast — Kc and SAVI (derived) -->
          <template v-if="forecastData && (layer.name === 'kc' || layer.name === 'savi')">
            <div class="fc-item" v-for="w in [['5day','5D'], ['10day','10D'], ['15day','15D']]" :key="w[0]"
                 :class="{ 'fc-item--active': selectedWindow === w[0] && layer.name === 'kc' }"
                 @click="layer.name === 'kc' && selectForecastWindow(w[0])">
              <span class="fc-label">{{ w[1] }} avg</span>
              <span v-if="layer.name === 'kc' && forecastData?.kc?.[w[0]] != null"
                    class="value"
                    :style="getValueStyle('kc', forecastData.kc[w[0]])">
                {{ format(forecastData.kc[w[0]]) }}
              </span>
              <span v-else-if="layer.name === 'savi' && forecastData?.kc?.[w[0]] != null"
                    class="value"
                    :style="getValueStyle('savi', calculateSaviFromKc(forecastData.kc[w[0]]))">
                {{ format(calculateSaviFromKc(forecastData.kc[w[0]])) }}
              </span>
              <span v-else class="nodata-chip">—</span>
            </div>
          </template>

          <!-- 5/10/15-day forecast — CWR / IWR -->
          <template v-if="forecastData && (layer.name === 'cwr' || layer.name === 'iwr')">
            <div class="fc-item" v-for="w in [['5day','5D'], ['10day','10D'], ['15day','15D']]" :key="w[0]">
              <span class="fc-label">{{ w[1] }} avg</span>
              <span v-if="forecastData?.[layer.name]?.[w[0]] != null"
                    class="value"
                    :style="getValueStyle(layer.name, forecastData[layer.name][w[0]])">
                {{ format(forecastData[layer.name][w[0]]) }}
                <em class="unit">{{ layer.name === 'cwr' || layer.name === 'iwr' ? 'mm' : '' }}</em>
              </span>
              <span v-else class="nodata-chip">—</span>
            </div>
          </template>
        </div>
      </div>

      <!-- Forecast loading indicator -->
      <p v-if="isForecastLoading" class="loading-hint">⏳ Loading forecast…</p>
    </div>

    <!-- Location Button -->
    <button
      class="location-btn"
      @click="getCurrentLocation"
      :class="{ loading: isLocating }"
      :disabled="isLocating"
      :title="isLocating ? 'Detecting your location' : 'Use current location'"
      :aria-label="isLocating ? 'Detecting your location' : 'Use current location'"
    >
      <span class="location-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1">
          <circle cx="12" cy="12" r="3.5" />
          <path stroke-linecap="round" d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
        </svg>
      </span>
      <span class="location-spinner" v-if="isLocating" aria-hidden="true"></span>
    </button>

    <!-- Chart Panel -->
    <div class="chart-panel" v-if="props.chartVisible">
      <button class="close-btn" @click="emit('update:chart-visible', false)">×</button>
      <DataChart title="Wheat Crop Parameters - Historical Data" :initial-layer="activeLayers[0]?.name || 'savi'"
        :is-dark="false" :show-boundary-data="true" />
    </div>

    <!-- Weather Panel -->
    <div class="weather-panel" v-if="weatherVisible">
      <button class="close-btn" @click="weatherVisible = false">×</button>
      <div class="weather-content">
        <h2 class="weather-title">🌤️ Weather Forecast</h2>
        
        <div class="weather-header">
          <div class="weather-location-info">
            <p class="location-name">{{ props.weatherSummary?.location || 'Selected Location' }}</p>
            <p class="location-coords" v-if="pointData">
              {{ pointData.lat?.toFixed(4) }}°N, {{ pointData.lon?.toFixed(4) }}°E
            </p>
          </div>
          <p class="weather-date">{{ props.weatherSummary?.dateLabel || 'Today' }}</p>
        </div>

        <div class="weather-grid">
          <div class="weather-card" v-if="props.weatherSummary?.temperature">
            <span class="weather-icon">🌡️</span>
            <span class="weather-label">Temperature</span>
            <span class="weather-value">{{ props.weatherSummary.temperature }}°C</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.humidity">
            <span class="weather-icon">💧</span>
            <span class="weather-label">Humidity</span>
            <span class="weather-value">{{ props.weatherSummary.humidity }}%</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.windSpeed">
            <span class="weather-icon">💨</span>
            <span class="weather-label">Wind Speed</span>
            <span class="weather-value">{{ props.weatherSummary.windSpeed }} m/s</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.rainfall">
            <span class="weather-icon">🌧️</span>
            <span class="weather-label">Rainfall</span>
            <span class="weather-value">{{ props.weatherSummary.rainfall }} mm</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.solarRadiation">
            <span class="weather-icon">☀️</span>
            <span class="weather-label">Solar Radiation</span>
            <span class="weather-value">{{ props.weatherSummary.solarRadiation }} MJ/m²</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.windDirection">
            <span class="weather-icon">🧭</span>
            <span class="weather-label">Wind Direction</span>
            <span class="weather-value">{{ props.weatherSummary.windDirection }}°</span>
          </div>
        </div>

        <p v-if="!props.weatherSummary" class="no-weather-data">
          No weather data available for this location.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import DataChart from './DataChart.vue'

// DEFINE PROPS - THIS WAS MISSING!
const props = defineProps({
  layers: {
    type: Object,
    default: () => ({ savi: false, kc: false, cwr: false, iwr: false })
  },
  forecastDays: {
    type: String,
    default: 'today'
  },
  slot: {
    type: String,
    default: 'today'
  },
  opacity: {
    type: Number,
    default: 1.0
  },
  selectedDate: {
    type: String,
    default: null
  },
  availableDates: {
    type: Array,
    default: () => []
  },
  weatherSummary: {
    type: Object,
    default: null
  },
  chartVisible: {
    type: Boolean,
    default: false
  },
  isDark: {
    type: Boolean,
    default: true   // dashboard is dark by default
  }
})

const emit = defineEmits(['location-selected', 'calendar-open', 'open-weather', 'update:chart-visible'])

// Add slot to date map for display
const slotToDateMap = ref({})
const weatherVisible = ref(false)

// Create slotToDateMap from availableDates
watch(() => props.availableDates, (dates) => {
  const map = {}
  dates.forEach(d => {
    if (d.slot && d.date) {
      map[d.slot] = d.date
    }
  })
  slotToDateMap.value = map
}, { immediate: true })

const mapEl = ref(null)
let map
let baseLayer = null
let boundaryLayer = null
let wmsLayers = {}
const pointData = ref(null)
const forecastData = ref(null)

// SAVI-Kc relationship constants for derived forecast
const SAVI_KC_SLOPE = 1.2088
const SAVI_KC_INTERCEPT = 0.5375

// Helper to calculate SAVI from Kc forecast
function calculateSaviFromKc(kcValue) {
  if (kcValue == null) return null
  return (kcValue - SAVI_KC_INTERCEPT) / SAVI_KC_SLOPE
}

const isForecastLoading = ref(false)
const boundaryLoaded = ref(false)
const currentMapStyle = ref('street')
const isStyleDropdownOpen = ref(false)
// isDarkMode is now derived from the isDark prop passed by App.vue
const isDarkMode = computed(() => props.isDark)
const isLocating = ref(false)
const locationError = ref(null)
let userLocationMarker = null

// Forecast window state: null = observed, '5day' | '10day' | '15day' = forecast
const selectedWindow = ref(null)
// Separate WMS layer ref for kc forecast overlay
let kcForecastLayer = null

// Map style options
const mapStyles = [
  {
    name: 'street',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap',
    // icon: 'Field'
  },
  {
    name: 'Focus',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '© CartoDB',
    // icon: 'Focus'
  },
  {
    name: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri',
    // icon: 'Satellite'
  }
]

// GeoServer configuration
const GEOSERVER_URL = 'http://localhost:8080/geoserver'
const WORKSPACE = 'irrigation'

const layerConfigs = {
  savi: { name: 'savi', displayName: 'SAVI', style: 'savi_style' },
  kc: { name: 'kc', displayName: 'Kc', style: 'kc_style' },
  cwr: { name: 'cwr', displayName: 'CWR (mm)', style: 'cwr_style' },
  iwr: { name: 'iwr', displayName: 'IWR (mm)', style: 'iwr_style' }
}

// Create WMS layer - using the current slot
function createWMSLayer(layerKey) {
  const config = layerConfigs[layerKey]
  const slot = props.slot || 'today'
  const geoLayerName = `${layerKey}_${slot}`

  return L.tileLayer.wms(`${GEOSERVER_URL}/${WORKSPACE}/wms`, {
    layers: `irrigation:${geoLayerName}`,
    styles: config.style,
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    crs: L.CRS.EPSG3857,
    opacity: props.opacity,
    tiled: true,
    maxZoom: 30
  })
}

function refreshWMSLayers() {
  Object.keys(wmsLayers).forEach(key => {
    if (map && map.hasLayer(wmsLayers[key])) {
      map.removeLayer(wmsLayers[key])
    }
    wmsLayers[key] = createWMSLayer(key)
    if (props.layers[key] && map) {
      wmsLayers[key].addTo(map)
    }
  })
  // Refresh kc forecast overlay when slot changes
  refreshKcForecastLayer()
}

// Create the Kc forecast WMS layer for a specific window
function createKcForecastWMSLayer(window) {
  const slot = props.slot || 'today'
  const geoLayerName = `kc_${slot}_${window}`
  return L.tileLayer.wms(`${GEOSERVER_URL}/${WORKSPACE}/wms`, {
    layers: `irrigation:${geoLayerName}`,
    styles: 'kc_style',
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    crs: L.CRS.EPSG3857,
    opacity: props.opacity,
    tiled: true,
    maxZoom: 30
  })
}

// Toggle between observed kc layer and forecast kc layer
function refreshKcForecastLayer() {
  if (!map) return

  // Remove existing forecast overlay
  if (kcForecastLayer && map.hasLayer(kcForecastLayer)) {
    map.removeLayer(kcForecastLayer)
    kcForecastLayer = null
  }

  if (!selectedWindow.value || !props.layers.kc) return

  // Hide the observed kc history layer
  if (wmsLayers.kc && map.hasLayer(wmsLayers.kc)) {
    map.removeLayer(wmsLayers.kc)
  }

  // Show forecast kc layer
  kcForecastLayer = createKcForecastWMSLayer(selectedWindow.value)
  kcForecastLayer.addTo(map)
}

// Fetch point data
async function fetchPointData(lat, lon) {
  try {
    const pointRes = await fetch(
      `http://localhost:8000/api/point?lat=${lat}&lon=${lon}&slot=${props.slot}`
    )
    const data = await pointRes.json()

    pointData.value = {
      lat: Number(data.lat),
      lon: Number(data.lon),
      acquisition_date: data.acquisition_date || 'N/A',
      values: data.values || {},
    }
    forecastData.value = data.forecast || {}
  } catch (err) {
    console.error("Point fetch error:", err)
    pointData.value = null
  }
}

// Watch for slot changes to refresh layers and fetch point data
watch(() => props.slot, async (newSlot) => {
  if (newSlot) {
    refreshWMSLayers()
    // If we have a current point, refresh its data
    if (pointData.value && pointData.value.lat && pointData.value.lon) {
      await fetchPointData(pointData.value.lat, pointData.value.lon)
    }
  }
}, { immediate: true })

// Watch for selectedWindow changes — swap kc between observed and forecast layer
watch(selectedWindow, () => {
  refreshKcForecastLayer()
})

// Watch for layer toggles
watch(() => props.layers, (val) => {
  if (!map) return
  Object.keys(wmsLayers).forEach(key => {
    if (val[key]) {
      // For kc, only show the history layer if no forecast window is selected
      if (key === 'kc' && selectedWindow.value) {
        // kc forecast overlay handles visibility; hide history layer
        if (map.hasLayer(wmsLayers[key])) map.removeLayer(wmsLayers[key])
        refreshKcForecastLayer()
      } else {
        if (!map.hasLayer(wmsLayers[key])) wmsLayers[key].addTo(map)
        // If kc was just enabled and forecast was active, refresh overlay
        if (key === 'kc') refreshKcForecastLayer()
      }
    } else {
      if (map.hasLayer(wmsLayers[key])) map.removeLayer(wmsLayers[key])
      // If kc was disabled, also remove forecast overlay
      if (key === 'kc' && kcForecastLayer && map.hasLayer(kcForecastLayer)) {
        map.removeLayer(kcForecastLayer)
        kcForecastLayer = null
      }
    }
  })
}, { deep: true })

// Watch for opacity changes
watch(() => props.opacity, (val) => {
  const op = Number(val) || 1
  Object.entries(wmsLayers).forEach(([key, layer]) => {
    if (props.layers[key] && layer) {
      layer.setOpacity(op)
    }
  })
})

// Color mapping based on GeoServer styles
const colorMaps = {
  savi: [
    { value: -1.0, color: '#8B0000' },
    { value: -0.8, color: '#A52A2A' },
    { value: -0.6, color: '#CD5C5C' },
    { value: -0.4, color: '#FF4500' },
    { value: -0.2, color: '#FF8C00' },
    { value: 0.0, color: '#FFA500' },
    { value: 0.1, color: '#FFD700' },
    { value: 0.2, color: '#FFFF00' },
    { value: 0.3, color: '#ADFF2F' },
    { value: 0.4, color: '#90EE90' },
    { value: 0.5, color: '#32CD32' },
    { value: 0.6, color: '#228B22' },
    { value: 0.7, color: '#008000' },
    { value: 0.8, color: '#006400' },
    { value: 0.9, color: '#004d00' },
    { value: 1.0, color: '#003300' }
  ],
  kc: [
    { value: 0.0, color: '#FFD700' },
    { value: 0.1, color: '#FFD700' },
    { value: 0.2, color: '#FFD700' },
    { value: 0.3, color: '#DAA520' },
    { value: 0.4, color: '#BDB76B' },
    { value: 0.5, color: '#90EE90' },
    { value: 0.6, color: '#90EE90' },
    { value: 0.7, color: '#7CCD7C' },
    { value: 0.8, color: '#32CD32' },
    { value: 0.9, color: '#32CD32' },
    { value: 1.0, color: '#228B22' },
    { value: 1.1, color: '#006400' },
    { value: 1.2, color: '#006400' },
    { value: 1.3, color: '#556B2F' },
    { value: 1.4, color: '#8B4513' },
    { value: 1.5, color: '#8B4513' }
  ],
  cwr: [
    { value: 0, color: '#FF4444' },
    { value: 1, color: '#FF4444' },
    { value: 2, color: '#FF6346' },
    { value: 3, color: '#FFA500' },
    { value: 4, color: '#FFA500' },
    { value: 4.5, color: '#FFFF00' },
    { value: 5, color: '#ADFF2F' },
    { value: 5.5, color: '#90EE90' },
    { value: 6, color: '#00CED1' },
    { value: 6.5, color: '#1E90FF' },
    { value: 7, color: '#1E90FF' },
    { value: 7.5, color: '#1E90FF' },
    { value: 8, color: '#0000CD' },
    { value: 8.5, color: '#00008B' },
    { value: 9, color: '#00008B' },
    { value: 9.5, color: '#4B0082' },
    { value: 10, color: '#4B0082' }
  ],
  iwr: [
    { value: 0, color: '#E0F7FA' },
    { value: 1, color: '#B2EBF2' },
    { value: 2, color: '#80DEEA' },
    { value: 3, color: '#4DD0E1' },
    { value: 4, color: '#26C6DA' },
    { value: 5, color: '#00BCD4' },
    { value: 6, color: '#0097A7' },
    { value: 7, color: '#00796B' },
    { value: 8, color: '#00695C' },
    { value: 9, color: '#004D40' },
    { value: 10, color: '#1A237E' }
  ]
}

// Current style object
const currentStyle = computed(() => {
  return mapStyles.find(s => s.name === currentMapStyle.value) || mapStyles[0]
})

// Computed active layers based on props
const activeLayers = computed(() => {
  return Object.keys(props.layers)
    .filter(key => props.layers[key])
    .map(key => layerConfigs[key])
})

// Get color for a specific value
function getColorForValue(layerName, value) {
  if (value === undefined || value === null) return '#808080'

  const colorMap = colorMaps[layerName]
  if (!colorMap) return '#808080'

  let closest = colorMap[0]
  let minDiff = Math.abs(value - closest.value)

  for (let i = 1; i < colorMap.length; i++) {
    const diff = Math.abs(value - colorMap[i].value)
    if (diff < minDiff) {
      minDiff = diff
      closest = colorMap[i]
    }
  }

  return closest.color
}

// Get style object for value display
function getValueStyle(layerName, value) {
  const bgColor = getColorForValue(layerName, value)
  const textColor = getTextColor(bgColor)

  return {
    backgroundColor: bgColor,
    padding: '4px 8px',
    borderRadius: '4px',
    fontWeight: 'bold',
    color: textColor,
    display: 'inline-block',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
  }
}

// Determine text color based on background luminance
function getTextColor(hexColor) {
  const r = parseInt(hexColor.slice(1, 3), 16)
  const g = parseInt(hexColor.slice(3, 5), 16)
  const b = parseInt(hexColor.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.5 ? '#000000' : '#ffffff'
}

// Format number
function format(val) {
  return typeof val === 'number' ? val.toFixed(3) : "-"
}

// Toggle dropdown
function toggleStyleDropdown() {
  isStyleDropdownOpen.value = !isStyleDropdownOpen.value
}

// Select forecast window for Kc layer
function selectForecastWindow(window) {
  selectedWindow.value = selectedWindow.value === window ? null : window
}

// Select map style
function selectMapStyle(styleName) {
  currentMapStyle.value = styleName
  isStyleDropdownOpen.value = false
  changeMapStyle(styleName)
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
  const dropdown = document.querySelector('.map-style-dropdown')
  if (dropdown && !dropdown.contains(event.target)) {
    isStyleDropdownOpen.value = false
  }
}

// Change map base style
function changeMapStyle(styleName) {
  const style = mapStyles.find(s => s.name === styleName)
  if (!style) return

  if (baseLayer) {
    map.removeLayer(baseLayer)
  }

  baseLayer = L.tileLayer(style.url, {
    attribution: style.attribution,
    maxZoom: 19
  }).addTo(map)

  if (boundaryLayer) {
    boundaryLayer.bringToFront()
  }

  Object.keys(wmsLayers).forEach(key => {
    if (props.layers[key] && map.hasLayer(wmsLayers[key])) {
      wmsLayers[key].bringToFront()
    }
  })
}

// Load boundary
async function loadBoundary() {
  try {
    const res = await fetch('http://localhost:8000/api/boundary')
    const data = await res.json()

    if (boundaryLayer) {
      map.removeLayer(boundaryLayer)
    }

    boundaryLayer = L.geoJSON(data.geojson, {
      style: {
        color: '#19c7a6',
        weight: 2.5,
        fill: false,
        opacity: 0.9,
        dashArray: '7, 5'
      }
    }).addTo(map)

    const bounds = boundaryLayer.getBounds()
    map.fitBounds(bounds, { padding: [20, 20] })
    boundaryLoaded.value = true
  } catch (err) {
    console.error("Boundary load failed:", err)
  }
}

// Unit label per layer
function layerUnit(name) {
  return { savi: '', kc: '', cwr: 'mm/day', iwr: 'mm/day' }[name] ?? ''
}

// Check if point is within boundary
function isPointInBoundary(lat, lon) {
  if (!boundaryLayer) return false
  const bounds = boundaryLayer.getBounds()
  return bounds.contains([lat, lon])
}

// Get current location and show info panel
async function getCurrentLocation() {
  if (!navigator.geolocation) {
    alert('Geolocation is not supported by your browser')
    return
  }

  isLocating.value = true
  locationError.value = null

  if (userLocationMarker) {
    map.removeLayer(userLocationMarker)
    userLocationMarker = null
  }

  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      })
    })

    const { latitude, longitude } = position.coords
    
    if (!isPointInBoundary(latitude, longitude)) {
      alert('Your location is outside the study area boundary')
      map.flyTo([latitude, longitude], 10, { duration: 1.5 })
      
      userLocationMarker = L.marker([latitude, longitude], {
        icon: L.divIcon({
          className: 'blue-dot-marker',
          html: '<div class="blue-dot"></div><div class="pulse-ring"></div>',
          iconSize: [24, 24],
          iconAnchor: [12, 12]
        })
      }).addTo(map).bindPopup('Your location (outside study area)').openPopup()
      
      return
    }

    await fetchPointData(latitude, longitude)
    map.flyTo([latitude, longitude], 12, { duration: 1.5 })
    emit('location-selected', { lat: latitude, lon: longitude })

    userLocationMarker = L.marker([latitude, longitude], {
      icon: L.divIcon({
        className: 'blue-dot-marker',
        html: '<div class="blue-dot"></div><div class="pulse-ring"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      })
    }).addTo(map).bindPopup('Your current location').openPopup()

    setTimeout(() => {
      if (userLocationMarker && map.hasLayer(userLocationMarker)) {
        map.removeLayer(userLocationMarker)
        userLocationMarker = null
      }
    }, 8000)

  } catch (error) {
    console.error('Error getting location:', error)
    locationError.value = error.message
    
    let errorMessage = 'Unable to get your location. '
    switch(error.code) {
      case error.PERMISSION_DENIED:
        errorMessage += 'Please enable location access.'
        break
      case error.POSITION_UNAVAILABLE:
        errorMessage += 'Location information is unavailable.'
        break
      case error.TIMEOUT:
        errorMessage += 'Location request timed out.'
        break
      default:
        errorMessage += 'An unknown error occurred.'
    }
    alert(errorMessage)
  } finally {
    isLocating.value = false
  }
}

// Handle map click
async function onMapClick(e) {
  const { lat, lng } = e.latlng
  
  const popup = L.popup({
    className: `custom-value-popup ${!isDarkMode.value ? 'light' : ''}`,
    closeButton: false,
    offset: [0, -10],
    autoPan: false
  })
  .setLatLng([lat, lng])
  .setContent('<div class="popup-loading"><span>⏳</span> Fetching...</div>')
  .openOn(map)

  await fetchPointData(lat, lng)
  emit('location-selected', { lat, lon: lng })

  if (pointData.value) {
    const activeWithData = activeLayers.value.filter(l => pointData.value.values?.[l.name] != null)
    
    if (activeWithData.length > 0) {
      let content = `<div class="popup-content-multi">`
      activeWithData.forEach(layer => {
        const val = pointData.value.values[layer.name]
        const formattedVal = val.toFixed(3)
        const unit = layerUnit(layer.name)
        content += `
          <div class="popup-row">
            <span class="value-layer">${layer.displayName}:</span>
            <span class="value-num">${formattedVal}</span>
            <span class="value-unit">${unit}</span>
          </div>
        `
      })
      content += `</div>`
      popup.setContent(content)
    } else {
      popup.setContent('<div class="popup-content no-data">No layer data here</div>')
      setTimeout(() => { if (map.hasLayer(popup)) map.closePopup(popup) }, 2000)
    }
  } else {
    map.closePopup(popup)
  }
}

// Apply filter method (exposed to parent)
function applyFilter(layer, filter) {
  if (wmsLayers[layer]) {
    wmsLayers[layer].setParams({
      CQL_FILTER: filter
    })
  }
}

// Initialize map
onMounted(() => {
  map = L.map(mapEl.value, {
    center: [29.0, 79.4],
    zoom: 9,
    maxZoom: 22,
    minZoom: 5,
    zoomControl: true
  })

  const defaultStyle = mapStyles[0]
  baseLayer = L.tileLayer(defaultStyle.url, {
    attribution: defaultStyle.attribution,
    maxZoom: 19
  }).addTo(map)

  const labels = L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png',
    {
      attribution: '© CartoDB',
      pane: 'overlayPane'
    }
  )
  labels.addTo(map)

  // Create WMS layers
  wmsLayers.savi = createWMSLayer('savi')
  wmsLayers.kc = createWMSLayer('kc')
  wmsLayers.cwr = createWMSLayer('cwr')
  wmsLayers.iwr = createWMSLayer('iwr')

  loadBoundary()
  map.on('click', onMapClick)
  document.addEventListener('click', handleClickOutside)
})

// Clean up
onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  if (userLocationMarker && map) {
    map.removeLayer(userLocationMarker)
  }
  if (map) {
    map.remove()
  }
})

defineExpose({
  invalidateMapSize: () => {
    if (map) {
      setTimeout(() => {
        map.invalidateSize()
        if (boundaryLayer) {
          map.fitBounds(boundaryLayer.getBounds())
        }
      }, 100)
    }
  },
  applyFilter
})
</script>

<style scoped>

.map-container {
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
  font-family: 'Space Grotesk', 'JetBrains Mono', sans-serif;
  background:
    radial-gradient(circle at top right, rgba(25, 199, 166, 0.08), transparent 24%),
    linear-gradient(180deg, #050810 0%, #080c14 100%);
}

#map {
  width: 100%;
  height: 100%;
  min-height: 0;
  background: #0a0f14;
}

/* ─── Shared pill / card base ───────────────────────────── */
.pill-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 50px;
  border: 1px solid rgba(200, 210, 220, 0.12);
  background: rgba(10, 15, 20, 0.9);
  backdrop-filter: blur(14px);
  color: #d0dbe5;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3);
  transition: all 0.2s ease;
  white-space: nowrap;
}
.pill-btn:hover {
  border-color: rgba(47, 133, 90, 0.5);
  color: #3b9fd9;
  transform: translateY(-2px);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.4);
}

/* ─── Map Style Dropdown ────────────────────────────────── */
.map-style-dropdown {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 1000;
  width: 170px;
}

.dropdown-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 999px;
  border: 1px solid rgba(200, 210, 220, 0.1);
  background: rgba(5, 8, 14, 0.9);
  backdrop-filter: blur(14px);
  color: #d0dbe5;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.4);
  transition: all 0.2s ease;
}

.dropdown-toggle:hover {
  border-color: rgba(25, 199, 166, 0.5);
  color: #f0f4f8;
  transform: translateY(-1px);
}

.style-icon { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #8899aa; }
.style-name  { flex: 1; }
.dropdown-arrow { font-size: 0.7rem; opacity: 0.6; color: #8899aa; }

.dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 100%;
  background: rgba(5, 8, 14, 0.96);
  border: 1px solid rgba(200, 210, 220, 0.1);
  border-radius: 16px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  animation: dropdownFadeIn 0.18s ease;
}

@keyframes dropdownFadeIn {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.dropdown-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: #8899aa;
  font-size: 0.82rem;
  font-weight: 500;
  transition: all 0.18s;
  text-align: left;
}
.dropdown-item:hover { background: rgba(47, 133, 90, 0.15); color: #f0f4f8; }
.dropdown-item.active { background: rgba(47, 133, 90, 0.2); color: #3b9fd9; }
.check-mark { margin-left: auto; font-weight: 700; color: #3b9fd9; }

/* ─── Info Panel ────────────────────────────────────────── */
.info-panel {
  position: absolute;
  bottom: 70px;
  left: 16px;
  background:
    linear-gradient(180deg, rgba(5, 8, 14, 0.96), rgba(8, 12, 18, 0.94)),
    radial-gradient(circle at top right, rgba(25, 199, 166, 0.08), transparent 34%);
  backdrop-filter: blur(16px);
  padding: 18px 18px 14px;
  border-radius: 22px;
  border: 1px solid rgba(200, 210, 220, 0.1);
  z-index: 1000;
  width: 360px;
  max-width: 90vw;
  max-height: 75vh;
  overflow-y: auto;
  box-shadow: 0 24px 52px rgba(0, 0, 0, 0.5);
  color: #f0f4f8;
  scrollbar-width: thin;
  scrollbar-color: rgba(47, 133, 90, 0.3) transparent;
  transition: all 0.3s ease;
}

.info-panel.light {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(47, 133, 90, 0.24);
  color: #1e293b;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

.info-panel.light h3 { color: #2f855a; }
.info-panel.light .meta-row { background: rgba(0, 0, 0, 0.04); }
.info-panel.light .meta-label { color: #64748b; }
.info-panel.light .meta-val { color: #0f172a; }
.info-panel.light .sentinel-date { color: #2f855a; }
.info-panel.light .coord-val { color: #334155; }
.info-panel.light .fc-item { background: rgba(0, 0, 0, 0.03); }
.info-panel.light .fc-label { color: #64748b; }
.info-panel.light .value-section { border-top-color: rgba(0, 0, 0, 0.08); }
.info-panel.light .value-section h4 { color: #334155; }
.info-panel.light .loading-hint { color: #64748b; }
.info-panel.light .close-btn { background: rgba(0, 0, 0, 0.05); border-color: rgba(0, 0, 0, 0.1); color: #64748b; }
.info-panel.light .close-btn:hover { background: rgba(47, 133, 90, 0.1); color: #2f855a; border-color: rgba(47, 133, 90, 0.28); }
.info-panel::-webkit-scrollbar { width: 4px; }
.info-panel::-webkit-scrollbar-thumb { background: rgba(47, 133, 90, 0.2); border-radius: 2px; }

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(200, 210, 220, 0.06);
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
}
.meta-icon  { font-size: 0.9rem; flex-shrink: 0; }
.meta-label { color: #8899aa; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.67rem; flex-shrink: 0; }
.meta-val   { margin-left: auto; font-weight: 600; text-align: right; font-size: 0.73rem; color: #d0dbe5; }
.sentinel-date { color: #3b9fd9; }
.coord-val     { color: #8899aa; font-size: 0.7rem; }
.weather-row { cursor: pointer; }
.weather-link {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.weather-date-line { color: #d0dbe5; }
.weather-location-line { color: #3b9fd9; font-size: 0.66rem; }
.info-panel.light .weather-date-line { color: #0f172a; }
.info-panel.light .weather-location-line { color: #2f855a; }

.forecast-grid {
  display: flex;
  flex-direction: row;
  gap: 6px;
  overflow-x: auto;
  padding: 2px 0 8px;
  scrollbar-width: none;
}
.forecast-grid::-webkit-scrollbar { display: none; }

.fc-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 6px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  min-width: 76px;
  flex: 1;
  transition: all 0.2s ease;
  border: 1px solid rgba(200, 210, 220, 0.06);
}
.fc-item[onclick], .fc-item:has(.value) { cursor: pointer; }
.fc-item:hover { background: rgba(47, 133, 90, 0.1); border-color: rgba(47, 133, 90, 0.2); }

.fc-item--active {
  background: rgba(47, 133, 90, 0.2) !important;
  border-color: rgba(47, 133, 90, 0.4) !important;
}

.fc-label {
  font-size: 0.62rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.observed-label { color: #3b9fd9; font-weight: 600; }
.fc-na { opacity: 0.5; }
.unit {
  font-style: normal;
  font-size: 0.68rem;
  opacity: 0.7;
  margin-left: 3px;
}
.nodata-chip {
  font-size: 0.7rem;
  color: #8899aa;
  font-style: italic;
  font-family: 'JetBrains Mono', monospace;
}
.nodata-hint {
  font-size: 0.72rem;
  color: #8899aa;
  font-style: italic;
  margin: 4px 0 0;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
}
.model-tag {
  font-size: 0.62rem;
  color: #3A5A7A;
  font-family: 'JetBrains Mono', monospace;
  text-align: right;
  margin: 2px 0 0;
  padding: 0 4px;
}
.loading-hint {
  font-size: 0.7rem;
  color: #8ca6b8;
  text-align: center;
  margin: 8px 0 0;
  font-style: italic;
}

.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(170, 199, 216, 0.12);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  color: #8ca6b8;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}
.close-btn:hover { background: rgba(25, 199, 166, 0.12); color: #88f2db; border-color: rgba(25, 199, 166, 0.28); }

.info-panel h3 {
  margin: 0 0 10px 0;
  color: #effbff;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace;
}

.info-panel p {
  font-size: 0.76rem;
  color: #8ca6b8;
  margin: 0 0 10px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(255, 255, 255, 0.05) !important;
  padding: 6px 10px;
  border-radius: 10px;
}

.value-section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(170, 199, 216, 0.1);
}

.value-section h4 {
  margin: 0 0 10px 0;
  font-size: 0.75rem;
  font-weight: 700;
  color: #b9cfdd;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-family: 'JetBrains Mono', monospace;
}

.value {
  font-weight: 700;
  font-size: 0.85rem;
  display: inline-block;
  transition: transform 0.2s;
  border-radius: 6px;
  padding: 3px 7px;
}
.value:hover { transform: scale(1.05); }

/* ─── Location Button ───────────────────────────────────── */
.location-btn {
  position: absolute;
  bottom: 30px;
  right: 20px;
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 52px;
  height: 52px;
  padding: 0;
  border-radius: 16px;
  border: 1px solid rgba(170, 199, 216, 0.14);
  background:
    radial-gradient(circle at 50% 50%, rgba(25, 199, 166, 0.18), transparent 58%),
    rgba(9, 23, 34, 0.86);
  backdrop-filter: blur(14px);
  color: #eaf6fc;
  cursor: pointer;
  box-shadow: 0 14px 34px rgba(1, 10, 17, 0.24);
  transition: all 0.2s ease;
}
.location-btn:hover {
  border-color: rgba(25, 199, 166, 0.38);
  color: #88f2db;
  transform: translateY(-2px);
  box-shadow: 0 18px 38px rgba(1, 10, 17, 0.26);
}
.location-btn.loading { opacity: 0.65; cursor: wait; }
.location-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.location-btn:disabled:hover { transform: none; border-color: rgba(170, 199, 216, 0.14); color: #eaf6fc; }
.location-icon {
  display: inline-flex;
  width: 24px;
  height: 24px;
}
.location-icon svg {
  width: 100%;
  height: 100%;
}
.location-spinner {
  position: absolute;
  inset: 10px;
  border: 2px solid rgba(170, 199, 216, 0.14);
  border-top-color: #19c7a6;
  border-radius: 50%;
  animation: locateSpin 0.85s linear infinite;
}

@keyframes locateSpin {
  to { transform: rotate(360deg); }
}

/* ─── Chart Panel ───────────────────────────────────────── */
.chart-panel {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(62vw, 900px);
  height: min(72vh, 620px);
  min-width: 520px;
  min-height: 420px;
  background: linear-gradient(180deg, rgba(10, 25, 36, 0.96), rgba(14, 32, 45, 0.94));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(170, 199, 216, 0.14);
  border-radius: 22px;
  z-index: 2000;
  box-shadow: 0 24px 70px rgba(1, 10, 17, 0.28), 0 0 0 1px rgba(170, 199, 216, 0.04);
  overflow: hidden;
  animation: fadeIn 0.22s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translate(-50%, -54%); }
  to   { opacity: 1; transform: translate(-50%, -50%); }
}

.chart-panel > .close-btn {
  z-index: 2001;
  top: 14px;
  right: 14px;
}

/* ─── Weather Panel ───────────────────────────────────────── */
.weather-panel {
  position: absolute;
  top: 50%;
  right: 20px;
  transform: translateY(-50%);
  width: min(320px, 90vw);
  max-height: 85vh;
  background: linear-gradient(180deg, rgba(10, 25, 36, 0.96), rgba(14, 32, 45, 0.94));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(170, 199, 216, 0.14);
  border-radius: 20px;
  z-index: 2000;
  box-shadow: 0 24px 70px rgba(1, 10, 17, 0.28), 0 0 0 1px rgba(170, 199, 216, 0.04);
  overflow-y: auto;
  animation: slideInRight 0.28s ease;
  scrollbar-width: thin;
  scrollbar-color: rgba(47, 133, 90, 0.3) transparent;
}

.weather-panel::-webkit-scrollbar {
  width: 4px;
}

.weather-panel::-webkit-scrollbar-thumb {
  background: rgba(47, 133, 90, 0.2);
  border-radius: 2px;
}

@keyframes slideInRight {
  from { opacity: 0; transform: translateY(-50%) translateX(30px); }
  to   { opacity: 1; transform: translateY(-50%) translateX(0); }
}

.weather-panel > .close-btn {
  z-index: 2001;
  top: 12px;
  right: 12px;
}

.weather-content {
  padding: 20px 18px;
}

.weather-title {
  margin: 0 0 16px 0;
  color: #effbff;
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  font-family: 'JetBrains Mono', monospace;
}

.weather-header {
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(170, 199, 216, 0.1);
}

.weather-location-info {
  margin-bottom: 8px;
}

.location-name {
  margin: 0;
  color: #d0dbe5;
  font-size: 0.82rem;
  font-weight: 600;
}

.location-coords {
  margin: 2px 0 0 0;
  color: #8899aa;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
}

.weather-date {
  margin: 0;
  color: #3b9fd9;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.weather-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

.weather-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(200, 210, 220, 0.08);
  transition: all 0.2s ease;
}

.weather-card:hover {
  background: rgba(47, 133, 90, 0.12);
  border-color: rgba(47, 133, 90, 0.2);
}

.weather-icon {
  font-size: 1.6rem;
}

.weather-label {
  font-size: 0.65rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
}

.weather-value {
  font-size: 0.9rem;
  color: #3b9fd9;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.no-weather-data {
  text-align: center;
  color: #8899aa;
  font-style: italic;
  font-size: 0.75rem;
  margin: 12px 0 0 0;
}

.leaflet-tile { image-rendering: auto; }

/* ─── Blue Dot Marker ───────────────────────────────────── */
:global(.blue-dot-marker) { position: relative; }
:global(.blue-dot) {
  width: 16px; height: 16px;
  background: #19c7a6;
  border: 3px solid white;
  border-radius: 50%;
  position: absolute; top: 4px; left: 4px;
  z-index: 2;
  box-shadow: 0 0 12px rgba(25, 199, 166, 0.45);
}
:global(.pulse-ring) {
  width: 32px; height: 32px;
  background: rgba(25, 199, 166, 0.22);
  border-radius: 50%;
  position: absolute; top: -4px; left: -4px;
  animation: markerPulse 1.5s ease-out infinite;
  z-index: 1;
}
@keyframes markerPulse {
  0%   { transform: scale(0.5); opacity: 0.5; }
  50%  { transform: scale(1.2); opacity: 0.3; }
  100% { transform: scale(1.5); opacity: 0; }
}

/* ─── Responsive ────────────────────────────────────────── */
@media (max-width: 768px) {
  .map-style-dropdown { top: 10px; right: 10px; width: 155px; }
  .info-panel { left: 10px; right: 10px; bottom: 10px; width: auto; max-width: none; max-height: 42vh; }
  .location-btn { right: 78px; bottom: 14px; width: 48px; height: 48px; }
  .chart-panel { min-width: 90vw; width: 92vw; min-height: 55vh; }
  .weather-panel { right: 10px; width: calc(100% - 20px); max-width: 340px; }
}

@media (max-width: 480px) {
  .map-style-dropdown { width: 146px; }
  .dropdown-toggle { padding: 8px 12px; }
  .info-panel { padding: 14px 14px 12px; border-radius: 18px; }
  .location-btn { right: 66px; width: 46px; height: 46px; border-radius: 14px; }
  .chart-panel { min-width: 94vw; width: 94vw; top: 48%; }
  .weather-panel { right: 8px; width: calc(100% - 16px); max-width: 290px; }
  .weather-grid { grid-template-columns: 1fr; }
}
/* ─── Kc Forecast Window Bar ────────────────────────────────────────── */
.forecast-window-bar {
  position: absolute;
  top: 62px;
  right: 16px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(200, 210, 220, 0.1);
  background: rgba(5, 8, 14, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  animation: dropdownFadeIn 0.18s ease;
}

.fw-label {
  font-size: 0.68rem;
  font-weight: 700;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
  padding-right: 6px;
  border-right: 1px solid rgba(255,255,255,0.06);
  margin-right: 4px;
}

.fw-btn {
  padding: 5px 11px;
  border-radius: 50px;
  border: 1px solid transparent;
  background: transparent;
  color: #8899aa;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  font-family: 'Space Grotesk', sans-serif;
  white-space: nowrap;
}
.fw-btn:hover {
  background: rgba(47, 133, 90, 0.15);
  color: #d0dbe5;
}
.fw-btn.active {
  background: rgba(47, 133, 90, 0.25);
  border-color: rgba(47, 133, 90, 0.5);
  color: #3b9fd9;
  box-shadow: 0 0 10px rgba(47, 133, 90, 0.2);
}

.fc-label--active {
  color: #3b9fd9 !important;
  font-weight: 700;
}

/* Forecast window bar responsive */
@media (max-width: 768px) {
  .forecast-window-bar {
    top: 54px;
    right: 10px;
    padding: 5px 8px;
    gap: 2px;
  }
  .fw-btn { padding: 4px 8px; font-size: 0.68rem; }
}

@media (max-width: 480px) {
  .forecast-window-bar { gap: 1px; }
  .fw-label { display: none; }
  .fw-btn { padding: 4px 7px; font-size: 0.65rem; }
}

/* ─── Custom Value Popup ────────────────────────────────── */ 
:global(.custom-value-popup .leaflet-popup-content-wrapper) { 
  background: rgba(239, 242, 245, 0.9) !important; 
  backdrop-filter: blur(14px) saturate(180%); 
  border: 1px solid rgba(0, 0, 0, 0.35); 
  border-radius: 12px; 
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.4); 
  padding: 10; 
} 

:global(.custom-value-popup .leaflet-popup-content) { 
  margin: 5 !important; 
  min-width: 190px !important;
} 

:global(.custom-value-popup .leaflet-popup-tip) { 
  background: rgba(13, 25, 48, 0.88) !important; 
  border-left: 1px solid rgba(0, 212, 168, 0.2); 
  border-bottom: 1px solid rgba(0, 212, 168, 0.2); 
} 

.popup-content-multi {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.popup-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.popup-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

:global(.custom-value-popup.light .leaflet-popup-content-wrapper) {
  background: rgba(255, 255, 255, 0.94) !important;
  border-color: rgba(13, 148, 136, 0.25);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
}

:global(.custom-value-popup.light .leaflet-popup-tip) {
  background: rgba(255, 255, 255, 0.94) !important;
}

:global(.custom-value-popup.light .value-layer) {
  color: #475569 !important;
  font-weight: 600;
}

:global(.custom-value-popup.light .value-num) {
  color: #0d9488 !important;
  font-weight: 700;
}

:global(.custom-value-popup.light .value-unit) {
  color: #64748b !important;
}

:global(.custom-value-popup.light .popup-row) {
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

:global(.custom-value-popup.light .popup-loading) {
  color: #475569;
}

.popup-loading { 
  padding: 14px 20px; 
  color: #C8DFF0; 
  font-family: 'JetBrains Mono', monospace; 
  font-size: 0.85rem; 
  display: flex; 
  align-items: center; 
  gap: 10px; 
} 

.value-layer { 
  color: #C8DFF0; 
  font-size: 0.8rem;
  font-weight: 500; 
  text-transform: uppercase;
  letter-spacing: 0.03em;
} 

.value-num { 
  color: #00D4A8; 
  font-weight: 700; 
  font-size: 1rem;
  font-family: 'JetBrains Mono', monospace; 
  margin-left: auto;
} 

.value-unit { 
  font-size: 0.72rem; 
  color: #8AACCC; 
  font-weight: 500; 
} 

.no-data { 
  padding: 14px 20px;
  color: #8AACCC; 
  font-style: italic; 
  font-weight: 400; 
  font-size: 0.85rem;
} 
</style>
