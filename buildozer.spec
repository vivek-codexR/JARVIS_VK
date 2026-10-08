[app]
title = VYRo V1.8.1
package.name = vyroassistant
package.domain = org.vyro
source.dir = .
source.include_exts = py,json,png,jpg,kv
version = 1.8.1
requirements = python3,kivy,pyjnius
orientation = portrait
fullscreen = 0
android.api = 36
android.minapi = 24
android.ndk = 29
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.permissions = INTERNET,RECORD_AUDIO,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MICROPHONE,POST_NOTIFICATIONS
services = vyroservice:service.py
p4a.fork = kivy
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
