/**
 * Agro-Botany chat widget for ekolojiktarim.com.tr.
 *
 * Single-file, framework-free embed. Drop this before </body>:
 *
 *   <script src="agro-chat-widget.js"
 *           data-api-base="http://127.0.0.1:8000"></script>
 *
 * Uses Shadow DOM so the widget's styles never leak into (or clash with)
 * the host page's CSS.
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript;
  var API_BASE = (scriptEl && scriptEl.getAttribute("data-api-base")) || "http://127.0.0.1:8000";

  var BRAND = {
    green: "#60a945",
    greenLight: "#95c362",
    dark: "#231f20",
  };

  // Greeting shown before any user message exists, so there's nothing to
  // detect language from yet - picked from the browser's locale instead.
  // Falls back to English for locales not in this list.
  var GREETINGS = {
    tr: "Merhaba! Ben ekolojik tarım asistanıyım. Bitki besleme, organik gübreleme ve toprak sağlığı hakkında sorularınızı yanıtlayabilirim.",
    en: "Hello! I'm an ecological agriculture assistant. I can help with plant nutrition, organic fertilization, and soil health questions.",
    de: "Hallo! Ich bin ein Assistent für ökologische Landwirtschaft. Ich helfe gerne bei Fragen zu Pflanzenernährung, organischer Düngung und Bodengesundheit.",
    fr: "Bonjour ! Je suis un assistant en agriculture écologique. Je peux répondre à vos questions sur la nutrition des plantes, la fertilisation biologique et la santé des sols.",
    es: "¡Hola! Soy un asistente de agricultura ecológica. Puedo ayudarte con preguntas sobre nutrición vegetal, fertilización orgánica y salud del suelo.",
    ar: "مرحباً! أنا مساعد للزراعة البيئية. يمكنني مساعدتك في أسئلة حول تغذية النباتات والتسميد العضوي وصحة التربة.",
  };

  function getGreeting() {
    var lang = (navigator.language || "en").slice(0, 2).toLowerCase();
    return GREETINGS[lang] || GREETINGS.en;
  }

  var LOGO_URL = "https://www.ekolojiktarim.com.tr/wp-content/uploads/2024/09/ekolojik-tarim.svg";

  var CSS = "" +
    ":host, * { box-sizing: border-box; }" +
    /* bottom offset cleared to sit above the site's own WhatsApp button
       (#ht-ctc-chat, measured at bottom:15px/right:30px/68x68px) */
    ".launcher {" +
    "  position: fixed; bottom: 100px; right: 22px; width: 60px; height: 60px;" +
    "  border-radius: 50%; background: " + BRAND.green + "; box-shadow: 0 4px 16px rgba(0,0,0,.25);" +
    "  display: flex; align-items: center; justify-content: center; cursor: pointer;" +
    "  z-index: 999999; border: none; transition: transform .15s ease;" +
    "}" +
    ".launcher:hover { transform: scale(1.06); }" +
    ".launcher svg { width: 28px; height: 28px; fill: #fff; }" +
    ".panel {" +
    "  position: fixed; bottom: 174px; right: 22px; width: 370px; max-width: calc(100vw - 32px);" +
    "  height: 560px; max-height: calc(100vh - 220px); background: #fff; border-radius: 16px;" +
    "  box-shadow: 0 8px 32px rgba(0,0,0,.28); display: flex; flex-direction: column; overflow: hidden;" +
    "  z-index: 999999; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;" +
    "  opacity: 0; transform: translateY(12px); pointer-events: none; transition: opacity .18s ease, transform .18s ease;" +
    "}" +
    ".panel.open { opacity: 1; transform: translateY(0); pointer-events: auto; }" +
    ".header {" +
    "  background: " + BRAND.green + "; color: #fff; padding: 14px 16px; display: flex;" +
    "  align-items: center; gap: 10px; flex-shrink: 0;" +
    "}" +
    ".header img { height: 22px; filter: brightness(0) invert(1); }" +
    ".header .title { font-size: 14px; font-weight: 600; line-height: 1.25; }" +
    ".header .close { margin-left: auto; cursor: pointer; opacity: .9; padding: 4px; }" +
    ".header .close:hover { opacity: 1; }" +
    ".messages {" +
    "  flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px;" +
    "  background: #f7f9f5;" +
    "}" +
    ".msg { max-width: 84%; padding: 9px 12px; border-radius: 14px; font-size: 13.5px; line-height: 1.45; word-wrap: break-word; }" +
    ".msg.user { align-self: flex-end; background: " + BRAND.green + "; color: #fff; border-bottom-right-radius: 4px; white-space: pre-wrap; }" +
    ".msg.bot { align-self: flex-start; background: #fff; color: " + BRAND.dark + "; border: 1px solid #e3e8dd; border-bottom-left-radius: 4px; }" +
    ".msg.bot.typing { color: #8a9280; font-style: italic; }" +
    ".msg.bot p { margin: 0 0 8px 0; }" +
    ".msg.bot p:last-child { margin-bottom: 0; }" +
    ".msg.bot ul { margin: 4px 0 8px 0; padding-left: 18px; }" +
    ".msg.bot ul:last-child { margin-bottom: 0; }" +
    ".msg.bot li { margin-bottom: 3px; }" +
    ".msg.bot strong { font-weight: 700; }" +
    ".products { align-self: flex-start; max-width: 88%; display: flex; flex-direction: column; gap: 6px; }" +
    ".product-chip {" +
    "  display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid " + BRAND.greenLight + ";" +
    "  border-radius: 10px; padding: 8px 10px; text-decoration: none; color: " + BRAND.dark + "; font-size: 12.5px;" +
    "}" +
    ".product-chip:hover { background: #eef6e7; }" +
    ".product-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: " + BRAND.green + "; flex-shrink: 0; }" +
    ".input-row { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e6e6e6; flex-shrink: 0; background: #fff; }" +
    ".input-row input {" +
    "  flex: 1; border: 1px solid #d7dcd0; border-radius: 20px; padding: 10px 14px; font-size: 13.5px; outline: none;" +
    "}" +
    ".input-row input:focus { border-color: " + BRAND.green + "; }" +
    ".input-row input:disabled { opacity: .6; }" +
    ".input-row button {" +
    "  width: 38px; height: 38px; border-radius: 50%; border: none; background: " + BRAND.green + ";" +
    "  color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0;" +
    "}" +
    ".input-row button:disabled { opacity: .5; cursor: default; }" +
    ".input-row button svg { width: 16px; height: 16px; fill: #fff; }" +
    "@media (max-width: 420px) {" +
    "  .panel { right: 8px; bottom: 168px; width: calc(100vw - 16px); height: calc(100vh - 210px); }" +
    "  .launcher { right: 16px; bottom: 100px; }" +
    "}";

  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (html != null) e.innerHTML = html;
    return e;
  }

  function buildUI(root) {
    var style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);

    var launcher = el("button", { class: "launcher", "aria-label": "Sohbeti aç" },
      '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>');

    var panel = el("div", { class: "panel" });

    var header = el("div", { class: "header" });
    var logoImg = el("img", { src: LOGO_URL, alt: "logo" });
    var titleWrap = el("div", {}, '<div class="title">Ekolojik Tarım Asistanı</div>');
    var closeBtn = el("div", { class: "close" }, "&#10005;");
    header.appendChild(logoImg);
    header.appendChild(titleWrap);
    header.appendChild(closeBtn);

    var messages = el("div", { class: "messages" });

    var inputRow = el("div", { class: "input-row" });
    var input = el("input", { type: "text", placeholder: "Bitkileriniz hakkında bir soru sorun..." });
    var sendBtn = el("button", { "aria-label": "Gönder" },
      '<svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>');
    inputRow.appendChild(input);
    inputRow.appendChild(sendBtn);

    panel.appendChild(header);
    panel.appendChild(messages);
    panel.appendChild(inputRow);

    root.appendChild(launcher);
    root.appendChild(panel);

    return { launcher: launcher, panel: panel, closeBtn: closeBtn, messages: messages, input: input, sendBtn: sendBtn };
  }

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Minimal, XSS-safe markdown: escapes HTML first, then supports **bold**
  // and "* "/"- " bullet lines. Good enough for LLM-style chat formatting.
  function renderMarkdown(text) {
    var escaped = escapeHtml(text);
    var lines = escaped.split("\n");
    var html = "";
    var inList = false;
    lines.forEach(function (line) {
      var bulletMatch = /^\s*[*-]\s+(.*)$/.exec(line);
      if (bulletMatch) {
        if (!inList) { html += "<ul>"; inList = true; }
        html += "<li>" + bulletMatch[1] + "</li>";
      } else {
        if (inList) { html += "</ul>"; inList = false; }
        if (line.trim() === "") {
          html += "<br>";
        } else {
          html += "<p>" + line + "</p>";
        }
      }
    });
    if (inList) html += "</ul>";
    // Bold first (**text**), then remaining single-asterisk pairs as italics.
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    return html;
  }

  function addMessage(messagesEl, role, text) {
    var bubble = el("div", { class: "msg " + role }, "");
    if (role.indexOf("bot") === 0) {
      bubble.innerHTML = renderMarkdown(text);
    } else {
      bubble.textContent = text;
    }
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
  }

  function addProducts(messagesEl, products) {
    if (!products || !products.length) return;
    var wrap = el("div", { class: "products" });
    products.forEach(function (p) {
      var a = el("a", { class: "product-chip", href: p.link, target: "_blank", rel: "noopener" });
      var dot = el("span", { class: "dot" });
      var label = document.createElement("span");
      label.textContent = p.title;
      a.appendChild(dot);
      a.appendChild(label);
      wrap.appendChild(a);
    });
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function initWidget() {
    var host = document.createElement("div");
    host.id = "agro-chat-widget-host";
    document.body.appendChild(host);
    var shadow = host.attachShadow({ mode: "open" });
    var ui = buildUI(shadow);

    var history = [];
    var open = false;

    function togglePanel(force) {
      open = typeof force === "boolean" ? force : !open;
      ui.panel.classList.toggle("open", open);
    }

    ui.launcher.addEventListener("click", function () { togglePanel(); });
    ui.closeBtn.addEventListener("click", function () { togglePanel(false); });

    function send() {
      // Guard against a second send while one is still in flight - Enter
      // calls send() directly, bypassing the button's disabled state.
      if (ui.sendBtn.disabled) return;
      var text = ui.input.value.trim();
      if (!text) return;
      ui.input.value = "";
      ui.input.disabled = true;
      ui.sendBtn.disabled = true;
      addMessage(ui.messages, "user", text);
      // Snapshot prior turns only - the current message is sent separately
      // via `message`, so it must not also appear as the last history entry.
      var requestHistory = history.slice();

      var botBubble = addMessage(ui.messages, "bot typing", "Yazıyor...");
      var accumulated = "";
      var firstToken = true;

      fetch(API_BASE + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: requestHistory, stream: true }),
      })
        .then(function (resp) {
          var reader = resp.body.getReader();
          var decoder = new TextDecoder("utf-8");
          var buffer = "";

          function pump() {
            return reader.read().then(function (result) {
              if (result.done) return;
              buffer += decoder.decode(result.value, { stream: true });
              var lines = buffer.split("\n\n");
              buffer = lines.pop();
              lines.forEach(function (line) {
                if (!line.startsWith("data: ")) return;
                var evt;
                try { evt = JSON.parse(line.slice(6)); } catch (e) { return; }
                if (evt.type === "products") {
                  addProducts(ui.messages, evt.recommended_products);
                } else if (evt.type === "token") {
                  if (firstToken) {
                    botBubble.classList.remove("typing");
                    firstToken = false;
                  }
                  accumulated += evt.content;
                  botBubble.innerHTML = renderMarkdown(accumulated);
                  ui.messages.scrollTop = ui.messages.scrollHeight;
                } else if (evt.type === "done") {
                  history.push({ role: "user", content: text });
                  history.push({ role: "assistant", content: accumulated });
                }
              });
              return pump();
            });
          }
          return pump();
        })
        .catch(function () {
          botBubble.classList.remove("typing");
          botBubble.textContent = "Bağlantı hatası. Lütfen tekrar deneyin.";
        })
        .finally(function () {
          ui.sendBtn.disabled = false;
          ui.input.disabled = false;
          ui.input.focus();
        });
    }

    ui.sendBtn.addEventListener("click", send);
    ui.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") send();
    });

    addMessage(ui.messages, "bot", getGreeting());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidget);
  } else {
    initWidget();
  }
})();
