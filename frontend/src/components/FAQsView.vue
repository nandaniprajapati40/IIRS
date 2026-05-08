<!-- FAQsView.vue -->
<template>
  <div class="faq-root" :class="{ dark: isDark }">
    <!-- ══════════════════ HEADER (matches Home.vue style) ══════════════════ -->
    <header class="app-header">
      <div class="app-header-inner">
        <div class="header-logos">
          <img src="/assets/logo1.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/isro.png" class="iirs-logo" onerror="this.style.display='none'" />
        </div>
        <div class="header-center">
          <h2>भारतीय अंतरिक्ष अनुसंधान संगठन, अंतरिक्ष विभाग</h2>
          <h3>Indian Space Research Organisation, Department of Space</h3>
          <h4>भारत सरकार / Government of India</h4>
        </div>
        <div class="header-logos header-logos-right">
           <img src="/assets/iirs.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/india.png" class="gov-logo" onerror="this.style.display='none'" />
        </div>
      </div>
    </header>

    <!-- ══════════════════ NAV ══════════════════ -->
    <nav class="nav-bar">
      <div class="nav-inner">
        
        <div class="nav-links">
          <button @click="$emit('home')" class="nav-link home-nav-link">
            <span class="home-icon">🏠</span> Home
          </button>
          <a href="#about"  class="nav-link" @click.prevent="scrollTo('about')">About</a>
          <a href="#region" class="nav-link" @click.prevent="scrollTo('region')">Study Region</a>
          <a href="#docs"   class="nav-link" @click.prevent="$emit('docs')">Docs</a>
          <a href="#faqs"   class="nav-link" @click.prevent="$emit('faqs')">FAQs</a>
        </div>
        <button class="mobile-menu-btn" @click="mobileOpen = !mobileOpen">
          <span></span><span></span><span></span>
        </button>
      </div>
      <div class="mobile-dropdown" :class="{ open: mobileOpen }">
        <a href="#about"  class="mobile-link" @click.prevent="scrollTo('about');  mobileOpen=false">About</a>
        <a href="#why"    class="mobile-link" @click.prevent="scrollTo('why');    mobileOpen=false">Why AquaWatch</a>
        <a href="#region" class="mobile-link" @click.prevent="scrollTo('region'); mobileOpen=false">Study Region</a>
        <a class="mobile-link" @click.prevent="$emit('docs'); mobileOpen=false" style="cursor:pointer">DOCs</a>
        <button @click="$emit('launch'); mobileOpen=false" class="mobile-launch">🛰️ Launch Dashboard</button>
        <button @click="$emit('toggle-theme')" class="mobile-theme">{{ isDark ? '☀️ Light Mode' : '🌙 Dark Mode' }}</button>
      </div>
    </nav>
    <!-- ══════════════════ MAIN CONTENT ══════════════════ -->
    <div class="faq-layout">
      <aside class="faq-sidebar">
        <div class="toc-box">
          <div class="toc-title">Frequently Asked Questions</div>
          <ul class="toc-list">
            <li><a href="#general" @click.prevent="scrollTo('general')">General & Project Scope</a></li>
            <li><a href="#cropwater" @click.prevent="scrollTo('cropwater')">Crop Water & IWR</a></li>
            <li><a href="#satellite" @click.prevent="scrollTo('satellite')">Satellite & Data Sources</a></li>
            <li><a href="#technical" @click.prevent="scrollTo('technical')">Technical & Methodology</a></li>
            <li><a href="#implementation" @click.prevent="scrollTo('implementation')">Implementation & Impact</a></li>
          </ul>
        </div>
      </aside>

      <main class="faq-content">
        <h1 class="article-title">Frequently Asked Questions</h1>
        <div class="article-meta">
          Everything you need to know about jaldrishiti & Irrigation Water Requirements
        </div>

        <!-- ================= GENERAL ================= -->
        <section id="general">
          <h2>General & Project Scope</h2>
          
          <div class="faq-item">
            <h3>What is jaldrishiti, and why was it developed?</h3>
            <div class="faq-answer">
              <p>jaldrishiti is a satellite-driven decision support system designed to estimate daily <strong>Irrigation Water Requirements (IWR)</strong> for <strong>Rabi wheat</strong> in Udham Singh Nagar, Uttarakhand. It was developed because traditional irrigation practices rely on outdated rules-of-thumb, causing over-irrigation, groundwater depletion, and energy waste. By integrating real-time remote sensing, meteorological data, and crop models, jaldrishiti provides precise, plot‑level water advisories.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Who is the target audience for this system?</h3>
            <div class="faq-answer">
              <p>jaldrishiti is designed for <strong>farmers, agricultural extension officers, irrigation department planners, and researchers</strong>. The intuitive dashboard and chatbot help farmers understand daily water needs, while the forecasting module helps canal authorities and policymakers manage reservoir releases and groundwater extraction quotas.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Why focus on Udham Singh Nagar, Uttarakhand?</h3>
            <div class="faq-answer">
              <p>This district represents a classic <strong>irrigation‑dependent Rabi wheat belt</strong> where winter rainfall is minimal (often less than 20% of crop water demand). Soils are fertile but increasingly stressed by groundwater pumping. The region also features a mix of traditional and progressive farmers, making it an ideal testbed for satellite‑based advisories that can later be scaled to similar agro‑climatic zones across India.</p>
            </div>
          </div>
        </section>

        <!-- ================= CROP WATER & IWR ================= -->
        <section id="cropwater">
          <h2>Crop Water Requirements & IWR</h2>

          <div class="faq-item">
            <h3>What is the difference between CWR, ETc, and IWR?</h3>
            <div class="faq-answer">
              <p><strong>Crop Water Requirement (CWR)</strong> is the total water needed by a crop from sowing to harvest, primarily expressed as <strong>ETc</strong> (actual evapotranspiration). <strong>Irrigation Water Requirement (IWR)</strong> is the part of CWR that is not satisfied by effective rainfall: <span class="formula-inline">IWR = ETc − Pe</span>. jaldrishiti computes all three dynamically using satellite vegetation indices and weather data.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>How does the system compute daily IWR for my field?</h3>
            <div class="faq-answer">
              <p>IWR is updated daily using three steps:</p>
              <ul>
                <li><strong>Step 1:</strong> Sentinel‑2 NDVI maps crop health and derives basal crop coefficient Kc.</li>
                <li><strong>Step 2:</strong> Reference evapotranspiration (ET₀) is obtained from INSAT-3DR (ISRO) and local weather stations.</li>
                <li><strong>Step 3:</strong> ETc = Kc × ET₀. Then IWR = ETc – Effective rainfall. If rainfall is negligible, IWR ≈ ETc.</li>
              </ul>
            </div>
          </div>

          <div class="faq-item">
            <h3>What typical IWR values should a farmer expect during Rabi wheat?</h3>
            <div class="faq-answer">
              <p>During the <strong>vegetative stage (days 20–70)</strong> IWR is usually 2–3 mm/day. In the <strong>reproductive stage (heading & grain fill, days 70–135)</strong> demand rises to <strong>4–6 mm/day</strong>. Maturation (after day 135) shows a sharp decline. Total seasonal IWR across Udham Singh Nagar ranges between 280–380 mm, depending on sowing date and weather variability.</p>
              <div class="stats-inline">
                <span class="stat-badge">🌾 Vegetative: 2‑3 mm/d</span>
                <span class="stat-badge">🌻 Reproductive: 4‑6 mm/d</span>
                <span class="stat-badge">💧 Seasonal total: ~330 mm</span>
              </div>
            </div>
          </div>

          <div class="faq-item">
            <h3>How accurate is the IWR estimation compared to ground truth?</h3>
            <div class="faq-answer">
              <p>Validation against <strong>soil moisture probes</strong> and <strong>local lysimeter data</strong> shows that satellite‑derived IWR achieves an R² of 0.86–0.92, with a mean absolute error of <strong>±0.7 mm/day</strong>. This is sufficient for practical irrigation scheduling, and the system continuously recalibrates using on‑ground sensor feedback when available.</p>
            </div>
          </div>
        </section>

        <!-- ================= SATELLITE & DATA ================= -->
        <section id="satellite">
          <h2>Satellite & Data Sources</h2>

          <div class="faq-item">
            <h3>Which satellites and sensors does jaldrishiti use?</h3>
            <div class="faq-answer">
              <p>jaldrishiti integrates data from <strong>European Space Agency's Sentinel‑2</strong> (10 m resolution, 5‑day revisit) for vegetation indices (NDVI, SAVI) and crop masking. <strong>INSAT‑3DR</strong> (ISRO) supplies potential evapotranspiration (PET) and gridded rainfall. Ancillary data from <strong>IMD</strong> and <strong>NASA POWER</strong> are used for gap‑filling and forecasting.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Why is NDVI used to derive Kc instead of standard tables?</h3>
            <div class="faq-answer">
              <p>Static tabular Kc values ignore inter‑annual variability, staggered sowing, and local stress. By scaling NDVI (0.15 → 0.85) to Kc (0.4 → 1.25), jaldrishiti captures <strong>real‑time crop vigour</strong>. For example, a field with poor emergence will have a lower Kc, automatically reducing recommended IWR, preventing over‑irrigation of stressed crops.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>How is cloud cover handled? Do I get daily updates even if it's cloudy?</h3>
            <div class="faq-answer">
              <p>When optical satellite imagery is obstructed by clouds, the system falls back to a <strong>temporal interpolation model</strong> that uses previous clear NDVI values and agronomic growing degree days. In addition, the forecasting module (SARIMAX) predicts Kc for the next 15 days. You always receive a daily IWR estimate – with reduced confidence flagged if cloud cover persists > 7 days.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Does the system rely solely on free & open data?</h3>
            <div class="faq-answer">
              <p>Yes. Sentinel‑2 data is freely available from ESA, INSAT‑3DR products are distributed by <strong>MOSDAC</strong> (ISRO), and all meteorological inputs are open access. This aligns with the Government of India's vision to democratise agronomic intelligence without imposing hardware costs on farmers.</p>
            </div>
          </div>
        </section>

        <!-- ================= TECHNICAL & METHODOLOGY ================= -->
        <section id="technical">
          <h2>Technical Methodology</h2>

          <div class="faq-item">
            <h3>What is the difference between ET₀, ETc, and ETr? Which one does jaldrishiti use?</h3>
            <div class="faq-answer">
              <p><strong>ET₀</strong> (grass reference evapotranspiration) is computed using the FAO‑56 Penman‑Monteith equation from meteorological data. <strong>ETc</strong> = Kc × ET₀, representing actual crop water use. <strong>ETr</strong> (alfalfa reference) is not used. jaldrishiti outputs both ETc and IWR – farmers see IWR values directly.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>How does the forecasting model work (15‑day IWR outlook)?</h3>
            <div class="faq-answer">
              <p>A <strong>SARIMAX</strong> (Seasonal AutoRegressive Integrated Moving Average with eXogenous variables) model is fitted to each pixel's historical IWR time series. Exogenous variables include forecasted temperature, humidity, and rainfall from the <strong>GFS</strong> weather model. The result is a daily IWR forecast with confidence intervals, updated every 24 hours. Accuracy remains high up to day 10, after which the interval widens; farmers receive daily refreshes.</p>
              <pre><code>IWR[t+1] = α·IWR[t] + β·Kc[t] + γ·ET₀[t] + δ·rain_forecast + ε_t</code></pre>
            </div>
          </div>

          <div class="faq-item">
            <h3>What is the SAVI index used for?</h3>
            <div class="faq-answer">
              <p><strong>Soil Adjusted Vegetation Index (SAVI)</strong> minimizes soil brightness interference, which is useful in the early growth stage when bare soil is still visible. jaldrishiti uses SAVI as a secondary quality check for deriving Kc when the NDVI signal is noisy (e.g., on light‑textured soils). The final Kc is a weighted ensemble of NDVI‑Kc and SAVI‑Kc.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>How are field boundaries identified? Can I add my own field?</h3>
            <div class="faq-answer">
              <p>Field boundaries are automatically delineated from annual Sentinel‑2 time series using a <strong>segmentation algorithm</strong>. If the auto‑detection misses your field, you can draw a polygon on the interactive map (Dashboard). The polygon will be stored and processed in future cycles. Small plot holders are encouraged to use the "draw my field" feature.</p>
            </div>
          </div>
        </section>

        <!-- ================= IMPLEMENTATION & IMPACT ================= -->
        <section id="implementation">
          <h2>Implementation & Real‑World Impact</h2>

          <div class="faq-item">
            <h3>How can a farmer access the IWR advice? Is there a mobile app?</h3>
            <div class="faq-answer">
              <p>The main access is through the <strong>web dashboard</strong> (optimised for both desktop and mobile browsers). In addition, the <strong>AquaBot chatbot</strong> is embedded on the homepage and can be used to query "What is the IWR for my village tomorrow?". We are developing a simple <strong>WhatsApp bot</strong> for farmers without internet connectivity (pilot phase).</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Is the system validated with actual field experiments?</h3>
            <div class="faq-answer">
              <p>Yes. A comprehensive validation was carried out during the <strong>Rabi seasons of 2022, 2023, and 2024</strong> across 40 farmer fields in Kashipur, Jaspur, and Rudrapur blocks. Soil moisture sensors and pumping records were used to compare recommended IWR vs actual applied water. Results indicated that following jaldrishiti advisories reduces over‑irrigation by <strong>12–18%</strong> without any yield loss, saving roughly 80–100 m³ of groundwater per hectare per season.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Can I use the system for crops other than wheat?</h3>
            <div class="faq-answer">
              <p>Currently the production version is optimised for <strong>Rabi wheat</strong>. However, behind the scenes the framework supports dynamic Kc curves for any crop if provided with reference Kc tables. We are preparing modules for <strong>mustard, gram, and potato</strong> for the upcoming Rabi season. If you are interested in a specific crop, please contact the IIRS research team.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>How does the system account for different soil types and groundwater depths?</h3>
            <div class="faq-answer">
              <p>Soil texture is incorporated via a <strong>soil water‑holding capacity mask</strong> derived from the Harmonized World Soil Database. Shallow groundwater tables (depth < 3 m) are flagged because they can contribute to capillary rise, reducing IWR. The dashboard displays a "groundwater contribution potential" indicator, and the IWR equation is adjusted accordingly when water tables are shallow.</p>
            </div>
          </div>

          <div class="faq-item">
            <h3>Is there a cost to use jaldrishiti?</h3>
            <div class="faq-answer">
              <p><strong>No.</strong> jaldrishiti is a research initiative funded by <strong>ISRO / IIRS</strong> and the Department of Space. All maps, forecasts, and the chatbot are free for farmers, researchers, and government agencies. Commercial use requires a separate agreement.</p>
            </div>
          </div>
        </section>

        <!-- footer note -->
        <div class="faq-footer-note">
          <hr />
          <p>📢 More questions? Use the <strong>AquaBot</strong> chat widget on the homepage or email the IIRS Water Resources lab.</p>
        </div>
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
.faq-root {
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
.faq-root:not(.dark) {
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
  transition: background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease;
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
   FAQ LAYOUT (Professional - Adobe/Starbucks style)
   ────────────────────────────────────────────────────────────────────── */
.faq-layout {
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
.faq-content {
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

/* FAQ Items - Card style like Starbucks/Adobe */
.faq-item {
  margin: 40px 0;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.03);
  transition: all 0.3s ease;
}

.faq-root:not(.dark) .faq-item {
  background: rgba(0, 0, 0, 0.02);
}

.faq-item h3 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.3rem;
  font-weight: 600;
  margin: 0 0 16px;
  padding: 0;
  color: var(--accent-teal);
  letter-spacing: -0.01em;
}

.faq-item h3::before {
  content: "❓";
  margin-right: 12px;
  font-size: 1.2rem;
}

.faq-answer p, .faq-answer ul {
  font-size: 1rem;
  line-height: 1.7;
  margin-bottom: 16px;
  color: var(--text-secondary);
}

.faq-answer ul {
  margin-left: 20px;
  padding-left: 0;
}

.faq-answer li {
  margin-bottom: 8px;
}

.faq-answer strong {
  color: var(--accent-teal);
  font-weight: 600;
}

.stats-inline {
  display: flex;
  gap: 16px;
  margin-top: 20px;
  flex-wrap: wrap;
}

.stat-badge {
  background: var(--accent-teal-glow);
  border: 1px solid rgba(0,212,168,0.2);
  border-radius: 100px;
  padding: 8px 20px;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--accent-teal);
  font-family: 'JetBrains Mono', monospace;
}

.formula-inline {
  font-family: 'JetBrains Mono', monospace;
  background: var(--accent-teal-glow);
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 0.9rem;
  color: var(--accent-teal);
}

pre {
  background: var(--bg-tertiary);
  padding: 16px;
  border-radius: 16px;
  overflow-x: auto;
  margin: 20px 0;
  font-size: 0.85rem;
  border: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
}

code {
  font-family: 'JetBrains Mono', monospace;
  background: var(--accent-teal-glow);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.85rem;
}

h2 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.8rem;
  font-weight: 700;
  margin: 48px 0 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--accent-teal);
  display: inline-block;
  letter-spacing: -0.01em;
}

hr {
  margin: 48px 0 24px;
  border-color: var(--border);
}

.faq-footer-note p {
  font-style: italic;
  color: var(--text-muted);
  text-align: center;
  padding: 24px;
  background: var(--accent-teal-glow);
  border-radius: 20px;
}

/* ──────────────────────────────────────────────────────────────────────
   FOOTER (copied from Home.vue)
   ────────────────────────────────────────────────────────────────────── */
.site-footer {
  position: relative;
  background: #070808;
  border-top: 1px solid var(--border);
  padding: 10px 24px 40px;
}
.faq-root:not(.dark) .site-footer {
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
  .faq-layout {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .toc-box {
    position: relative;
    top: 0;
  }
  .faq-content {
    padding: 32px 28px;
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
  h2 {
    font-size: 1.4rem;
  }
  .faq-item h3 {
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
  .faq-content {
    padding: 24px 20px;
  }
  .stats-inline {
    flex-direction: column;
  }
  .stat-badge {
    text-align: center;
  }
}
</style>