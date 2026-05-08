<!-- DOCsView.vue -->
<template>
  <div class="wiki-root" :class="{ dark: isDark }">
    <!-- ══════════════════ HEADER (matches Home.vue style) ══════════════════ -->
    <header class="app-header">
      <div class="app-header-inner">
        <div class="header-logos">
          <img src="/assets/iirs.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/isro.png" class="iirs-logo" onerror="this.style.display='none'" />
        </div>
        <div class="header-center">
          <h2>भारतीय अंतरिक्ष अनुसंधान संगठन, अंतरिक्ष विभाग</h2>
          <h3>Indian Space Research Organisation, Department of Space</h3>
          <h4>भारत सरकार / Government of India</h4>
        </div>
        <div class="header-logos header-logos-right">
          <img src="/assets/india.png" class="gov-logo" onerror="this.style.display='none'" />
        </div>
      </div>
    </header>

    <!-- ══════════════════ NAV BAR ══════════════════ -->
    <nav class="nav-bar">
      <div class="nav-inner">
        <div class="nav-links">
          <button @click="$emit('home')" class="nav-link home-nav-link">
            <span class="home-icon">🏠</span> Home
          </button>
        </div>
        <button class="mobile-menu-btn" @click="mobileOpen = !mobileOpen">
          <span></span><span></span><span></span>
        </button>
      </div>
      <div class="mobile-dropdown" :class="{ open: mobileOpen }">
        <button @click="$emit('home'); mobileOpen=false" class="mobile-link">🏠 Home</button>
      </div>
    </nav>

    <!-- ══════════════════ MAIN CONTENT ══════════════════ -->
    <div class="wiki-layout">
      <aside class="wiki-sidebar">
        <div class="toc-box">
          <div class="toc-title">Contents</div>
          <ul class="toc-list">
            <li><a href="#overview" @click.prevent="scrollTo('overview')">1. Overview</a></li>
            <li><a href="#methodology" @click.prevent="scrollTo('methodology')">2. Methodology</a>
              <ul>
                <li><a href="#data-sources" @click.prevent="scrollTo('data-sources')">2.1 Data Sources & NDVI</a></li>
                <li><a href="#water-demand" @click.prevent="scrollTo('water-demand')">2.2 ETc & Crop Demand</a></li>
                <li><a href="#forecasting" @click.prevent="scrollTo('forecasting')">2.3 Analysis & Forecasting</a></li>
              </ul>
            </li>
            <li><a href="#insights" @click.prevent="scrollTo('insights')">3. Key Insights & Data</a></li>
            <li><a href="#impact" @click.prevent="scrollTo('impact')">4. Real-World Impact</a></li>
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
            <strong>Irrigation Water Requirement (IWR)</strong> estimation within the <strong>AquaWatch</strong> framework refers to the calculation of the precise volume of water that must be artificially supplied to crops. By systematically evaluating both crop-specific characteristics and dynamic atmospheric conditions, the platform aims to optimize agricultural water allocations and transition farmers away from generalized, traditional practices.
          </p>

          <div class="wiki-thumb right">
            <div class="thumb-inner">
              <img src="/assets/about.png" alt="AquaWatch Platform" />
              <div class="thumbcaption">
                The AquaWatch monitoring ecosystem integrates satellite and meteorological data.
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
          <div class="wiki-thumb left">
            <div class="thumb-inner">
              <img src="/assets/barley.png" alt="Satellite imagery of fields" />
              <div class="thumbcaption">
                High-resolution Sentinel-2 multispectral imagery is used to identify actively cultivated agricultural land.
              </div>
            </div>
          </div>
          <p>
            The estimation of IWR is not a singular measurement but a sequential pipeline of satellite image processing, meteorological data ingestion, and predictive modeling. AquaWatch relies heavily on the European Space Agency's Sentinel-2 satellite imagery at a 10-meter spatial resolution. This imagery is primarily used for identifying crop boundaries and generating the Normalised Difference Vegetation Index (NDVI).
          </p>
          <p>
            Alongside Earth observation data, meteorological variables—specifically Potential Evapotranspiration (PET)—are acquired via the INSAT-3DR satellite system operated by ISRO. This dual-source approach continuously captures both ground reality and atmospheric evaporative forcing.
          </p>
        </section>

        <section id="water-demand">
          <h3>ETc & Crop Coefficients</h3>
          <div class="wiki-thumb right">
            <div class="thumb-inner">
              <img src="/assets/kc.jpg" alt="Crop coefficient curve" />
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
          <div class="wiki-thumb right">
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
            <li><strong>Stage-Dependent Fluctuation:</strong> Growth spikes drastically adjust daily irrigation requirements. Predictability models indicate demand surges precisely between days 76 and 135 post-sowing.</li>
            <li><strong>Sub-Regional Disparities:</strong> Maps consistently highlight 1–2 mm/day differences between immediately adjacent plots due to staggered planting schedules and differing soil drainage topologies.</li>
            <li><strong>Satellite Congruence:</strong> NDVI-derived crop consumption data structurally aligns with localized ground-truth metering, verifying orbital telemetry as scalable alternatives to physical hardware grids.</li>
          </ul>
        </section>

        <h2 id="impact">Real-World Impact & Policy</h2>
        <section>
          <div class="wiki-thumb left">
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

    <!-- ══════════════════ FOOTER (matches Home.vue style) ══════════════════ -->
    <footer class="site-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span></span>
          <div>
            <p class="fb-name">&nbsp;·&nbsp; Irrigation Water Requirements</p>
            <p class="fb-sub">ISRO &nbsp;·&nbsp; IIRS &nbsp;·&nbsp; Department of Space, Govt. of India</p>
          </div>
        </div>
        
        <div class="footer-links-col">
          <p class="fc">Udham Singh Nagar · Uttarakhand · Rabi Wheat</p>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  isDark: { type: Boolean, default: true }
})

const emit = defineEmits(['home', 'launch'])
const mobileOpen = ref(false)

function scrollTo(id) {
  const el = document.getElementById(id)
  if (!el) return
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 100, behavior: 'smooth' })
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

/* ──────────────────────────────────────────────────────────────────────
   THEME SYSTEM (matches Home.vue)
   ────────────────────────────────────────────────────────────────────── */
.wiki-root {
  /* DARK THEME */
  --bg-primary: #040814;
  --bg-secondary: #0A1128;
  --bg-tertiary: #131E3A;
  --surface: rgba(19, 30, 58, 0.4);
  --border: rgba(0, 212, 168, 0.15);
  --border-light: rgba(255,255,255,0.04);
  
  --text-primary: #F8FAFC;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  
  --accent-teal: #00D4A8;
  --accent-teal-glow: rgba(0, 212, 168, 0.15);
  --accent-amber: #FDE047;
  --accent-blue: #3B82F6;
  
  --card-bg: rgba(30, 41, 59, 0.5);
  --header-bg: #1A4A6B;
  --header-text: #FFFFFF;
  --nav-bg: #009688;
  --nav-text: #FFFFFF;

  font-family: 'Inter', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: background 0.4s ease, color 0.4s ease;
  min-height: 100vh;
  overflow-x: hidden;
}

/* LIGHT THEME OVERRIDES */
.wiki-root:not(.dark) {
  --bg-primary: #F8FAFC;
  --bg-secondary: #F1F5F9;
  --bg-tertiary: #E2E8F0;
  --surface: #FFFFFF;
  --border: rgba(0, 0, 0, 0.08);
  --border-light: rgba(0, 0, 0, 0.05);
  
  --text-primary: #0F172A;
  --text-secondary: #334155;
  --text-muted: #64748B;
  
  --accent-teal: #0D9488;
  --accent-teal-glow: rgba(13, 148, 136, 0.18);
  --accent-amber: #D97706;
  --accent-blue: #2563EB;
  
  --card-bg: rgba(255, 255, 255, 0.85);
  --header-bg: #F8FAFC;
  --header-text: #0F172A;
  --nav-bg: #FFFFFF;
  --nav-text: #0D9488;
}

/* ──────────────────────────────────────────────────────────────────────
   HEADER (copied from Home.vue)
   ────────────────────────────────────────────────────────────────────── */
.app-header {
  position: relative;
  background: var(--header-bg);
  border-bottom: 1px solid rgba(0, 0, 0, 0.18);
  padding: 14px 24px;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.25);
  transition: background 0.4s ease;
}

.app-header-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
}

.header-logos, .header-logos-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-logos-right {
  justify-content: flex-end;
}

.iirs-logo, .gov-logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  transition: transform 0.3s ease;
}
.iirs-logo:hover, .gov-logo:hover {
  transform: scale(1.05);
}

.gov-logo {
  height: 60px;
}

.header-center {
  flex: 1;
  text-align: center;
  padding: 0 8px;
}
.header-center h2 {
  font-family: 'Outfit', sans-serif;
  font-size: clamp(1.1rem, 2vw, 1.5rem);
  font-weight: 800;
  color: var(--header-text);
  margin: 0 0 4px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.header-center h3 {
  font-size: clamp(1.0rem, 1.6vw, 1.15rem);
  color: var(--header-text);
  opacity: 0.9;
  font-weight: 500;
  margin: 0 0 2px;
}
.header-center h4 {
  font-size: clamp(0.8rem, 1.3vw, 0.95rem);
  color: var(--header-text);
  opacity: 0.75;
  font-weight: 400;
  margin: 0;
}

/* ──────────────────────────────────────────────────────────────────────
   NAVIGATION (copied from Home.vue)
   ────────────────────────────────────────────────────────────────────── */
.nav-bar {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--nav-bg);
  border-bottom: 2px solid rgba(0, 0, 0, 0.15);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.20);
  transition: background 0.4s ease;
}

.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  color: var(--nav-text);
  text-decoration: none;
  padding: 8px 20px;
  border-radius: 6px;
  transition: all 0.2s ease;
  font-weight: 600;
  letter-spacing: 0.04em;
  background: none;
  border: none;
  cursor: pointer;
  font-family: 'Inter', sans-serif;
}

.home-icon {
  font-size: 1rem;
}

.nav-link::after {
  content: '';
  position: absolute;
  bottom: 4px;
  left: 50%;
  width: 0%;
  height: 2px;
  background: var(--nav-text);
  transition: all 0.3s ease;
  transform: translateX(-50%);
  border-radius: 2px;
}

.nav-link {
  position: relative;
}

.nav-link:hover {
  background: rgba(255,255,255,0.18);
  color: #FFFFFF;
}
.nav-link:hover::after {
  width: 70%;
}

.mobile-menu-btn {
  display: none;
  flex-direction: column;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  margin-left: auto;
}
.mobile-menu-btn span {
  display: block;
  width: 24px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 2px;
  transition: 0.3s;
}

.mobile-dropdown {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.4s ease;
  display: flex;
  flex-direction: column;
  padding: 0 24px;
  border-top: 1px solid transparent;
  background: var(--surface);
}
.mobile-dropdown.open {
  max-height: 400px;
  padding: 16px 24px;
  border-top-color: var(--border);
}
.mobile-link {
  padding: 12px 0;
  font-size: 1rem;
  color: var(--text-primary);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  font-weight: 500;
}

/* ──────────────────────────────────────────────────────────────────────
   DOCS LAYOUT (Professional - Adobe/Starbucks style)
   ────────────────────────────────────────────────────────────────────── */
.wiki-layout {
  max-width: 1280px;
  margin: 60px auto;
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 48px;
  padding: 0 24px;
}

/* Sidebar TOC - Glass card style */
.toc-box {
  background: var(--surface);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 28px 24px;
  position: sticky;
  top: 100px;
  transition: all 0.3s ease;
}

.toc-title {
  font-family: 'Outfit', sans-serif;
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--accent-teal);
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border);
  letter-spacing: -0.01em;
}

.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-list li {
  margin-bottom: 12px;
}

.toc-list ul {
  list-style: none;
  padding-left: 20px;
  margin-top: 8px;
}

.toc-list a {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.2s ease;
  display: block;
  padding: 6px 12px;
  border-radius: 12px;
  cursor: pointer;
}

.toc-list a:hover {
  color: var(--accent-teal);
  background: var(--accent-teal-glow);
  transform: translateX(4px);
}

/* Main Content */
.wiki-content {
  background: var(--surface);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: 32px;
  padding: 48px 56px;
  transition: all 0.3s ease;
}

.article-title {
  font-family: 'Outfit', sans-serif;
  font-size: 2.8rem;
  font-weight: 800;
  background: linear-gradient(135deg, var(--accent-teal), var(--accent-blue));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
}

.article-meta {
  font-size: 0.9rem;
  color: var(--text-muted);
  padding-bottom: 24px;
  margin-bottom: 32px;
  border-bottom: 1px solid var(--border);
}

.wiki-content section {
  margin-bottom: 40px;
}

.wiki-content p {
  font-size: 1rem;
  line-height: 1.7;
  margin-bottom: 20px;
  color: var(--text-secondary);
}

.wiki-content strong {
  color: var(--accent-teal);
  font-weight: 600;
}

.wiki-content ul {
  line-height: 1.7;
  margin-bottom: 24px;
  padding-left: 24px;
}

.wiki-content li {
  margin-bottom: 10px;
  color: var(--text-secondary);
}

.wiki-content h2 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.8rem;
  font-weight: 700;
  margin: 48px 0 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--accent-teal);
  display: inline-block;
  letter-spacing: -0.01em;
}

.wiki-content h3 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.3rem;
  font-weight: 600;
  margin: 32px 0 16px;
  color: var(--accent-teal);
  letter-spacing: -0.01em;
}

/* Thumbnails */
.wiki-thumb {
  border: 1px solid var(--border);
  background: var(--bg-tertiary);
  border-radius: 20px;
  padding: 8px;
  margin-bottom: 24px;
  width: 280px;
}

.wiki-thumb.right {
  float: right;
  margin-left: 32px;
}

.wiki-thumb.left {
  float: left;
  margin-right: 32px;
}

.thumb-inner img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 12px;
}

.thumbcaption {
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--text-muted);
  margin-top: 10px;
  padding: 0 8px;
  text-align: center;
}

/* Formula Box */
.formula-box {
  background: var(--accent-teal-glow);
  border-left: 4px solid var(--accent-teal);
  border-radius: 16px;
  padding: 20px 28px;
  margin: 32px 0;
  font-family: 'JetBrains Mono', monospace;
}

.formula-title {
  display: block;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text-muted);
  font-family: 'Inter', sans-serif;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.formula-math {
  font-size: 1.2rem;
  font-weight: 500;
}

.text-blue {
  color: var(--accent-blue);
}

.text-green {
  color: var(--accent-amber);
}

.text-teal {
  color: var(--accent-teal);
  font-weight: bold;
}

code {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--accent-teal);
}

/* Clear floats */
.wiki-content::after {
  content: "";
  display: table;
  clear: both;
}

/* ──────────────────────────────────────────────────────────────────────
   FOOTER (copied from Home.vue)
   ────────────────────────────────────────────────────────────────────── */
.site-footer {
  position: relative;
  background: #070808;
  border-top: 1px solid var(--border);
  padding: 10px 24px 40px;
  margin-top: 60px;
}
.wiki-root:not(.dark) .site-footer {
  background: #f1f5f9;
}
.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 32px;
}
.footer-brand {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 1.8rem;
}
.fb-name {
  font-weight: 700;
  font-family: 'Outfit', sans-serif;
  font-size: 1.25rem;
  color: var(--text-primary);
  margin: 0 0 6px;
  letter-spacing: 0.05em;
}
.fb-sub {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin: 0;
}
.footer-tech {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 460px;
}
.ft-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 50px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 0.75rem;
  color: var(--text-secondary);
  white-space: nowrap;
  transition: all 0.2s ease;
}
.ft-badge:hover {
  border-color: var(--accent-teal);
  color: var(--accent-teal);
  transform: translateY(-2px);
}
.footer-links-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}
.fc {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
}

/* ──────────────────────────────────────────────────────────────────────
   RESPONSIVE
   ────────────────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .wiki-layout {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .toc-box {
    position: relative;
    top: 0;
  }
  .wiki-content {
    padding: 32px 28px;
  }
  .wiki-thumb.right,
  .wiki-thumb.left {
    float: none;
    width: 100%;
    max-width: 320px;
    margin: 24px auto;
  }
}

@media (max-width: 768px) {
  .nav-links {
    display: none;
  }
  .mobile-menu-btn {
    display: flex;
  }
  .header-logos {
    min-width: 80px;
  }
  .iirs-logo {
    height: 55px;
  }
  .gov-logo {
    height: 55px;
  }
  .footer-links-col {
    align-items: flex-start;
  }
  .article-title {
    font-size: 2rem;
  }
  .wiki-content h2 {
    font-size: 1.4rem;
  }
  .wiki-content h3 {
    font-size: 1.1rem;
  }
}

@media (max-width: 480px) {
  .app-header-inner {
    grid-template-columns: 1fr;
    text-align: center;
    gap: 12px;
  }
  .header-logos, .header-logos-right {
    justify-content: center;
  }
  .iirs-logo {
    height: 40px;
  }
  .gov-logo {
    height: 36px;
  }
  .footer-inner {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .footer-links-col {
    align-items: center;
  }
  .wiki-content {
    padding: 24px 20px;
  }
  .formula-math {
    font-size: 0.9rem;
  }
}
</style>