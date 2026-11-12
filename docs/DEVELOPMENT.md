# Разработка DroidBridge / Development

[README](../README.md) · [Пользовательская инструкция / User guide](GETTING_STARTED.md) · [Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md)

Эта страница — для работы с исходниками. Пользователю готовых приложений не нужны Python, Android SDK, команды тестирования и сведения о внутреннем протоколе.

This page covers source development. Users of the packaged apps do not need Python, the Android SDK, test commands or protocol details. Commands below run from the repository root on Windows.

## Компоненты / Components

- [Android app](../app/src/ru/alexv/pcmote/MainActivity.java): Java, ресурсы RU/EN, сопряжение, просмотр ПК, передача файлов, захват экрана телефона и опциональное Accessibility-управление.
- [Windows launcher](../desktop/launcher.py): Tk-интерфейс, запуск/остановка дочернего сервера, временное окно сопряжения, локальные настройки программ и папки приёма, запуск просмотрщика. При открытии сервера автоматически не запускает.
- [Control listener](../listener/pc-listener.py): HTTP-команды Windows, состояние, экран, загрузка файла и автопоиск.
- [Phone viewer](../client/pc-viewer.pyw): Tk/Pillow-клиент, подключающийся к трансляции телефона; FFmpeg/ffplay для соответствующих видео- и аудиорежимов.
- [Windows packaging](../packaging/README.md): отдельная инструкция сборки установщика, зависимости и условия распространения сторонних компонентов.

## Запуск из исходников / Run from source

Нужны Windows, Python 3.10+ с Tkinter и зависимости из [requirements](../requirements.txt). Для H.264 и звука отдельно скачай FFmpeg с `ffplay` и укажи папку через **«Настроить видео и звук»** в launcher; менять PATH не требуется. Порядок проверки и перезапуска — в [пользовательской инструкции](GETTING_STARTED.md#3-установи-ffmpeg-для-видео-и-звука).

Requires Windows, Python 3.10+ with Tkinter and the project dependencies. Download FFmpeg with `ffplay` separately and select its folder via the launcher's **«Настроить видео и звук»** control. No PATH change is required; follow the [user guide](GETTING_STARTED.md#ffmpeg-and-ffplay-separate-download-no-path-editing) for verification and restart steps.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe desktop/launcher.py
```

Используй обычный профиль пользователя, не административный запуск по умолчанию. Кнопки запуска и сопряжения те же, что в [пользовательской инструкции](GETTING_STARTED.md). Основной сетевой транспорт не зашифрован — разрабатывай и проверяй только в доверенной LAN.

Use a regular user account rather than running elevated by default. Follow the user guide for pairing. The main transport is unencrypted: keep development and testing on a trusted LAN.

Для изолированной работы с отдельными компонентами / standalone components:

```powershell
.venv/Scripts/python.exe listener/pc-listener.py
.venv/Scripts/python.exe client/pc-viewer.pyw
```

При прямом запуске listener без `VZAIMOPULT_DATA_DIR` данные создаются рядом с его исходником, в том числе `listener/token.txt`; просмотрщик по умолчанию читает этот ключ. При запуске через desktop launcher данные находятся в профиле Windows, а путь передаётся компонентам через переменную окружения. Не запускай второй сервер на том же порту.

A direct listener launch without `VZAIMOPULT_DATA_DIR` stores runtime files beside the listener source, including `listener/token.txt`; the standalone viewer defaults to that key. The desktop launcher uses Windows-profile storage and passes the directory to components through the environment. Do not start two listeners on the same port.

Не публикуй runtime-ключи, ссылки/QR сопряжения, персональные каталоги программ, адреса устройств, записи экрана и необработанные логи. Для примеров используй вымышленные данные. Демо-SVG в README — иллюстрации, не свидетельство проверки реального интерфейса.

Do not publish runtime keys, pairing links/QRs, personal catalogs, device addresses, recordings or unchecked logs. Use synthetic examples. README SVGs are illustrations, not evidence of a real-device UI test.

### Брандмауэр для разработки / Development firewall

[Start script](../start.ps1) без параметров запускает listener. Параметр `-SetupFirewall` **только создаёт** правила для TCP 8765 и UDP 8766: профиль Private, удалённый адрес LocalSubnet; нужны права администратора, после создания скрипт завершается. Это не настройка TCP 8767 для сопряжения и не действие установщика. Не разрешай порты для Public и не отключай брандмауэр целиком.

The start script runs the listener by default. `-SetupFirewall` only creates Private/LocalSubnet rules for TCP 8765 and UDP 8766, requires elevation and exits afterwards. It does not configure pairing TCP 8767. Setup does not automatically create these rules.

## Android APK

Сборка без Gradle: [build script](../build.ps1). Нужны PowerShell, **JDK 21**, Android SDK **platform 34**, **build-tools 34.0.0**, настроенные `JAVA_HOME` и `ANDROID_HOME`. Если `ANDROID_HOME` не указан, скрипт ищет SDK в `%LOCALAPPDATA%/Android/SDK`.

Build without Gradle using PowerShell, JDK 21, SDK platform 34 and build-tools 34.0.0. Set `JAVA_HOME` and `ANDROID_HOME`; the script otherwise looks for the SDK at `%LOCALAPPDATA%/Android/SDK`.

```powershell
powershell -File build.ps1
```

Результат — `pc-remote.apk` в корне; временная папка `build` пересоздаётся. При отсутствии `debug.keystore` скрипт создаёт debug-ключ, затем подписывает и проверяет APK. Существующий debug-ключ используется повторно. Этот рецепт не заменяет управление релизной подписью: чужой ключ не позволит обновить уже установленный APK без удаления приложения, а удаление может потерять настройки. Храни релизные keystore и пароли вне Git; не используй опубликованные debug-пароли как секрет.

The output is `pc-remote.apk`; the temporary `build` directory is recreated. A missing `debug.keystore` is generated, otherwise reused. The script signs and verifies the APK. This is not release-signing management: a differently signed APK cannot update an installed app in place. Uninstalling may lose settings. Keep release keystores/passwords outside Git; debug credentials are not secrets.

Минимальная версия Android — API 21 (Android 5); жесты управления — API 24 (Android 7); захват звука воспроизведения — API 29 (Android 10) и только для разрешающих его приложений. Системные разрешения и ограничения защищённых экранов сохраняются.

Minimum Android is API 21; control gestures require API 24 and playback-audio capture API 29 plus an app that allows capture. System consent and protected-screen restrictions still apply.

## Windows installer

Следуй [проверяемому рецепту упаковки](../packaging/README.md), а не копируй рабочую папку в дистрибутив. Windows 1.0.2 — slim-сборка без FFmpeg/ffplay с локальным выбором папки; Python и UI/TLS/QR-зависимости включены. Локальная сборка со сторонним FFmpeg не означает, что его можно автоматически публиковать: лицензии и соответствующие исходники проверяются отдельно.

Follow the packaging recipe instead of distributing a working directory. Windows 1.0.2 is the slim installer without FFmpeg/ffplay, with a local folder selector; Python and UI/TLS/QR dependencies are frozen into it. A local third-party media bundle is not automatic authorization to redistribute it: review licenses and corresponding-source requirements separately.

При изменении исходников frozen-приложение нужно пересобрать. `--self-test OUTPUT_JSON` проверяет импорты и встроенные зависимости в изолированной временной папке, но не заменяет установку, подключение телефона или проверку сети. Контроль целостности артефакта тоже не доказывает работоспособность и готовность к публикации.

Source changes require rebuilding the frozen app. `--self-test OUTPUT_JSON` checks imports and embedded dependencies using isolated temporary data; it is not an install/pairing/network integration test. Artifact integrity is not evidence of functionality or release readiness.

## Тесты / Tests

```powershell
python -m unittest discover -s listener -p "test_*.py" -v
python -m unittest discover -s client -p "test_*.py" -v
python -m unittest discover -s desktop -p "test_*.py" -v
python -m unittest discover -s app -p "test_*.py" -v
python -m unittest discover -s packaging -p "test_packaging.py" -v
```

Часть проверок компилирует Java или зависит от Windows API; отсутствие toolchain и пропущенные тесты нужно отмечать в отчёте, а не считать успешной полной проверкой. Используй Python с установленными зависимостями проекта. Не запускай параллельно сборку/форматирование файлов, которые меняет другой участник.

Some checks compile Java or depend on Windows APIs. Report missing toolchains and skipped tests explicitly rather than claiming a complete pass. Use a Python environment with project dependencies. Coordinate concurrent builds/formatting to avoid overwriting another contributor's edits.

Перед релизом отдельно проверь на реальных устройствах / real-device release checklist:

- Чистая установка и удаление Windows, запуск без отдельно установленного Python. / Clean install/uninstall and operation without a separate Python installation.
- Новый QR, совпадение кода, отказ/тайм-аут, сохранение пары и повторное подключение. / Fresh pairing, matching-code approval, rejection/expiry, saving and reconnecting.
- Команды, смена IP и автопоиск, корректный отказ с другим ключом. / Commands, changed IP/discovery and rejection with a wrong key.
- Видео в обе стороны, звук на поддерживаемом Android, явное включение/отзыв управления. / Both video directions, supported Android audio and control opt-in/revocation.
- Передача файла, смена папки для следующей загрузки, недоступная папка, совпадение имён, отмена и обрыв. / Uploads, next-upload folder changes, inaccessible folders, name collisions, cancellation and disconnects.
- Настройка видео без изменения PATH: выбор обоих EXE, отказ от запуска проверки, ошибка/тайм-аут, сохранение только после успеха, перезапуск сервера и просмотрщика, недоступная выбранная папка без скрытого fallback. / Media setup without PATH edits: both EXEs, declined probe consent, failure/timeout, save only on success, server/viewer restart and an unavailable selected folder without silent fallback.
- Остановка сервера и закрытие launcher без оставшихся дочерних процессов. / Server stop and launcher close without leftover child processes.

Исторически проверялись передача файла и клики в обе стороны на одной связке Android/Windows; это не подтверждение для каждого устройства и не проверка текущего артефакта. Полный файл на 50 ГиБ в прежней проверке не передавался — проверялась логика лимита. Для нового релиза записывай версии устройств, хеши артефактов, выполненные сценарии и ограничения отдельно от пользовательского README.

Earlier development checks covered file transfer and clicks both ways on one Android/Windows setup, not universal compatibility or the current artifact. The previous check did not transfer an actual 50 GiB file; it tested limit logic. Record device versions, artifact hashes, scenarios and limitations for each release separately from the user-facing README.

## Сеть и протоколы / Network and protocols

Это описание существующей реализации, **не гарантия безопасного доступа из Интернета**.

This describes the current implementation, **not a claim that it is safe to expose to the Internet**.

План перехода к шифрованию основных каналов / planned transport-encryption migration: [Transport security](TRANSPORT_SECURITY.md). Это план для разработчиков, не реализованная возможность.

- **TCP 8765, PC:** HTTP listener для команд, статуса, экрана и загрузки файлов. Старые маршруты используют ключ в параметрах URL, более новые операции — `Authorization: Bearer …`. См. [listener](../listener/pc-listener.py), [input](../listener/remote_input.py), [upload](../listener/file_upload.py). Авторизация не шифрует содержимое и не защищает ключ от наблюдения в недоверенной сети. / Commands, status, screen and uploads; legacy URL-key and newer Bearer-header routes coexist. Authentication does not encrypt traffic.
- **UDP 8766, PC:** [LAN discovery](../listener/lan_discovery.py). Сообщения версии 1 `PCMOTE_DISCOVERY` подписаны HMAC-SHA256 и связаны nonce; ключ в discovery-пакете не передаётся. Это поиск уже известного ПК, не механизм первого сопряжения и не шифрование других каналов. / HMAC-SHA256 discovery with nonces locates an already paired PC; it neither pairs unknown PCs nor encrypts other traffic.
- **TCP 8767, PC:** временный HTTPS [pairing server](../listener/pairing.py), выбранный частный IPv4-адаптер. Ссылка `pcmote://pair` несёт одноразовый ticket и отпечаток TLS-сертификата, не постоянный ключ; код сравнивается пользователем, подтверждение выполняется локально на ПК. Ключ выдаётся в рамках подтверждённого обмена. Закрытие/истечение/завершение сессии останавливает временный listener. / Temporary HTTPS pairing with certificate pinning, one-time ticket and local matching-code approval; the long-term key is not in the QR.
- **TCP 8768, phone:** [Android mirroring service](../app/src/ru/alexv/pcmote/MirrorService.java), к которому подключается ПК. Пакеты: длина 4 байта big-endian, тип 1 байт, payload. Типы: 0 hello/JSON, 1 JPEG, 2 PCM, 3 H.264, 4 конфигурация H.264, 5 команды управления. Проверка общего ключа не делает канал зашифрованным. / PC connects to the phone's framed stream; a shared-key check is not transport encryption.
- **UDP 9:** Wake-on-LAN magic packet, не подтверждение запуска ПК. / Wake-on-LAN magic packet, not a startup acknowledgement.

Не добавляй советы про публичный проброс портов, обход UAC или защищённых Android-экранов. Локальные редакторы программ и папки приёма не должны становиться удалёнными API изменения настроек. Пути запуска программ остаются на ПК; телефон получает ID и подписи.

Do not document public port forwarding, UAC bypass or protected-screen bypass as supported features. Keep application/upload-folder editing local; the phone receives catalog IDs and labels, not executable paths.

## Совместимость и локальные данные / Compatibility and local data

Бренд DroidBridge не совпадает с некоторыми прежними техническими именами; они сохранены для совместимости, а не являются отдельными приложениями:

Some technical names predate the DroidBridge brand and remain for compatibility:

- Android package: `ru.alexv.pcmote`.
- Pairing URI: `pcmote://pair`.
- Windows profile directory: `%LOCALAPPDATA%/VzaimoPult`; launcher использует её для данных, компоненты получают `VZAIMOPULT_DATA_DIR`. / Launcher data lives here and is passed to components through `VZAIMOPULT_DATA_DIR`.
- Windows setup **1.0.2** и Android **1.14** — отдельные версии компонентов, а не обязанные совпадать номера; релиз Windows может ссылаться на неизменённый APK предыдущего выпуска. / Windows setup 1.0.2 and Android 1.14 are independent component versions; a Windows release may link to the unchanged APK from an earlier release.

Смена namespace, URI, подписывающего ключа или каталога данных требует плана миграции и проверки обновления поверх установленного приложения. Не удаляй пользовательские настройки для «исправления» несовместимости без понятного предупреждения и согласия.

Changing the namespace, URI scheme, signing key or data directory requires migration planning and in-place update testing. Do not silently delete user settings to resolve incompatibility.
