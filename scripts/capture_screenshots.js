/**
 * Refresh docs/screenshots/ — every README screenshot, phone-sized, in one pass.
 *
 *     node scripts/capture_screenshots.js [out-dir]     # default: docs/screenshots
 *
 * Needs, before you run it:
 *   - the Expo web server on :8081   (cd mobile-app && node node_modules/expo/bin/cli start --web)
 *   - the backend on :8000           (python -m src.main)
 *   - LM Studio up on :1234          (the chat shot waits for a real streamed answer)
 * Chrome is launched here, headless, on a throwaway profile — nothing else to start.
 *
 * ALL SIX SHOTS ARE TAKEN IN ONE CDP SESSION ON PURPOSE. Device metrics are
 * per-session: reconnecting without re-applying them silently falls back to the
 * window size at 1x, which is what once shipped a 375x812 chat.png next to five
 * 750x1624 ones. The size check at the end exists to catch exactly that.
 */
const fs = require("fs");
const os = require("os");
const net = require("net");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.resolve(process.argv[2] || path.join(ROOT, "docs", "screenshots"));
const BASE = "http://localhost:8081";
const VIEWPORT = { width: 375, height: 812, deviceScaleFactor: 2, mobile: true };

// `ws` isn't a dependency of this repo — borrow the one Expo already installed.
const WS_PATH = path.join(ROOT, "mobile-app", "node_modules", "ws");
if (!fs.existsSync(WS_PATH)) {
  console.error(`no ws module at ${WS_PATH} — run \`npm install\` in mobile-app/ first`);
  process.exit(1);
}
const WebSocket = require(WS_PATH);

const CHROMES = [
  process.env.CHROME,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const httpJson = (port, p) =>
  new Promise((resolve, reject) => {
    http
      .get({ host: "127.0.0.1", port, path: p }, (res) => {
        let b = "";
        res.on("data", (c) => (b += c));
        res.on("end", () => {
          try {
            resolve(JSON.parse(b));
          } catch (e) {
            reject(e);
          }
        });
      })
      .on("error", reject);
  });

const portOpen = (port) =>
  new Promise((resolve) => {
    const s = net
      .connect(port, "127.0.0.1", () => (s.destroy(), resolve(true)))
      .on("error", () => resolve(false));
    s.setTimeout(2000, () => (s.destroy(), resolve(false)));
  });

const freePort = () =>
  new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });

async function launchChrome() {
  const exe = CHROMES.find((p) => p && fs.existsSync(p));
  if (!exe) {
    console.error("Chrome not found — set CHROME to its executable path");
    process.exit(1);
  }
  const port = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "shots-chrome-"));
  const proc = spawn(
    exe,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "about:blank",
    ],
    { stdio: "ignore", detached: false }
  );

  for (let i = 0; i < 60; i++) {
    await sleep(500);
    try {
      await httpJson(port, "/json/version");
      return { proc, port, profile };
    } catch {
      /* not listening yet */
    }
  }
  proc.kill();
  throw new Error("Chrome never opened its debugging port");
}

async function capture(port) {
  fs.mkdirSync(OUT, { recursive: true });
  const page = (await httpJson(port, "/json/list")).find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl, { perMessageDeflate: false });
  await new Promise((r) => ws.on("open", r));

  let id = 0;
  const pending = new Map();
  ws.on("message", (raw) => {
    const m = JSON.parse(raw);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
    }
  });
  const send = (method, params = {}) => {
    const i = ++id;
    ws.send(JSON.stringify({ id: i, method, params }));
    return new Promise((resolve, reject) => pending.set(i, { resolve, reject }));
  };
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    return r.result && r.result.value;
  };

  const sizes = {};
  const shot = async (name) => {
    const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const buf = Buffer.from(r.data, "base64");
    fs.writeFileSync(path.join(OUT, name + ".png"), buf);
    sizes[name] = `${buf.readUInt32BE(16)}x${buf.readUInt32BE(20)}`;
    console.log(`${name}.png  ${sizes[name]}`);
  };
  const go = async (route, settle = 4000) => {
    await send("Page.navigate", { url: BASE + route });
    await sleep(settle);
  };
  const clickText = async (label) => {
    const box = await evaluate(`
      (() => {
        const hits = [...document.querySelectorAll('div')]
          .filter(e => (e.innerText || '').trim().startsWith(${JSON.stringify(label)}))
          .map(e => e.getBoundingClientRect())
          .filter(r => r.width > 20 && r.height > 10);
        if (!hits.length) return null;
        const r = hits[hits.length - 1];
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      })()`);
    if (!box) throw new Error(`no click target for ${label}`);
    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", {
        type,
        x: box.x,
        y: box.y,
        button: "left",
        buttons: type === "mousePressed" ? 1 : 0,
        clickCount: 1,
      });
      await sleep(60);
    }
    await sleep(3000);
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", VIEWPORT);

  await go("/");
  await shot("home");

  await go("/products", 5000);
  await shot("products");
  await clickText("HIGRO WETT");
  await shot("product-detail");

  await go("/articles", 5000);
  await shot("articles");
  await clickText("Toprak Canlılığı");
  await shot("article-detail");

  await go("/chat");
  await evaluate(`
    (() => {
      const i = document.querySelector('input');
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      set.call(i, 'Domates fidesi için organik gübreleme nasıl yapılır?');
      i.dispatchEvent(new Event('input', { bubbles: true }));
      i.focus();
      i.dispatchEvent(new KeyboardEvent('keydown',
        { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
      return true;
    })()`);

  // The reply streams in; wait for the text to stop growing rather than a guess.
  // Watching for "Yazıyor..." to vanish fires on the first token and catches a
  // half-written answer.
  let last = -1;
  for (let i = 0; i < 40; i++) {
    await sleep(3000);
    const len = await evaluate("document.body.innerText.length");
    if (len === last && len > 400) break;
    last = len;
  }
  await sleep(1500);
  await shot("chat");

  ws.close();
  return sizes;
}

(async () => {
  if (!(await portOpen(8081))) {
    console.error("nothing on :8081 — start the Expo web server first (see the header)");
    process.exit(1);
  }
  if (!(await portOpen(8000))) {
    console.error("nothing on :8000 — start the backend first (python -m src.main)");
    process.exit(1);
  }

  const chrome = await launchChrome();
  let sizes;
  try {
    sizes = await capture(chrome.port);
  } finally {
    chrome.proc.kill();
    // Windows keeps the profile's files open for a moment after the kill; a
    // leftover temp dir is harmless, so never let cleanup fail the run.
    await sleep(500);
    try {
      fs.rmSync(chrome.profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    } catch (e) {
      console.warn(`could not remove ${chrome.profile}: ${e.code}`);
    }
  }

  const distinct = [...new Set(Object.values(sizes))];
  if (distinct.length > 1) {
    console.error(`\nMIXED SIZES ${distinct.join(" / ")} — the device override was lost mid-run:`);
    for (const [name, size] of Object.entries(sizes)) console.error(`  ${name}.png ${size}`);
    process.exit(1);
  }
  console.log(`\nall ${Object.keys(sizes).length} shots ${distinct[0]} -> ${OUT}`);
})().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
