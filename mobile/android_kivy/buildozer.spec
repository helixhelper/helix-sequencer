[app]

title = Helix Mobile
package.name = helixmobile
package.domain = org.helixsequencer

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md

version = 0.1.0

requirements = python3,kivy,requests

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 35
android.minapi = 23
android.ndk = 25b
android.accept_sdk_license = True

# Keep debug simple for the MVP.
log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
