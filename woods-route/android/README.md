# Woods Route Planner for Android

This is a standalone Android application wrapper for the live Woods Route Planner. It installs as an app, provides a full-screen map, and requests location permission only when the web app asks to use GPS.

## Build an APK

The GitHub Actions workflow at `.github/workflows/woods-route-android.yml` builds the APK automatically when these files change, or can be run manually from the repository Actions tab.

Download the `WoodsRoutePlanner-Android-APK` artifact from the latest successful workflow run. The APK is an installable Android package; Android may ask you to allow installation from the browser or file manager you used to download it.

## Build locally

Install Android Studio / Android SDK, Java 17, and Gradle 8.9 or newer, then run from this directory:

```sh
gradle assembleDebug
```

APK output: `app/build/outputs/apk/debug/app-debug.apk`.

The app loads `https://woods-route-planner.onrender.com` and therefore needs an internet connection. The map data and routing services remain live third-party services.
