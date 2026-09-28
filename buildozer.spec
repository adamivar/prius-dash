[app]
title = Prius Live
package.name = priuslive
package.domain = io.github.adamivar
source.dir = .
source.include_exts = py
source.exclude_dirs = tools, docs, .github, bin, .buildozer, __pycache__, venv, .venv
# app.py is the Windows (tkinter) front end; the phone runs main.py
source.exclude_patterns = app.py
version = 0.5.0
requirements = python3,kivy,pyjnius,android
orientation = portrait
fullscreen = 0

# Bluetooth: BLUETOOTH + BLUETOOTH_ADMIN up to Android 11, BLUETOOTH_CONNECT (asked for at start) on Android 12+
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
# pinned: the stable python-for-android release (Python 3.11, Kivy 2.3) and the NDK it's tested with
android.ndk = 25b
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
