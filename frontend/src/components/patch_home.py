import re

with open('/home/aman-/aman/irrigation/frontend/src/components/Home.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update <script setup> to include overviewStats and footerTech
script_additions = """
const overviewStats = [
  { icon: '🛰️', value: '10m', label: 'Spatial Resolution' },
  { icon: '🔄', value: '5 Days', label: 'Revisit Frequency' },
  { icon: '🌾', value: '150 Days', label: 'Rabi Season Window' },
  { icon: '💧', value: 'Real-time', label: 'Water Estimation' },
  { icon: '📍', value: 'Field', label: 'Scale Level' },
  { icon: '⚡', value: 'Live', label: 'Data Processing' },
]

const footerTech = [
  { name: 'Vue 3', icon: '⚡', role: 'Frontend Framework' },
  { name: 'FastAPI', icon: '🚀', role: 'Backend API' },
  { name: 'PostgreSQL', icon: '🐘', role: 'Database' },
  { name: 'Sentinel-2', icon: '🛸', role: 'EO Imagery' }
]
"""

# Replace `]
# </script>` with `]\n\n` + script_additions + `\n</script>`
content = content.replace("  },\n]\n</script>", "  },\n]\n" + script_additions + "\n</script>")


# 2. Update Animated Background Template
old_bg = """    <!-- ══════════════════ ANIMATED BG ══════════════════ -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div class="field-grid"></div>
      <div v-for="p in particles" :key="p.id" class="particle"
        :style="`left:${p.x}%;top:${p.y}%;animation-delay:${p.delay}s;animation-duration:${p.dur}s;width:${p.size}px;height:${p.size}px;opacity:${p.op}`">
      </div>
      <div class="orbit-ring"><div class="orbit-dot"></div></div>
      <div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
    </div>"""

new_bg = """    <!-- ══════════════════ ANIMATED BG ══════════════════ -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div class="field-grid"></div>
      <div class="grid-overlay"></div>
      <div v-for="p in particles" :key="p.id" class="particle"
        :style="`left:${p.x}%;top:${p.y}%;animation-delay:${p.delay}s;animation-duration:${p.dur}s;width:${p.size}px;height:${p.size}px;opacity:${p.op}`">
      </div>
      <div class="orbit-ring orbit-ring-1"><div class="orbit-dot"></div></div>
      <div class="orbit-ring orbit-ring-2"><div class="orbit-dot dot-alt"></div></div>
      <div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
    </div>"""
content = content.replace(old_bg, new_bg)

# 3. Enhance Theme Colors and Animations
old_theme = """  /* DARK THEME - Professional Slate & Deep Indigo */
  --bg-primary: #0A0F1C;
  --bg-secondary: #111827;
  --bg-tertiary: #1F2937;
  --surface: #1E293B;
  --surface-hover: #334155;
  --border: rgba(255,255,255,0.08);"""

new_theme = """  /* DARK THEME - Professional Slate & Deep Indigo (Modernized) */
  --bg-primary: #040814;
  --bg-secondary: #0A1128;
  --bg-tertiary: #131E3A;
  --surface: rgba(19, 30, 58, 0.4);
  --surface-hover: rgba(19, 30, 58, 0.65);
  --border: rgba(0, 212, 168, 0.15);"""
content = content.replace(old_theme, new_theme)

# 4. Enhance Animated Grid CSS
old_grid_css = """.field-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(var(--accent-teal-glow) 1px, transparent 1px),
    linear-gradient(90deg, var(--accent-teal-glow) 1px, transparent 1px);
  background-size: 52px 52px;
  opacity: 0.3;
}
.home-root:not(.dark) .field-grid { opacity: 0.4; }"""

new_grid_css = """.field-grid {
  position: absolute; inset: -50% -50% -50% -50%;
  background-image:
    linear-gradient(var(--accent-teal-glow) 1px, transparent 1px),
    linear-gradient(90deg, var(--accent-teal-glow) 1px, transparent 1px);
  background-size: 60px 60px;
  opacity: 0.25;
  transform: perspective(600px) rotateX(60deg) translateY(-100px) translateZ(-200px);
  animation: gridMove 20s linear infinite;
  mask-image: radial-gradient(circle at center, black 10%, transparent 80%);
  -webkit-mask-image: radial-gradient(circle at center, black 10%, transparent 80%);
}
@keyframes gridMove {
  from { transform: perspective(600px) rotateX(60deg) translateY(0) translateZ(-200px); }
  to { transform: perspective(600px) rotateX(60deg) translateY(60px) translateZ(-200px); }
}
.grid-overlay {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at top, transparent 20%, var(--bg-primary) 80%);
}
.home-root:not(.dark) .field-grid { opacity: 0.4; }"""
content = content.replace(old_grid_css, new_grid_css)

# Update orbit ring
old_orbit = """.orbit-ring {
  position: absolute; top: 50%; left: 50%;
  width: 600px; height: 600px; margin: -300px;
  border-radius: 50%;
  border: 1px dashed rgba(0,212,168,0.15);
  animation: orbit 45s linear infinite;
}
.home-root:not(.dark) .orbit-ring { border-color: rgba(13,148,136,0.15); }
.orbit-dot {
  position: absolute; top: -5px; left: 50%; margin-left: -5px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent-teal);
  box-shadow: 0 0 14px var(--accent-teal);
}
@keyframes orbit { to { transform: rotate(360deg); } }"""

new_orbit = """.orbit-ring {
  position: absolute; top: 50%; left: 50%; border-radius: 50%;
  border: 1px dashed rgba(0,212,168,0.15);
}
.orbit-ring-1 {
  width: 600px; height: 600px; margin: -300px;
  animation: orbit 45s linear infinite;
}
.orbit-ring-2 {
  width: 800px; height: 800px; margin: -400px;
  border: 1px dashed rgba(59,130,246,0.15);
  animation: orbit 60s linear infinite reverse;
}
.home-root:not(.dark) .orbit-ring { border-color: rgba(13,148,136,0.15); }
.orbit-dot {
  position: absolute; top: -5px; left: 50%; margin-left: -5px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent-teal);
  box-shadow: 0 0 14px var(--accent-teal);
}
.orbit-dot.dot-alt { background: var(--accent-blue); box-shadow: 0 0 14px var(--accent-blue); box-shadow: 0 0 18px rgba(59, 130, 246, 0.8); }
@keyframes orbit { to { transform: rotate(360deg); } }"""
content = content.replace(old_orbit, new_orbit)

# 5. Make Header & Nav Glassmorphism pop
content = content.replace("backdrop-filter: blur(12px);", "backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05);")
content = content.replace("backdrop-filter: blur(16px);", "backdrop-filter: blur(24px); border-bottom: 1px solid rgba(255,255,255,0.05);")

# Nav links fancy hover
old_nav_link = """.nav-link:hover { color: var(--accent-teal); background: var(--accent-teal-glow); }"""
new_nav_link = """.nav-link { position: relative; }
.nav-link::after {
  content: ''; position: absolute; bottom: 0; left: 50%;
  width: 0%; height: 2px; background: var(--accent-teal);
  transition: all 0.3s ease; transform: translateX(-50%); border-radius: 2px;
}
.nav-link:hover { color: var(--accent-teal); background: transparent; }
.nav-link:hover::after { width: 80%; }"""
content = content.replace(old_nav_link, new_nav_link)

# Footer refinement
content = content.replace("border-top: 1px solid var(--border); padding: 40px 24px;", "border-top: 1px solid var(--border); padding: 60px 24px 40px;")
old_fb_name = ".fb-name { font-weight: 700; font-family: 'Outfit', sans-serif; font-size: 1rem; color: var(--text-primary); margin: 0 0 4px; }"
new_fb_name = ".fb-name { font-weight: 800; font-family: 'Outfit', sans-serif; font-size: 1.25rem; color: var(--text-primary); margin: 0 0 6px; letter-spacing: 0.05em; }"
content = content.replace(old_fb_name, new_fb_name)

# Make stats card look more professional
content = content.replace(".stat-card {", ".stat-card { cursor: default;")
old_stat_hover = ".stat-card:hover { background: var(--surface-hover); }"
new_stat_hover = ".stat-card:hover { background: var(--surface-hover); transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); border-color: rgba(0,212,168,0.2) !important; border-radius: 12px; z-index: 10; position: relative; }"
content = content.replace(old_stat_hover, new_stat_hover)
content = content.replace("font-size: clamp(1rem, 2vw, 1.25rem); font-weight: 700; color: var(--accent-teal);", "font-size: clamp(1.4rem, 2.5vw, 1.8rem); font-weight: 800; color: var(--accent-teal); text-shadow: 0 0 15px rgba(0, 212, 168, 0.4);")


with open('/home/aman-/aman/irrigation/frontend/src/components/Home.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully.")
