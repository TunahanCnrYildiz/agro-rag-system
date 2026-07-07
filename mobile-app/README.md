# Ekolojik Tarım Asistanı — Mobile App

React Native (Expo) chat app for the Agro-Botany RAG backend, branded to match
ekolojiktarim.com.tr (colors and logo extracted from the live site).

## Run

```bash
npm install
npm run web       # browser preview via react-native-web
npm run android    # Android emulator/device (Expo Go)
npm run ios        # iOS simulator (macOS only)
```

## API endpoint

`src/api.ts` points at `API_BASE = "http://127.0.0.1:8000"` by default. This
only works when the app and the API run on the same machine (e.g. web
preview). For a physical device or emulator, change `API_BASE`:

- Android emulator → `http://10.0.2.2:8000`
- Physical device → `http://<your-machine-LAN-IP>:8000`
- Production → your deployed API's public URL

## Notes

- Uses the API's **unified (non-streaming)** response mode (`stream: false`).
  React Native's `fetch` doesn't reliably support reading a streaming response
  body (no `ReadableStream` support), unlike the web widget. A "Yazıyor..."
  indicator covers the wait instead of token-by-token streaming.
- `src/MarkdownText.tsx` renders the LLM's lightweight markdown (`**bold**`,
  `*italic*`, bullet lists) as native Text/View components — React Native has
  no `innerHTML`, so this can't reuse the web widget's HTML-based renderer.
- Brand assets in `assets/` (icon, adaptive icon layers, splash, favicon) were
  generated from the site's logo SVG (`web-widget/site/logo.svg`).
