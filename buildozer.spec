[app]

title = 로또 6/45 번호생성기

package.name = lotto645
package.domain = org.surfer.lotto

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,csv,ttf,otf
source.include_patterns = assets/*
source.exclude_dirs = bin,.buildozer,__pycache__,.github
source.exclude_patterns = shot_*.png,*.spec.bak

version = 1.0

requirements = python3,kivy,openssl

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #d7ebfb

android.permissions = android.permission.INTERNET,android.permission.ACCESS_NETWORK_STATE

android.api = 33
android.minapi = 24
android.ndk_api = 24
android.accept_sdk_license = True

p4a.source_dir = ~/p4a-src

android.archs = arm64-v8a

android.allow_backup = True
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 0
