# App builds (Android + iOS in one place)

Both platforms' build artifacts live here so they don't get mixed up:

```
builds/
├── android/   # .apk / .aab  (installable directly on Android)
└── ios/       # .app (simulator) / .ipa (device)  — see note below
```

The binaries themselves are gitignored (large); only this folder structure is tracked.

## Serving builds over the LAN (port 8090)

To download a build from another device on the same Wi-Fi:

```bash
python -m http.server 8090 --bind 0.0.0.0 --directory mobile-app/builds
```

Then open `http://<this-machine-LAN-IP>:8090` (e.g. http://192.168.1.103:8090).

## Android

```bash
cd mobile-app
eas build -p android --profile preview   # cloud build -> APK URL, or:
# local: npx expo prebuild -p android && cd android && ./gradlew assembleRelease
```
Put the resulting `.apk` in `builds/android/`. Open the 8090 URL on the Android
phone and download → install. (Android allows this.)

## iOS  ⚠️ important

iOS **cannot** be built on Windows and a downloaded build **cannot** be
sideloaded onto an iPhone the way an APK can. Path for a machine with no Mac and
no iPhone:

```bash
cd mobile-app
eas build -p ios --profile preview   # cloud build, unsigned SIMULATOR .app
```
Download the artifact into `builds/ios/`. To actually *see it run*, upload that
`.app` to **https://appetize.io** (runs an iOS simulator in the browser). The
8090 download server is only useful here for grabbing/staging the file — it will
NOT install on an iPhone (simulator builds run on simulators only; device installs
need an Apple Developer account + TestFlight/ad-hoc signing).
