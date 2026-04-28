<template>
  <div class="wiki-root" :class="{ dark: isDark }">
    <div class="wiki-topbar">
      <div class="topbar-inner">
        <div class="brand" @click="$emit('home')">
          <button @click="$emit('home')" class="home-btn">🏠 Home</button>
          <span class="icon">🌾</span> <span class="brand-text">Irrigation crop Water Requirement</span>
          
        </div>
      </div>
    </div>

    <div class="wiki-layout">
      <aside class="wiki-sidebar">
        <div class="toc-box">
          <div class="toc-title">Contents</div>
          <ul class="toc-list">
            <li><a href="#overview">1 Overview</a></li>
            <li><a href="#methodology">2 Methodology</a>
              <ul>
                <li><a href="#data-sources">2.1 Data Sources & NDVI</a></li>
                <li><a href="#water-demand">2.2 ETc & Crop Demand</a></li>
                <li><a href="#forecasting">2.3 Analysis & Forecasting</a></li>
              </ul>
            </li>
            <li><a href="#insights">3 Key Insights & Data</a></li>
            <li><a href="#impact">4 Real-World Impact</a></li>
          </ul>
        </div>
      </aside>

      <main class="wiki-content">
        <h1 class="article-title">Irrigation Water Requirement</h1>
        
        <div class="article-meta">
          From AquaWatch Interactive Knowledge Base
        </div>

        <section id="overview">
          <p>
            <b>Irrigation Water Requirement (IWR)</b> estimation within the <strong>AquaWatch</strong> framework refers to the calculation of the precise volume of water that must be artificially supplied to crops. By systematically evaluating both crop-specific characteristics and dynamic atmospheric conditions, the platform aims to optimize agricultural water allocations and transition farmers away from generalized, traditional practices.
          </p>

          <div class="wiki-thumb right" style="width: 320px;">
            <div class="thumb-inner">
              <img src="/assets/about.png" alt="AquaWatch Platform" />
              <div class="thumbcaption">
                 The AquaWatch monitoring ecosystem integrates satellite and meteorological data to establish sustainable guidelines.
              </div>
            </div>
          </div>

          <p>
            The fundamental principle driving this system is the balance between total crop water demand (ETc) and effective precipitation (Pe). When combined, they yield the actual irrigation requirement—serving as a critical input for sustainable water resource management in regions like Udham Singh Nagar, Uttarakhand, where the Rabi wheat season is highly dependent on pumped groundwater.
          </p>
          
          <div class="formula-box">
            <span class="formula-title">Core Equation:</span>
            <div class="formula-math">
              <span class="text-blue">ET<sub>c</sub> (Crop Water Requirement)</span> − <span class="text-green">P<sub>e</sub> (Effective Rainfall)</span> = <span class="text-teal">IWR (Irrigation Water Requirement)</span>
            </div>
          </div>
        </section>

        <h2 id="methodology">Methodology</h2>
        <section id="data-sources">
          <h3>Data Sources & NDVI</h3>
          <div class="wiki-thumb left" style="width: 260px;">
            <div class="thumb-inner">
              <img src="/assets/barley.png" alt="Satellite imagery of fields" />
              <div class="thumbcaption">
                High-resolution Sentinel-2 multispectral imagery is used to identify actively cultivated agricultural land.
              </div>
            </div>
          </div>
          <p>
            The estimation of IWR is not a singular measurement but a sequential pipeline of satellite image processing, meteorological data ingestion, and predictive modeling.
            AquaWatch relies heavily on the European Space Agency's Sentinel-2 satellite imagery at a 10-meter spatial resolution. This imagery is primarily used for identifying crop boundaries and generating the Normalised Difference Vegetation Index (NDVI).
          </p>
          <p>
            Alongside Earth observation data, meteorological variables—specifically Potential Evapotranspiration (PET)—are acquired via the INSAT-3DR satellite system operated by ISRO. This dual-source approach continuously captures both ground reality and atmospheric evaporative forcing.
          </p>
        </section>

        <section id="water-demand">
          <h3>ETc & Crop Coefficients</h3>
          <div class="wiki-thumb right" style="width: 300px;">
            <div class="thumb-inner">
              <img src="../../dist/assets/kc.jpg"/>
              <div class="thumbcaption">
                Standard basal crop coefficient (Kc) evolution representing stages of a crop lifecycle.
              </div>
            </div>
          </div>

          <p>
            The calculation of ETc relies on the Food and Agriculture Organization's FAO-56 methodology: <code>ETc = Kc × ET₀</code>. Here, ET₀ represents the baseline reference evapotranspiration, while the crop coefficient (Kc) reflects local agricultural health.
          </p>
          <p>
            Rather than relying on static, generalized tables, the system derives Kc dynamically from time-series NDVI observations. This ensures the water demand profiles accurately match actual phenological stages mapped to individual plots. During peak growth phases like the "Heading" and "Grain Fill" stages, IWR typically scales to 3–6 mm/day.
          </p>
          <p>
            Next, effective rainfall (Pe) is assessed. If heavy precipitation events occur, Pe significantly lowers the final requirement. However, in low-rainfall Rabi seasons, precipitation offsets less than 20% of the requisite crop demand, meaning farmers bear the entire burden of irrigation management.
          </p>
        </section>

        <section id="forecasting">
          <h3>Analysis & Forecasting</h3>
          <p>
            Transforming descriptive analytics into operational intelligence requires prediction matrices. AquaWatch utilizes dual <strong>SARIMAX</strong> (Seasonal AutoRegressive Integrated Moving Average with eXogenous variables) grid models to forecast daily crop requirements 15 days in advance. Short-term tracking continuously recalibrates output weights to minimize localized errors—enabling robust support for canal authorities managing macro-level reservoirs.
          </p>
        </section>

        <h2 id="insights">Key Insights & Spatial Data</h2>
        <section>
          <div class="wiki-thumb right" style="width: 250px;">
            <div class="thumb-inner">
              <img src="/assets/cwr.jpeg" alt="Spatial crop water maps" />
              <div class="thumbcaption">
                 Spatial output mapping sub-district variation in real-time.
              </div>
            </div>
          </div>
          <p>
            Analyzing granular grid data from the Udham Singh Nagar district yields significant geospatial discoveries:
          </p>
          <ul>
            <li><b>Stage-Dependent Fluctuation:</b> Growth spikes drastically adjust daily irrigation requirements. Predictability models indicate demand surges precisely between days 76 and 135 post-sowing.</li>
            <li><b>Sub-Regional Disparities:</b> Maps consistently highlight 1–2 mm/day differences between immediately adjacent plots due to staggered planting schedules and differing soil drainage topologies.</li>
            <li><b>Satellite Congruence:</b> NDVI-derived crop consumption data structurally aligns with localized ground-truth metering, verifying orbital telemetry as scalable alternatives to physical hardware grids.</li>
          </ul>
        </section>

        <h2 id="impact">Real-World Impact & Policy</h2>
        <section>
          <div class="wiki-thumb left" style="width: 280px;">
            <div class="thumb-inner">
              <img src="/assets/wheat.png" alt="Healthy wheat crop" />
              <div class="thumbcaption">
                Optimal precision watering prevents degradation of soil profiles and maximizes crop yields.
              </div>
            </div>
          </div>
          <p>
            Modernizing agricultural frameworks transitions farmers towards precision guidance, replacing historical intuition methodologies. In active zones, forecasting outputs translate directly to hardware pump timing: calculating a 4 mm daily deficit demands 20 mm replenishment per standard 5-day cycle.
          </p>
          <p>
            Economically and environmentally, systematic application protocols radically curtail over-irrigation side effects. Phenomena including nitrogen fertilizer leaching, extensive surface waterlogging, and irreversible aquifer salination scale proportionally with excess pumping. Quantifications suggest implementing satellite advisories locally reduces groundwater abstraction volumes by 10 to 15%, conserving energy expenditure alongside deep-earth aquifers.
          </p>
        </section>

      </main>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['launch', 'home'])
const currentView = ref('home')
// Maintain state for the background theme. Start in light mode for the Wiki theme by default.
const isDark = ref(false)

function showHome() {
  emit('home')
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=Inter:wght@400;500;600;700&display=swap');

/* Main Theme Variables */
.wiki-root {
  --bg-site: #f8f9fa;
  --bg-surface: #ffffff;
  --border-subtle: #eaecf0;
  --border-strong: #a2a9b1;
  --text-main: #202122;
  --text-muted: #54595d;
  --link-color: #3366cc;
  --accent-teal: #0d9488;
  --thumb-bg: #f8f9fa;
  
  font-family: 'Inter', sans-serif;
  background: var(--bg-site);
  color: var(--text-main);
  min-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 80px;
  transition: background 0.3s, color 0.3s;
}

.wiki-root.dark {
  --bg-site: #0d1117;
  --bg-surface: #161b22;
  --border-subtle: #30363d;
  --border-strong: #484f58;
  --text-main: #e6edf3;
  --text-muted: #8b949e;
  --link-color: #58a6ff;
  --accent-teal: #14b8a6;
  --thumb-bg: #0d1117;
}

/* Scroll Behavior for internal links */
html {
  scroll-behavior: smooth;
}

/* TOPBAR */
.wiki-topbar {
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky; top: 0; z-index: 100;
  padding: 12px 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.02);
  transition: background 0.3s;
}
.topbar-inner {
  max-width: 1300px; margin: 0 auto;
  display: flex; justify-content: space-between; align-items: center;
}
.brand {
  font-weight: 700; font-size: 1.25rem; display: flex; align-items: center; gap: 8px;
  cursor: pointer;
}
.brand-text { font-family: 'Lora', serif; font-style: italic; }
.brand .icon { font-size: 1.5rem; }

.controls { display: flex; gap: 12px; align-items: center; }
.btn-launch, .btn-theme {
  padding: 8px 16px; border-radius: 4px; font-size: 0.85rem; font-weight: 600;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn-theme { background: var(--bg-site); color: var(--text-main); border: 1px solid var(--border-strong); }
.btn-launch { background: var(--link-color); color: #fff; }
.btn-theme:hover { background: var(--border-subtle); }
.btn-launch:hover { opacity: 0.9; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }

/* LAYOUT */
.wiki-layout {
  max-width: 1240px; margin: 40px auto 0;
  display: grid; grid-template-columns: 240px 1fr; gap: 56px;
  padding: 0 24px;
}

/* SIDEBAR & TOC */
.wiki-sidebar { position: relative; }
.toc-box {
  background: var(--bg-site);
  border: 1px solid var(--border-strong);
  padding: 20px;
  position: sticky; top: 90px;
  border-radius: 2px;
  box-shadow: 1px 1px 3px rgba(0,0,0,0.03);
}
.wiki-root.dark .toc-box { box-shadow: none; }
.toc-title {
  font-weight: 700; border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 10px; margin-bottom: 14px; font-size: 1rem;
}
.toc-list { list-style: none; padding: 0; margin: 0; font-size: 0.9rem; }
.toc-list li { margin-bottom: 10px; }
.toc-list ul { list-style: none; padding-left: 20px; margin-top: 10px; }
.toc-list a { color: var(--link-color); text-decoration: none; }
.toc-list a:hover { text-decoration: underline; }

/* ARTICLE CONTENT */
.wiki-content {
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  padding: 60px 72px;
  border-radius: 2px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.04);
  max-width: 100%;
  overflow: visible;
}
.wiki-root.dark .wiki-content { box-shadow: 0 2px 10px rgba(0,0,0,0.2); }

.article-title {
  font-family: 'Lora', serif;
  font-size: 2.6rem; font-weight: 600;
  border-bottom: 1px solid var(--border-strong);
  padding-bottom: 12px; margin: 0 0 8px;
  line-height: 1.2;
}
.article-meta {
  font-size: 0.85rem; color: var(--text-muted);
  margin-bottom: 36px; padding-bottom: 16px;
  border-bottom: 1px dashed var(--border-subtle);
}

.wiki-content section { margin-bottom: 32px; }

.wiki-content h2 {
  font-family: 'Lora', serif; font-size: 1.8rem; font-weight: 500;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 8px; margin: 48px 0 20px;
}
.wiki-content h3 {
  font-family: 'Inter', sans-serif; font-size: 1.25rem; font-weight: 600;
  margin: 32px 0 16px;
}
.wiki-content p {
  font-size: 1rem; line-height: 1.7; margin-bottom: 18px; color: var(--text-main);
  text-align: justify;
}
.wiki-content ul {
  line-height: 1.7; margin-bottom: 24px; padding-left: 28px;
}
.wiki-content li { margin-bottom: 10px; }

/* THUMBNAILS (Images) */
.wiki-thumb {
  border: 1px solid var(--border-strong);
  background: var(--thumb-bg);
  padding: 6px; margin-bottom: 20px;
}
.wiki-thumb.right { float: right; margin-left: 32px; }
.wiki-thumb.left  { float: left; margin-right: 32px; }
.thumb-inner img {
  width: 100%; height: auto; display: block; border: 1px solid var(--border-subtle);
}
.thumbcaption {
  font-size: 0.8rem; line-height: 1.45; color: var(--text-muted);
  margin-top: 10px; padding: 0 4px;
}

/* SPECIAL ELEMENTS */
.formula-box {
  background: var(--bg-site); border-left: 4px solid var(--accent-teal);
  padding: 18px 24px; margin: 32px 0; font-family: monospace;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.02);
}
.formula-title { display: block; font-weight: 700; margin-bottom: 10px; color: var(--text-muted); font-family: 'Inter', sans-serif;}
.formula-math { font-size: 1.25rem; }
.text-blue { color: #2563eb; }
.text-green { color: #16a34a; }
.text-teal { color: var(--accent-teal); font-weight: bold; }
.wiki-root.dark .text-blue { color: #60a5fa; }
.wiki-root.dark .text-green { color: #4ade80; }

code {
  background: var(--bg-site); border: 1px solid var(--border-subtle);
  padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em;
  color: var(--link-color);
}

/* RESPONSIVE */
@media (max-width: 1024px) {
  .wiki-content { padding: 48px; }
}
@media (max-width: 900px) {
  .wiki-layout { grid-template-columns: 1fr; gap: 32px; }
  .toc-box { position: relative; top: 0; }
  .wiki-content { padding: 32px 24px; }
  .wiki-thumb.right, .wiki-thumb.left { float: none; width: 100% !important; margin: 24px 0; }
  .article-title { font-size: 2rem; }
}

.home-btn {
  padding:6px 16px; border-radius:10px; font-size:0.8rem;
  font-family:'JetBrains Mono',monospace; font-weight:500;
  color:#6B8BAD; background:transparent; border:1px solid transparent;
  cursor:pointer; transition:all 0.2s; white-space:nowrap;
}
.home-btn:hover { color: var(--accent-teal-glow); border-color: var(--accent-teal-glow-30); background: var(--accent-teal-glow-10); }
</style>