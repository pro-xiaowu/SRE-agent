<script setup>
import { computed, nextTick, onMounted, ref } from "vue";

const EXAMPLES = [
  "现在有哪些 firing 告警？",
  "有没有 target down？",
  "把这条告警静默 1 小时",
];

const input = ref("");
const busy = ref(false);
const error = ref("");
const sessionId = ref(localStorage.getItem("sre-active-session") || "");
const sessions = ref([]);
const logEl = ref(null);
const turns = ref([
  {
    role: "system",
    text: "值班台已接通。只读查询会打到 Prometheus / Alertmanager；写操作只记审批单，V1 不执行。",
  },
]);

const lastStatus = computed(() => {
  const t = [...turns.value].reverse().find((x) => x.role === "agent");
  return t?.status || "idle";
});

function saveActive() {
  localStorage.setItem("sre-active-session", sessionId.value);
}

async function loadSessions() {
  const res = await fetch("/api/sessions");
  if (!res.ok) throw new Error("无法加载会话");
  sessions.value = (await res.json()).sessions;
  if (!sessionId.value || !sessions.value.some((s) => s.id === sessionId.value)) {
    if (sessions.value.length) {
      await switchSession(sessions.value[0].id);
    } else {
      await newSession();
    }
  } else {
    await switchSession(sessionId.value);
  }
}

async function newSession() {
  const res = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "新会话" }),
  });
  if (!res.ok) throw new Error("无法创建会话");
  const data = await res.json();
  sessionId.value = data.id;
  saveActive();
  turns.value = [{ role: "system", text: "值班台已接通。只读查询会打到 Prometheus / Alertmanager；写操作只记审批单，V1 不执行。" }];
  await loadSessionsCatalog();
}

async function loadSessionsCatalog() {
  const res = await fetch("/api/sessions");
  if (res.ok) sessions.value = (await res.json()).sessions;
}

async function switchSession(id) {
  sessionId.value = id;
  saveActive();
  const res = await fetch(`/api/sessions/${encodeURIComponent(id)}/messages`);
  if (!res.ok) throw new Error("无法恢复会话");
  const data = await res.json();
  turns.value = [
    { role: "system", text: "值班台已接通。只读查询会打到 Prometheus / Alertmanager；写操作只记审批单，V1 不执行。" },
    ...data.messages.map((m) => ({ role: m.role === "human" ? "you" : "agent", text: m.content })),
  ];
  await scroll();
}

async function removeSession(id) {
  await fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (id === sessionId.value) {
    sessionId.value = "";
    localStorage.removeItem("sre-active-session");
  }
  await loadSessions();
}

async function send(text) {
  const q = (text ?? input.value).trim();
  if (!q || busy.value) return;
  error.value = "";
  input.value = "";
  turns.value.push({ role: "you", text: q });
  busy.value = true;
  await scroll();
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: q, session_id: sessionId.value }),
    });
    if (!res.ok) {
      const raw = await res.text();
      throw new Error(raw || res.statusText);
    }
    const data = await res.json();
    turns.value.push({
      role: "agent",
      text: data.text,
      promql: data.promql_blocks || [],
      approvalId: data.approval_id,
      intent: data.intent,
      status: data.status,
    });
    await loadSessionsCatalog();
  } catch (e) {
    error.value =
      "后端没连上。先在项目根目录执行 uv run sre-agent serve（默认 :9108），再开这个页面。";
    turns.value.push({
      role: "agent",
      text: String(e.message || e),
      status: "rejected",
    });
  } finally {
    busy.value = false;
    await scroll();
  }
}

async function scroll() {
  await nextTick();
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
}

onMounted(() => {
  fetch("/api/health").then(() => loadSessions()).catch(() => {
    error.value = "检测不到 /api/health。请先启动 sre-agent serve。";
  });
});
</script>

<template>
  <div class="shell">
    <aside class="rail">
      <div class="busbar" aria-hidden="true" />
      <p class="eyebrow">SRE-Agent · 值班台</p>
      <h1>对着机柜说话</h1>
      <p class="lede">
        人话进左侧，PromQL 出右侧。模型只负责理解；真正查询是只读的。
      </p>

      <dl class="meta">
        <div>
          <dt>会话</dt>
          <dd>{{ sessionId }}</dd>
        </div>
        <div>
          <dt>上次状态</dt>
          <dd :class="'st st-' + lastStatus">{{ lastStatus }}</dd>
        </div>
      </dl>

      <p class="hint">试一句</p>
      <div class="chips">
        <button v-for="ex in EXAMPLES" :key="ex" type="button" class="chip" @click="send(ex)">
          {{ ex }}
        </button>
      </div>
      <div class="session-tools">
        <button type="button" class="new-session" @click="newSession">+ 新会话</button>
        <div
          v-for="s in sessions"
          :key="s.id"
          role="button"
          tabindex="0"
          type="button"
          class="session-item"
          :class="{ active: s.id === sessionId }"
          @click="switchSession(s.id)"
          @keydown.enter="switchSession(s.id)"
        >
          <span>{{ s.title }}</span>
          <span class="session-meta">
            <small>{{ s.message_count }}</small>
            <button type="button" class="delete-session" title="删除会话" @click.stop="removeSession(s.id)">×</button>
          </span>
        </div>
      </div>
    </aside>

    <section class="stage">
      <header class="stage-head">
        <span class="live" :class="{ on: !error }" />
        <span>{{ error ? "链路断开" : "只读通道" }}</span>
      </header>

      <div ref="logEl" class="log" role="log">
        <article v-for="(t, i) in turns" :key="i" :class="['turn', t.role]">
          <span class="who">{{ t.role === "you" ? "值班" : t.role === "system" ? "台" : "Agent" }}</span>
          <div class="body">
            <pre class="md">{{ t.text }}</pre>
            <pre v-for="(q, qi) in t.promql || []" :key="qi" class="ql">{{ q }}</pre>
            <p v-if="t.approvalId" class="ticket">审批单 {{ t.approvalId }} · V1 不执行</p>
          </div>
        </article>
        <article v-if="busy" class="turn agent wait">
          <span class="who">Agent</span>
          <div class="scope" aria-hidden="true">
            <svg viewBox="0 0 240 28" preserveAspectRatio="none">
              <polyline
                points="0,14 20,14 28,6 36,22 48,14 80,14 92,4 104,24 120,14 240,14"
              />
            </svg>
          </div>
        </article>
      </div>

      <form class="composer" @submit.prevent="send()">
        <p v-if="error" class="err">{{ error }}</p>
        <label class="sr" for="q">巡检问题</label>
        <textarea
          id="q"
          v-model="input"
          rows="3"
          :disabled="busy"
          placeholder="现在有哪些 firing 告警？"
          @keydown.enter.exact.prevent="send()"
        />
        <div class="row">
          <span class="tiny">Enter 发送 · Shift+Enter 换行</span>
          <button type="submit" :disabled="busy || !input.trim()">询问机柜</button>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: minmax(260px, 34%) 1fr;
  height: 100%;
  min-height: 100vh;
}

.rail {
  position: relative;
  padding: 2.2rem 1.8rem 1.6rem 2.1rem;
  background: linear-gradient(180deg, #1a212c 0%, #141820 100%);
  border-right: 1px solid var(--line);
}

.busbar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 7px;
  background: linear-gradient(180deg, var(--copper-hot), var(--copper) 40%, #7a4a22);
}

.eyebrow {
  margin: 0 0 0.6rem;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--copper);
}

h1 {
  margin: 0;
  font-family: "Instrument Sans", "IBM Plex Sans", sans-serif;
  font-weight: 650;
  font-size: clamp(1.8rem, 3vw, 2.4rem);
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.lede {
  margin: 1rem 0 1.6rem;
  color: var(--mute);
  line-height: 1.55;
}

.meta {
  margin: 0 0 1.8rem;
  display: grid;
  gap: 0.7rem;
}

.meta div {
  display: grid;
  gap: 0.15rem;
}

dt {
  font-size: 0.7rem;
  color: var(--mute);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

dd {
  margin: 0;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.85rem;
}

.st-ok {
  color: var(--ok);
}
.st-approval_created {
  color: var(--copper-hot);
}
.st-rejected {
  color: var(--alarm);
}

.hint {
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  color: var(--mute);
}

.chips {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.chip {
  text-align: left;
  background: transparent;
  color: var(--paper);
  border: 1px solid var(--line);
  border-radius: 2px;
  padding: 0.55rem 0.7rem;
  cursor: pointer;
}

.chip:hover {
  border-color: var(--copper);
  color: var(--copper-hot);
}

.stage {
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
  background: var(--rack);
}

.stage-head {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.85rem 1.4rem;
  border-bottom: 1px solid var(--line);
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.75rem;
  color: var(--mute);
}

.live {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--alarm);
}

.live.on {
  background: var(--scope);
  box-shadow: 0 0 8px var(--scope);
}

.log {
  overflow: auto;
  padding: 1.2rem 1.4rem 0.4rem;
}

.turn {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 0.8rem;
  margin-bottom: 1.1rem;
}

.who {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.7rem;
  color: var(--copper);
  padding-top: 0.2rem;
}

.body {
  background: var(--panel);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-left: 2px solid var(--copper);
  padding: 0.85rem 1rem;
}

.you .body {
  border-left-color: var(--scope);
  background: var(--panel-2);
}

.md,
.ql {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "IBM Plex Sans", sans-serif;
  line-height: 1.55;
}

.ql {
  margin-top: 0.75rem;
  padding: 0.7rem 0.8rem;
  background: #0e1218;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.78rem;
  color: var(--scope);
}

.ticket {
  margin: 0.7rem 0 0;
  color: var(--copper-hot);
  font-size: 0.85rem;
}

.scope {
  height: 36px;
  background: #0e1218;
  border: 1px solid var(--line);
}

.scope svg {
  width: 100%;
  height: 100%;
  stroke: var(--scope);
  fill: none;
  stroke-width: 1.6;
  animation: sweep 1.1s linear infinite;
}

@keyframes sweep {
  from {
    stroke-dashoffset: 80;
    stroke-dasharray: 12 8;
  }
  to {
    stroke-dashoffset: 0;
    stroke-dasharray: 12 8;
  }
}

.composer {
  padding: 0.9rem 1.4rem 1.2rem;
  border-top: 1px solid var(--line);
  background: #171d26;
}

.err {
  margin: 0 0 0.5rem;
  color: var(--alarm);
  font-size: 0.85rem;
}

textarea {
  width: 100%;
  resize: vertical;
  background: var(--rack);
  color: var(--paper);
  border: 1px solid var(--line);
  border-radius: 2px;
  padding: 0.75rem 0.85rem;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.55rem;
}

.tiny {
  color: var(--mute);
  font-size: 0.75rem;
}

.row button {
  background: var(--copper);
  color: #1a120a;
  border: 0;
  padding: 0.5rem 1rem;
  font-weight: 600;
  cursor: pointer;
}

.row button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .rail {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
}
</style>
