[app]

# 앱 이름 (홈 화면에 표시)
title = 로또 6/45 번호생성기

# 패키지 이름 (영문 소문자/숫자만)
package.name = lotto645
package.domain = org.surfer.lotto

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,csv,ttf,otf
source.include_patterns = assets/*
source.exclude_dirs = bin,.buildozer,__pycache__,.github
source.exclude_patterns = shot_*.png,*.spec.bak

version = 1.0

# python3 : 파이썬 런타임
# kivy    : 화면
# requests/urllib3/idna/charset-normalizer/certifi/openssl : 동행복권 HTTPS 조회
requirements = python3,kivy==2.3.1,openssl,certifi,charset-normalizer,idna,urllib3,requests

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #d7ebfb

# 인터넷 권한만 사용합니다 (최신 회차 조회용)
android.permissions = android.permission.INTERNET,android.permission.ACCESS_NETWORK_STATE

android.api = 34
android.minapi = 24
android.ndk_api = 24
android.accept_sdk_license = True

# arm64-v8a 는 2018년 이후 거의 모든 안드로이드폰입니다.
# 아주 오래된 기기까지 지원하려면 뒤에 , armeabi-v7a 를 추가하세요(빌드 시간 2배).
android.archs = arm64-v8a

android.allow_backup = True
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 0
