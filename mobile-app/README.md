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

## Screenshots

`node scripts/capture_screenshots.js` (from the repo root) refreshes the README's
`docs/screenshots/` with the web build, driven headlessly at phone size. It needs
`npm run web`, the backend and LM Studio running; it starts Chrome itself.

## API endpoint

Set `EXPO_PUBLIC_API_BASE` (in `mobile-app/.env` — see `.env.example` — or the
shell / EAS build env) to wherever the backend runs; `src/api.ts` reads it at
bundle time and falls back to a LAN IP only when it is unset. `127.0.0.1` only
works when the app and API share a machine (e.g. web preview); a physical device
or emulator needs a reachable address:

- Android emulator → `http://10.0.2.2:8000`
- Physical device → `http://<your-machine-LAN-IP>:8000`
- Production → your deployed API's public URL

## Notes

- Streams the answer token-by-token over SSE using `XMLHttpRequest`'s
  `onprogress` (React Native's `fetch` has no `ReadableStream` body, so the
  browser widget's reader approach doesn't work here). A "Yazıyor..." indicator
  covers the wait until the first token arrives.
- `src/MarkdownText.tsx` renders the LLM's lightweight markdown (`**bold**`,
  `*italic*`, bullet lists) as native Text/View components — React Native has
  no `innerHTML`, so this can't reuse the web widget's HTML-based renderer.
- Brand assets in `assets/` (icon, adaptive icon layers, splash, favicon) were
  generated from the site's logo SVG (`web-widget/site/logo.svg`).
