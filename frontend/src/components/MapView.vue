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
    <div class="info-panel" v-if="pointData">
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

      <!-- No active layer hint -->
      <p v-if="activeLayers.length === 0" class="nodata-hint">
        Enable a layer in the sidebar to see values.
      </p>

      <!-- Per-layer value cards -->
      <div v-for="layer in activeLayers" :key="layer.name" class="value-section">
        <h4>{{ layer.displayName }}</h4>

        <!-- Current pixel value (from /api/point) -->
        <div class="forecast-table">
          <div class="fc-row fc-header">
            <span>Period</span>
            <span>Value</span>
          </div>

          <!-- Observed (satellite pixel) -->
          <div class="fc-row">
            <span class="fc-label observed-label">Today</span>
            <span v-if="pointData.values?.[layer.name] != null"
                  class="value" :style="getValueStyle(layer.name, pointData.values[layer.name])">
              {{ format(pointData.values[layer.name]) }}
              <em class="unit">{{ layerUnit(layer.name) }}</em>
            </span>
            <span v-else class="nodata-chip">No data</span>
          </div>

          <!-- 5/10/15-day forecast — Kc only -->
          <template v-if="forecastData && layer.name === 'kc'">
            <div class="fc-row" v-for="w in [['5day','5-day'], ['10day','10-day'], ['15day','15-day']]" :key="w[0]">
              <span class="fc-label" :class="{ 'fc-label--active': selectedWindow === w[0] }">{{ w[1] }} avg</span>
              <span v-if="forecastData?.kc?.[w[0]] != null"
                    class="value"
                    :style="getValueStyle('kc', forecastData.kc[w[0]])">
                {{ format(forecastData.kc[w[0]]) }}
                <em class="unit"></em>
              </span>
              <span v-else class="nodata-chip">—</span>
            </div>
          </template>

          <!-- 5-day forecast — CWR / IWR only -->
          <template v-if="forecastData && (layer.name === 'cwr' || layer.name === 'iwr')">
            <div class="fc-row">
              <span class="fc-label">5-day avg</span>
              <span v-if="forecastData?.[layer.name]?.['5day'] != null"
                    class="value"
                    :style="getValueStyle(layer.name, forecastData[layer.name]['5day'])">
                {{ format(forecastData[layer.name]['5day']) }}
                <em class="unit">mm/day</em>
              </span>
              <span v-else class="nodata-chip">—</span>
            </div>
            <div class="fc-row">
              <span class="fc-label">10-day avg</span>
              <span v-if="forecastData?.[layer.name]?.['10day'] != null"
                    class="value"
                    :style="getValueStyle(layer.name, forecastData[layer.name]['10day'])">
                {{ format(forecastData[layer.name]['10day']) }}
                <em class="unit">mm/day</em>
              </span>
              <span v-else class="nodata-chip">—</span>
            </div>
            <div class="fc-row">
              <span class="fc-label">15-day avg</span>
              <span v-if="forecastData?.[layer.name]?.['15day'] != null"
                    class="value"
                    :style="getValueStyle(layer.name, forecastData[layer.name]['15day'])">
                {{ format(forecastData[layer.name]['15day']) }}
                <em class="unit">mm/day</em>
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
    <button class="location-btn" @click="getCurrentLocation" :class="{ 'loading': isLocating }" :disabled="isLocating">
      <span class="location-icon">◉</span>
      <span class="location-text">{{ isLocating ? 'Locating...' : 'My Location' }}</span>
    </button>

    <!-- Chart Toggle Button -->
    <button class="chart-toggle-btn" @click="toggleChart" :class="{ active: isChartVisible }">
      <span class="chart-icon">📊</span>
      <span class="chart-text">{{ isChartVisible ? 'Hide Chart' : 'Show Chart' }}</span>
    </button>

    <!-- Chart Panel -->
    <div class="chart-panel" v-if="isChartVisible">
      <button class="close-btn" @click="isChartVisible = false">×</button>
      <DataChart title="Wheat Crop Parameters - Historical Data" :initial-layer="activeLayers[0]?.name || 'savi'"
        :is-dark="isDarkMode" :show-boundary-data="true" />
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
  isDark: {
    type: Boolean,
    default: true   // dashboard is dark by default
  }
})

// Add slot to date map for display
const slotToDateMap = ref({})

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
const isForecastLoading = ref(false)
const boundaryLoaded = ref(false)
const currentMapStyle = ref('Dark')
const isStyleDropdownOpen = ref(false)
const isChartVisible = ref(false)
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
    name: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '© CartoDB',
    icon: '🌙'
  },
  {
    name: 'Street',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap',
    icon: '🗺️'
  },
  {
    name: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri',
    icon: '🛰️'
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
        color: '#ff7800',
        weight: 3,
        fill: false,
        dashArray: '5, 5'
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
  await fetchPointData(lat, lng)
}

// Toggle chart visibility
function toggleChart() {
  isChartVisible.value = !isChartVisible.value
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
/* Keep all your existing styles here - they remain unchanged */
.map-container {
  width: 100%;
  height: 100%;
  position: relative;
  font-family: 'Space Grotesk', 'JetBrains Mono', sans-serif;
}

#map {
  width: 100%;
  height: 100%;
  background: #060E1A;
}

/* ─── Shared pill / card base ───────────────────────────── */
.pill-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 50px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(4, 15, 36, 0.92);
  backdrop-filter: blur(14px);
  color: #C8DFF0;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.45);
  transition: all 0.2s ease;
  white-space: nowrap;
}
.pill-btn:hover {
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.55);
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
  border-radius: 50px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(4, 15, 36, 0.92);
  backdrop-filter: blur(14px);
  color: #C8DFF0;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.45);
  transition: all 0.2s ease;
}

.dropdown-toggle:hover {
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  transform: translateY(-1px);
}

.style-icon { font-size: 1rem; }
.style-name  { flex: 1; }
.dropdown-arrow { font-size: 0.7rem; opacity: 0.6; }

.dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 100%;
  background: rgba(4, 15, 36, 0.97);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.55);
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
  color: #6B8BAD;
  font-size: 0.82rem;
  font-weight: 500;
  transition: all 0.18s;
  text-align: left;
}
.dropdown-item:hover { background: rgba(255,255,255,0.05); color: #E8F4FD; }
.dropdown-item.active { background: rgba(0,212,168,0.12); color: #00D4A8; }
.check-mark { margin-left: auto; font-weight: 700; color: #00D4A8; }

/* ─── Info Panel ────────────────────────────────────────── */
.info-panel {
  position: absolute;
  bottom: 70px;
  left: 16px;
  background: rgba(4, 15, 36, 0.96);
  backdrop-filter: blur(16px);
  padding: 18px 18px 14px;
  border-radius: 18px;
  border: 1px solid rgba(0,212,168,0.2);
  z-index: 1000;
  max-width: 300px;
  max-height: 75vh;
  overflow-y: auto;
  box-shadow: 0 12px 40px rgba(0,0,0,0.55);
  color: #C8DFF0;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,212,168,0.2) transparent;
}
.info-panel::-webkit-scrollbar { width: 4px; }
.info-panel::-webkit-scrollbar-thumb { background: rgba(0,212,168,0.2); border-radius: 2px; }

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 9px;
  background: rgba(0,0,0,0.22);
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
}
.meta-icon  { font-size: 0.9rem; flex-shrink: 0; }
.meta-label { color: #4A6A8A; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.67rem; flex-shrink: 0; }
.meta-val   { margin-left: auto; font-weight: 600; text-align: right; font-size: 0.73rem; }
.sentinel-date { color: #00D4A8; }
.coord-val     { color: #8AACCC; font-size: 0.7rem; }

.forecast-table {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.fc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 7px;
  background: rgba(255,255,255,0.03);
}
.fc-header {
  background: transparent;
  padding: 2px 8px 4px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
.fc-header span {
  font-size: 0.64rem;
  color: #4A6A8A;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-family: 'JetBrains Mono', monospace;
}
.fc-label {
  font-size: 0.72rem;
  color: #6B8BAD;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.observed-label { color: #8AACCC; font-weight: 600; }
.fc-na { opacity: 0.5; }
.unit {
  font-style: normal;
  font-size: 0.68rem;
  opacity: 0.7;
  margin-left: 3px;
}
.nodata-chip {
  font-size: 0.7rem;
  color: #4A6A8A;
  font-style: italic;
  font-family: 'JetBrains Mono', monospace;
}
.nodata-hint {
  font-size: 0.72rem;
  color: #4A6A8A;
  font-style: italic;
  margin: 4px 0 0;
  padding: 6px 10px;
  background: rgba(0,0,0,0.18);
  border-radius: 7px;
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
  color: #4A6A8A;
  text-align: center;
  margin: 8px 0 0;
  font-style: italic;
}

.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  color: #6B8BAD;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}
.close-btn:hover { background: rgba(0,212,168,0.15); color: #00D4A8; border-color: rgba(0,212,168,0.4); }

.info-panel h3 {
  margin: 0 0 10px 0;
  color: #00D4A8;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace;
}

.info-panel p {
  font-size: 0.76rem;
  color: #6B8BAD;
  margin: 0 0 10px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(0,0,0,0.25) !important;
  padding: 6px 10px;
  border-radius: 8px;
}

.value-section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,0.07);
}

.value-section h4 {
  margin: 0 0 10px 0;
  font-size: 0.75rem;
  font-weight: 700;
  color: #8AACCC;
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
  bottom: 20px;
  right: 160px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 50px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(4, 15, 36, 0.92);
  backdrop-filter: blur(14px);
  color: #C8DFF0;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.45);
  transition: all 0.2s ease;
}
.location-btn:hover {
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.55);
}
.location-btn.loading { opacity: 0.65; cursor: wait; }
.location-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.location-btn:disabled:hover { transform: none; border-color: rgba(255,255,255,0.1); color: #C8DFF0; }
.location-icon { font-size: 1rem; }

/* ─── Chart Toggle Button ───────────────────────────────── */
.chart-toggle-btn {
  position: absolute;
  bottom: 20px;
  right: 16px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 50px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(4, 15, 36, 0.92);
  backdrop-filter: blur(14px);
  color: #C8DFF0;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.45);
  transition: all 0.2s ease;
}
.chart-toggle-btn:hover {
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  transform: translateY(-2px);
}
.chart-toggle-btn.active {
  background: rgba(0,212,168,0.15);
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  box-shadow: 0 0 20px rgba(0,212,168,0.2);
}
.chart-icon { font-size: 1rem; }

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
  background: rgba(4, 12, 28, 0.97);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0,212,168,0.2);
  border-radius: 22px;
  z-index: 2000;
  box-shadow: 0 24px 70px rgba(0,0,0,0.7), 0 0 0 1px rgba(0,212,168,0.05);
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

.leaflet-tile { image-rendering: auto; }

/* ─── Blue Dot Marker ───────────────────────────────────── */
:global(.blue-dot-marker) { position: relative; }
:global(.blue-dot) {
  width: 16px; height: 16px;
  background: #00D4A8;
  border: 3px solid white;
  border-radius: 50%;
  position: absolute; top: 4px; left: 4px;
  z-index: 2;
  box-shadow: 0 0 12px rgba(0,212,168,0.6);
}
:global(.pulse-ring) {
  width: 32px; height: 32px;
  background: rgba(0,212,168,0.25);
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
  .info-panel { left: 10px; bottom: 10px; max-width: calc(100% - 20px); }
  .location-btn { right: 136px; bottom: 14px; padding: 8px 14px; }
  .chart-toggle-btn { right: 10px; bottom: 14px; padding: 8px 14px; }
  .chart-panel { min-width: 90vw; width: 92vw; min-height: 55vh; }
}

@media (max-width: 480px) {
  .location-btn { right: 66px; padding: 9px; border-radius: 50%; }
  .location-text { display: none; }
  .chart-toggle-btn { right: 10px; padding: 9px; border-radius: 50%; }
  .chart-text { display: none; }
  .chart-icon, .location-icon { font-size: 1.2rem; margin: 0; }
  .chart-panel { min-width: 94vw; width: 94vw; top: 48%; }
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
  border-radius: 50px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(4, 15, 36, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.45);
  animation: dropdownFadeIn 0.18s ease;
}

.fw-label {
  font-size: 0.68rem;
  font-weight: 700;
  color: #4A6A8A;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
  padding-right: 6px;
  border-right: 1px solid rgba(255,255,255,0.08);
  margin-right: 4px;
}

.fw-btn {
  padding: 5px 11px;
  border-radius: 50px;
  border: 1px solid transparent;
  background: transparent;
  color: #6B8BAD;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  font-family: 'Space Grotesk', sans-serif;
  white-space: nowrap;
}
.fw-btn:hover {
  background: rgba(255,255,255,0.06);
  color: #C8DFF0;
}
.fw-btn.active {
  background: rgba(0,212,168,0.18);
  border-color: rgba(0,212,168,0.5);
  color: #00D4A8;
  box-shadow: 0 0 10px rgba(0,212,168,0.15);
}

.fc-label--active {
  color: #00D4A8 !important;
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

</style>