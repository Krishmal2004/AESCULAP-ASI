"use strict";

const I18N = {
  en: {},
  es: {
    tagline: "Apoyo a decisiones clínicas. No es un médico.", patient: "Paciente", clinician: "Clínico",
    language: "Idioma", emergency: "N.º emergencias", send: "Enviar",
    banner: "Si puede tratarse de una emergencia médica, llame ahora a su número de emergencias local. Aesculap no da diagnósticos ni recetas.",
    welcome_title: "¿En qué puedo ayudar?", placeholder: "Describa la pregunta o el caso…",
    welcome_body: "Haga una pregunta de salud. Las respuestas provienen de fuentes publicadas, con citas y nivel de confianza.",
    helpful: "¿Le resultó útil?", thanks: "Gracias, registrado.", calculations: "Cálculos", sources: "Fuentes",
  },
  fr: {
    tagline: "Aide à la décision clinique. Pas un médecin.", patient: "Patient", clinician: "Clinicien",
    language: "Langue", emergency: "N° d'urgence", send: "Envoyer",
    banner: "En cas d'urgence médicale possible, appelez immédiatement votre numéro d'urgence local. Aesculap ne pose pas de diagnostic et ne prescrit pas.",
    welcome_title: "Comment puis-je aider ?", placeholder: "Décrivez la question ou le cas…",
    welcome_body: "Posez une question de santé. Les réponses s'appuient sur des sources publiées, avec citations et niveau de confiance.",
    helpful: "Utile ?", thanks: "Merci, enregistré.", calculations: "Calculs", sources: "Sources",
  },
  de: {
    tagline: "Klinische Entscheidungsunterstützung. Kein Arzt.", patient: "Patient", clinician: "Klinik",
    language: "Sprache", emergency: "Notrufnr.", send: "Senden",
    banner: "Bei einem möglichen medizinischen Notfall rufen Sie sofort den örtlichen Notruf. Aesculap stellt keine Diagnosen und keine Rezepte aus.",
    welcome_title: "Wie kann ich helfen?", placeholder: "Frage oder Fall beschreiben…",
    welcome_body: "Stellen Sie eine Gesundheitsfrage. Antworten stammen aus veröffentlichten Quellen, mit Zitaten und Konfidenz.",
    helpful: "Hilfreich?", thanks: "Danke, gespeichert.", calculations: "Berechnungen", sources: "Quellen",
  },
};

const state = {
  mode: "patient",
  session: (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())).slice(0, 32),
};
const $ = (sel, root = document) => root.querySelector(sel);
const chat = $("#chat");
const t = (key, fallback) => (I18N[$("#language").value] || {})[key] || fallback;

function storeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storeSet(key, v) { try { localStorage.setItem(key, v); } catch { /* private mode */ } }

function applyI18n() {
  const lang = $("#language").value;
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    if (!el.dataset.en) el.dataset.en = el.textContent;
    el.textContent = (I18N[lang] || {})[el.dataset.i18n] || el.dataset.en;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    if (!el.dataset.enPh) el.dataset.enPh = el.placeholder;
    el.placeholder = (I18N[lang] || {})[el.dataset.i18nPlaceholder] || el.dataset.enPh;
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Minimal, safe markdown: escape first, then bold/italic/bullets/citations.
function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "";
  let inList = false;
  for (const raw of lines) {
    let line = raw
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|\s)\*(.+?)\*(?=\s|$)/g, "$1<em>$2</em>")
      .replace(/\[(S\d+)\]/g, '<span class="cite-ref">[$1]</span>');
    if (/^\s*[-•]\s+/.test(raw)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${line.replace(/^\s*[-•]\s+/, "")}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim()) html += `<p>${line}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function addUser(text) {
  $(".welcome")?.remove();
  const el = document.createElement("article");
  el.className = "msg user";
  el.textContent = text;
  chat.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

function badge(text, cls = "") {
  const b = document.createElement("span");
  b.className = `badge ${cls}`;
  b.textContent = text;
  return b;
}

function addAssistant(data) {
  const node = $("#tpl-assistant").content.firstElementChild.cloneNode(true);
  node.classList.add(data.decision);
  const meta = $(".meta", node);
  const labels = { escalate: "Emergency", block: "Safety block", review: "Held for clinician review", allow: "Answer" };
  meta.append(badge(labels[data.decision] || data.decision));
  meta.append(badge(`risk: ${data.risk_tier}`));
  if (data.confidence && data.confidence !== "n/a") meta.append(badge(`confidence: ${data.confidence}`, `conf-${data.confidence}`));
  meta.append(badge(data.mode));
  $(".body", node).innerHTML = renderMarkdown(data.answer);

  const cites = $(".cites", node);
  if (data.citations?.length) {
    $("summary", cites).textContent = `${t("sources", "Sources")} (${data.citations.length})`;
    const ol = $("ol", cites);
    for (const c of data.citations) {
      const li = document.createElement("li");
      const title = c.url
        ? Object.assign(document.createElement("a"), { href: c.url, target: "_blank", rel: "noopener noreferrer", textContent: c.title || c.source })
        : document.createTextNode(c.title || c.source);
      li.append(`[${c.id}] `, title, ` — ${c.source}, ${c.date || "n/a"}, ${c.evidence_level}`);
      const snip = document.createElement("span");
      snip.className = "snippet";
      snip.textContent = (c.text || "").slice(0, 280) + ((c.text || "").length > 280 ? "…" : "");
      li.append(snip);
      ol.append(li);
    }
  } else cites.remove();

  const tools = $(".tools", node);
  const calc = (data.tool_results || []).filter((r) => r.summary);
  if (calc.length) {
    for (const r of calc) {
      const li = document.createElement("li");
      li.textContent = r.summary;
      $("ul", tools).append(li);
    }
  } else tools.remove();

  const fb = $(".feedback", node);
  fb.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-rating]");
    if (!btn) return;
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trace_id: data.trace_id, rating: Number(btn.dataset.rating),
        failure_type: $(".ftype", fb).value, role: state.mode }),
    }).catch(() => {});
    fb.querySelectorAll("button, select").forEach((x) => (x.disabled = true));
    $(".thanks", fb).hidden = false;
  });

  chat.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "start" });
  if (data.review_id) pollReview(data.review_id, node);
}

async function pollReview(id, node) {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 10000));
    const res = await fetch(`/api/reviews/${id}/result`).catch(() => null);
    if (!res?.ok) continue;
    const r = await res.json();
    if (r.status === "approved") {
      $(".body", node).innerHTML = renderMarkdown("**Clinician-approved answer:**\n" + r.answer);
      return;
    }
    if (r.status === "rejected") {
      $(".body", node).innerHTML = renderMarkdown("A clinician reviewed this and did not approve an automated answer. Please speak to a clinician or pharmacist directly.");
      return;
    }
  }
}

async function send(text) {
  addUser(text);
  const btn = $("#send");
  btn.disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text, mode: state.mode, session_id: state.session,
        language: $("#language").value, locale: $("#locale").value.trim() || null,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    addAssistant(await res.json());
  } catch (err) {
    addAssistant({ decision: "block", risk_tier: "n/a", mode: state.mode, confidence: "n/a",
      answer: `Sorry, something went wrong (${err.message}). If this is urgent, contact a clinician or your local emergency number.` });
  } finally {
    btn.disabled = false;
  }
}

document.querySelectorAll(".seg-btn").forEach((b) =>
  b.addEventListener("click", () => {
    state.mode = b.dataset.mode;
    storeSet("aesculap.mode", state.mode);
    document.querySelectorAll(".seg-btn").forEach((x) => {
      x.classList.toggle("active", x === b);
      x.setAttribute("aria-checked", String(x === b));
    });
  })
);
$("#language").addEventListener("change", () => { storeSet("aesculap.lang", $("#language").value); applyI18n(); });
$("#locale").addEventListener("change", () => storeSet("aesculap.locale", $("#locale").value));
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#message").value.trim();
  if (!text) return;
  $("#message").value = "";
  send(text);
});
$("#message").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
});
document.querySelectorAll(".example").forEach((b) => b.addEventListener("click", () => send(b.textContent)));

(function restore() {
  const lang = storeGet("aesculap.lang");
  if (lang && [...$("#language").options].some((o) => o.value === lang)) $("#language").value = lang;
  const loc = storeGet("aesculap.locale");
  if (loc) $("#locale").value = loc;
  const mode = storeGet("aesculap.mode");
  if (mode) document.querySelector(`.seg-btn[data-mode="${mode}"]`)?.click();
  applyI18n();
})();
