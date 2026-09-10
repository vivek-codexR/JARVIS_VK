[app]

title = VYRo V1.6
package.name = jarvisassistant
package.domain = org.jarvis

source.dir = .
source.include_exts = py,json,png,jpg,kv

version = 1.6.0

requirements = python3,kivy,pyjnius

orientation = portrait
fullscreen = 0

android.api = 36
android.minapi = 24
android.ndk = 29
android.archs = arm64-v8a,armeabi-v7a

android.accept_sdk_license = True

android.permissions = INTERNET,RECORD_AUDIO


p4a.fork = kivy
p4a.branch = develop

[buildozer]

log_level = 2
warn_on_root = 1
