<template>
  <div class="aquabot-shell" :class="{ dark: isDark }">
    <button class="chat-fab" @click="chatOpen = !chatOpen" :class="{ active: chatOpen }" title="Ask to Bot">
      <span class="chat-fab-icon">{{ chatOpen ? 'X' : '💬' }}</span>
      <span v-if="!chatOpen && unreadCount > 0" class="chat-fab-badge">{{ unreadCount }}</span>
    </button>

    <div class="chat-panel" :class="{ open: chatOpen }">
      <div class="cp-header">
        <div class="cp-header-left">
          <div class="cp-avatar">🌾</div>
          <div>
            <div class="cp-title">Assistant</div>
            <div class="cp-subtitle">
              <span class="cp-dot" :class="{ thinking: botThinking }"></span>
              {{ botThinking ? 'Thinking...' : '' }}
            </div>
          </div>
        </div>
        <button class="cp-close" @click="chatOpen = false">X</button>
      </div>

      <div class="cp-suggestions" v-if="messages.length === 0">
        <div class="cp-suggest-label">Ask me anything about irrigation:</div>
        <div class="cp-chips">
          <button v-for="q in suggestedQuestions" :key="q" class="cp-chip" @click="sendSuggestion(q)">{{ q }}</button>
        </div>
      </div>

      <div class="cp-messages" ref="messagesEl">
        <div v-if="messages.length === 0" class="cp-welcome">
          <div class="cp-welcome-icon">🛰️</div>
          <div class="cp-welcome-text">
            Hello! I'm <strong>AquaBot</strong>, your irrigation intelligence assistant.
          </div>
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="cp-msg"
          :class="msg.role === 'user' ? 'cp-msg-user' : 'cp-msg-bot'"
        >
          <div class="cp-bubble">
            <div class="cp-bubble-text" v-html="renderMarkdown(msg.content)"></div>

            <div v-if="msg.liveData && Object.keys(msg.liveData).length > 0" class="cp-data-card">
              <div class="cp-data-title">📊 Live System Data</div>
              <div class="cp-data-grid">
                <div v-if="msg.liveData.savi" class="cp-data-item">
                  <span class="cp-data-label">SAVI</span>
                  <span class="cp-data-val">{{ msg.liveData.savi }}</span>
                </div>
                <div v-if="msg.liveData.kc" class="cp-data-item">
                  <span class="cp-data-label">Kc</span>
                  <span class="cp-data-val">{{ msg.liveData.kc }}</span>
                </div>
                <div v-if="msg.liveData.cwr" class="cp-data-item">
                  <span class="cp-data-label">CWR</span>
                  <span class="cp-data-val">{{ msg.liveData.cwr }} mm/d</span>
                </div>
                <div v-if="msg.liveData.iwr" class="cp-data-item">
                  <span class="cp-data-label">IWR</span>
                  <span class="cp-data-val">{{ msg.liveData.iwr }} mm/d</span>
                </div>
              </div>
            </div>

            <div v-if="msg.sources && msg.sources.length" class="cp-sources">
              <span v-for="s in msg.sources" :key="s" class="cp-source-tag">{{ s }}</span>
            </div>
          </div>
          <div class="cp-time">{{ msg.time }}</div>
        </div>

        <div v-if="botThinking" class="cp-msg cp-msg-bot">
          <div class="cp-bubble cp-typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

      <div v-if="chatError" class="cp-error">⚠ {{ chatError }}</div>

      <div class="cp-input-row">
        <input
          ref="inputEl"
          v-model="userInput"
          class="cp-input"
          placeholder="Ask about irrigation, CWR, region..."
          @keydown.enter.prevent="sendMessage"
          :disabled="botThinking"
          maxlength="300"
        />
        <button class="cp-send" @click="sendMessage" :disabled="botThinking || !userInput.trim()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="18" height="18">
            <path d="M22 2L11 13M22 2L15 22L11 13M11 13L2 9L22 2"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'

defineProps({
  isDark: { type: Boolean, default: false }
})

const chatOpen = ref(false)
const userInput = ref('')
const messages = ref([])
const botThinking = ref(false)
const chatError = ref('')
const unreadCount = ref(0)
const messagesEl = ref(null)
const inputEl = ref(null)
let msgIdCtr = 0

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const suggestedQuestions = [
  'What is CWR?',
  'Current IWR status',
  'Explain SAVI index',
  'Rabi wheat irrigation schedule',
  'About Udham Singh Nagar',
  'What is Kc?',
]

function nowTime() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- (.+)/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n/g, '<br>')
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function sendMessage() {
  const q = userInput.value.trim()
  if (!q || botThinking.value) return

  chatError.value = ''
  messages.value.push({ id: ++msgIdCtr, role: 'user', content: q, time: nowTime() })
  userInput.value = ''
  botThinking.value = true
  scrollToBottom()

  const history = messages.value.slice(-6).map(m => ({ role: m.role, content: m.content }))

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, history }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    messages.value.push({
      id: ++msgIdCtr,
      role: 'bot',
      content: data.answer,
      sources: data.sources || [],
      liveData: data.live_data || {},
      time: nowTime(),
    })
    if (!chatOpen.value) unreadCount.value++
  } catch (e) {
    chatError.value = 'Could not reach the server. Please ensure the backend is running.'
    messages.value.push({
      id: ++msgIdCtr,
      role: 'bot',
      content: 'Sorry, I could not connect to the server right now. Please try again shortly.',
      sources: [],
      liveData: {},
      time: nowTime(),
    })
  } finally {
    botThinking.value = false
    scrollToBottom()
  }
}

function sendSuggestion(q) {
  userInput.value = q
  sendMessage()
}
</script>

<style scoped>
.chat-fab {
  display: flex;
  position: fixed;
  bottom: 28px;
  right: 28px;
  z-index: 1000;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00D4A8, #3B82F6);
  border: none;
  cursor: pointer;
  box-shadow: 0 8px 28px rgba(0, 212, 168, 0.45);
  transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.3s ease;
  align-items: center;
  justify-content: center;
}
.chat-fab:hover { transform: scale(1.1); box-shadow: 0 12px 36px rgba(0,212,168,0.55); }
.chat-fab.active { background: linear-gradient(135deg, #ef4444, #f97316); }
.chat-fab-icon { color: #fff; font-size: 1.5rem; line-height: 1; }
.chat-fab-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #ef4444;
  color: #fff;
  font-size: 0.65rem;
  font-weight: 700;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
}

.chat-panel {
  position: fixed;
  bottom: 100px;
  right: 30px;
  width: 380px;
  max-height: min(700px, 80vh);
  z-index: 1500;
  display: flex;
  flex-direction: column;
  background: rgba(13, 20, 42, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(0, 212, 168, 0.25);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
  border-radius: 24px;
  opacity: 0;
  pointer-events: none;
  transform: translateY(20px) scale(0.95);
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.chat-panel.open {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0) scale(1);
}
.aquabot-shell:not(.dark) .chat-panel {
  background: rgba(248, 250, 252, 0.98);
  border: 1px solid rgba(13, 148, 136, 0.25);
  box-shadow: 0 20px 50px rgba(0,0,0,0.15);
}

.cp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(0, 212, 168, 0.12);
  background: rgba(0, 212, 168, 0.05);
  flex-shrink: 0;
}
.aquabot-shell:not(.dark) .cp-header {
  border-bottom: 1px solid rgba(13,148,136,0.12);
  background: rgba(13,148,136,0.05);
}
.cp-header-left { display: flex; align-items: center; gap: 12px; }
.cp-avatar {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(0,212,168,0.2), rgba(59,130,246,0.2));
  border: 1px solid rgba(0,212,168,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  box-shadow: 0 4px 12px rgba(0,212,168,0.15);
}
.cp-title {
  font-family: 'Outfit', sans-serif;
  font-weight: 700;
  font-size: 1rem;
  color: #F8FAFC;
  letter-spacing: 0.02em;
}
.aquabot-shell:not(.dark) .cp-title { color: #0F172A; }
.cp-subtitle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  color: #94A3B8;
  font-family: 'JetBrains Mono', monospace;
}
.aquabot-shell:not(.dark) .cp-subtitle { color: #64748B; }
.cp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #00D4A8;
  animation: pulse 2s infinite;
  box-shadow: 0 0 8px rgba(0,212,168,0.6);
  flex-shrink: 0;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.82); }
}
.cp-dot.thinking { background: #FDE047; box-shadow: 0 0 8px rgba(253,224,71,0.6); }
.cp-close {
  background: none;
  border: none;
  color: #64748B;
  cursor: pointer;
  font-size: 1rem;
  padding: 6px;
  border-radius: 8px;
  transition: all 0.2s ease;
}
.cp-close:hover { color: #ef4444; background: rgba(239,68,68,0.1); }

.cp-suggestions {
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(0,212,168,0.08);
  flex-shrink: 0;
}
.aquabot-shell:not(.dark) .cp-suggestions { border-bottom-color: rgba(13,148,136,0.1); }
.cp-suggest-label {
  font-size: 0.7rem;
  color: #64748B;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}
.cp-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.cp-chip {
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.75rem;
  background: rgba(0,212,168,0.08);
  border: 1px solid rgba(0,212,168,0.2);
  color: #00D4A8;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
  white-space: nowrap;
}
.cp-chip:hover {
  background: rgba(0,212,168,0.18);
  border-color: rgba(0,212,168,0.45);
  transform: translateY(-1px);
}
.aquabot-shell:not(.dark) .cp-chip {
  background: rgba(13,148,136,0.08);
  border-color: rgba(13,148,136,0.25);
  color: #0D9488;
}
.aquabot-shell:not(.dark) .cp-chip:hover {
  background: rgba(13,148,136,0.16);
  border-color: rgba(13,148,136,0.45);
}

.cp-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
}
.cp-messages::-webkit-scrollbar { width: 4px; }
.cp-messages::-webkit-scrollbar-thumb { background: rgba(0,212,168,0.2); border-radius: 4px; }

.cp-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 24px 12px;
  gap: 14px;
  background: rgba(0,212,168,0.05);
  border: 1px solid rgba(0,212,168,0.1);
  border-radius: 16px;
}
.aquabot-shell:not(.dark) .cp-welcome {
  background: rgba(13,148,136,0.05);
  border-color: rgba(13,148,136,0.1);
}
.cp-welcome-icon { font-size: 2.5rem; }
.cp-welcome-text { font-size: 0.85rem; color: #94A3B8; line-height: 1.7; }
.aquabot-shell:not(.dark) .cp-welcome-text { color: #334155; }
.cp-welcome-text strong { color: #00D4A8; }
.aquabot-shell:not(.dark) .cp-welcome-text strong { color: #0D9488; }

.cp-msg { display: flex; flex-direction: column; gap: 4px; max-width: 95%; }
.cp-msg-user { align-self: flex-end; align-items: flex-end; }
.cp-msg-bot { align-self: flex-start; align-items: flex-start; }
.cp-bubble {
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 0.82rem;
  line-height: 1.65;
  max-width: 100%;
}
.cp-msg-user .cp-bubble {
  background: linear-gradient(135deg, #00D4A8, #0EA5E9);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(0,212,168,0.25);
}
.cp-msg-bot .cp-bubble {
  background: rgba(30, 41, 59, 0.7);
  border: 1px solid rgba(0,212,168,0.1);
  color: #E2E8F0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.2);
}
.aquabot-shell:not(.dark) .cp-msg-bot .cp-bubble {
  background: #FFFFFF;
  border: 1px solid rgba(13,148,136,0.12);
  color: #334155;
  box-shadow: 0 2px 10px rgba(0,0,0,0.06);
}
.cp-bubble-text code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  background: rgba(0,212,168,0.12);
  padding: 1px 6px;
  border-radius: 4px;
  color: #00D4A8;
}
.aquabot-shell:not(.dark) .cp-bubble-text code { background: rgba(13,148,136,0.1); color: #0D9488; }
.cp-bubble-text ul { margin: 6px 0 0 16px; padding: 0; }
.cp-bubble-text li { margin-bottom: 3px; }

.cp-typing {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 12px 16px;
  min-width: 56px;
}
.cp-typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #00D4A8;
  animation: typingBounce 1.2s infinite;
}
.cp-typing span:nth-child(2) { animation-delay: 0.2s; }
.cp-typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.cp-data-card {
  margin-top: 8px;
  padding: 10px 12px;
  background: rgba(0, 212, 168, 0.06);
  border: 1px solid rgba(0, 212, 168, 0.15);
  border-radius: 10px;
}
.aquabot-shell:not(.dark) .cp-data-card { background: rgba(13,148,136,0.06); border-color: rgba(13,148,136,0.18); }
.cp-data-title {
  font-size: 0.68rem;
  font-weight: 700;
  color: #00D4A8;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
  font-family: 'JetBrains Mono', monospace;
}
.aquabot-shell:not(.dark) .cp-data-title { color: #0D9488; }
.cp-data-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.cp-data-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(0,0,0,0.15);
}
.aquabot-shell:not(.dark) .cp-data-item { background: rgba(0,0,0,0.04); }
.cp-data-label {
  font-size: 0.65rem;
  color: #64748B;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.cp-data-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem;
  font-weight: 700;
  color: #00D4A8;
}
.aquabot-shell:not(.dark) .cp-data-val { color: #0D9488; }

.cp-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.cp-source-tag {
  font-size: 0.62rem;
  padding: 2px 8px;
  border-radius: 50px;
  background: rgba(59,130,246,0.1);
  border: 1px solid rgba(59,130,246,0.2);
  color: #93C5FD;
  font-family: 'JetBrains Mono', monospace;
}
.aquabot-shell:not(.dark) .cp-source-tag {
  background: rgba(37,99,235,0.07);
  border-color: rgba(37,99,235,0.15);
  color: #2563EB;
}
.cp-time {
  font-size: 0.62rem;
  color: #64748B;
  font-family: 'JetBrains Mono', monospace;
  padding: 0 4px;
}
.cp-error {
  padding: 10px 16px;
  font-size: 0.78rem;
  background: rgba(239,68,68,0.1);
  border-top: 1px solid rgba(239,68,68,0.2);
  color: #FCA5A5;
  flex-shrink: 0;
}
.aquabot-shell:not(.dark) .cp-error { color: #DC2626; background: rgba(239,68,68,0.06); }

.cp-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid rgba(0,212,168,0.1);
  background: rgba(0,0,0,0.2);
  flex-shrink: 0;
}
.aquabot-shell:not(.dark) .cp-input-row {
  border-top-color: rgba(13,148,136,0.12);
  background: rgba(0,0,0,0.02);
}
.cp-input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 24px;
  background: rgba(30,41,59,0.6);
  border: 1px solid rgba(0,212,168,0.15);
  color: #F8FAFC;
  font-size: 0.83rem;
  font-family: 'Inter', sans-serif;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.cp-input:focus {
  border-color: rgba(0,212,168,0.45);
  box-shadow: 0 0 0 3px rgba(0,212,168,0.08);
}
.cp-input::placeholder { color: #475569; }
.cp-input:disabled { opacity: 0.5; cursor: not-allowed; }
.aquabot-shell:not(.dark) .cp-input {
  background: #F8FAFC;
  border-color: rgba(13,148,136,0.2);
  color: #0F172A;
}
.aquabot-shell:not(.dark) .cp-input::placeholder { color: #94A3B8; }
.aquabot-shell:not(.dark) .cp-input:focus {
  border-color: rgba(13,148,136,0.5);
  box-shadow: 0 0 0 3px rgba(13,148,136,0.08);
}
.cp-send {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
  background: linear-gradient(135deg, #00D4A8, #0EA5E9);
  border: none;
  cursor: pointer;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 4px 12px rgba(0,212,168,0.3);
}
.cp-send:hover:not(:disabled) {
  transform: scale(1.08);
  box-shadow: 0 6px 18px rgba(0,212,168,0.4);
}
.cp-send:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

@media (max-width: 1299px) {
  .chat-panel {
    width: 100%;
    max-width: 420px;
    border-radius: 24px 0 0 24px;
  }
}
@media (max-width: 480px) {
  .chat-panel {
    width: 100%;
    max-width: 100%;
    border-radius: 24px 24px 0 0;
    top: auto;
    bottom: 0;
    height: 80vh;
    border-left: none;
    border-top: 1px solid rgba(0,212,168,0.2);
  }
  .chat-fab { bottom: 20px; right: 20px; }
}
</style>
