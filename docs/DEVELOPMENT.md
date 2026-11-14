# Разработка PConDistance / Development

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

Нужны Windows, Python 3.10+ с Tkinter и зависимости из [requirements](../requirements.txt). Запуск из исходников не равен обычной установке: для H.264 и звука нужен доступный комплект FFmpeg с `ffplay`. Поиск использует ручной выбор, затем `media` рядом с приложением, PATH и стандартные места установки; он только проверяет наличие файлов, без запуска и скачивания. При необходимости укажи свою папку через **«Настроить видео и звук»**, без изменения PATH. Проверка выбранных EXE запускается только после согласия; см. [ручную настройку](GETTING_STARTED.md#необязательно-другая-сборка-или-восстановление-настройки).

Requires Windows, Python 3.10+ with Tkinter and the project dependencies. Source runs differ from a standard installation: H.264 and audio need an available FFmpeg/`ffplay` pair. Discovery uses the manual override, app-local `media`, PATH, then standard installation locations; it only checks file availability, without execution or downloads. If needed, select your own folder via **«Настроить видео и звук»**, without editing PATH. Selected EXEs are probed only after consent; see the [manual setup guide](GETTING_STARTED.md#optional-manual-override-or-recovery).

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

### QR dependency / Зависимость QR

Android uses ZXing core **3.3.3** (Apache-2.0), pinned for the API-21 Java build. The build downloads it from Maven Central and requires SHA-256 `5820f81e943e4bce0329306621e2d6255d2930b0a6ce934c5c23c0d6d3f20599`. The JAR is not committed; run the build once before Java decoder tests. The license is included in `app/assets/ZXING-LICENSE.txt` and the APK. This older version is not a claim of a security audit; dependency upgrades require API-21 device/build testing. Scanner inputs accept only validated PConDistance pairing links, not arbitrary actions or URLs.

Android использует ZXing core **3.3.3**, Apache-2.0. Сборка скачивает закреплённый JAR из Maven Central и проверяет SHA-256; бинарник не хранится в Git. Перед Java-тестами декодера сначала запусти сборку. Лицензия включена в APK. Версия выбрана для совместимости с текущей сборкой API 21; это не заявление о независимом аудите безопасности. Сканер принимает только проверенные ссылки сопряжения PConDistance.

## Windows installer

Следуй [проверяемому рецепту упаковки](../packaging/README.md), а не копируй рабочую папку в дистрибутив. **Windows-установщик 1.0.4** включает FFmpeg/ffplay с автоматическим выбором, Python и UI/TLS/QR-зависимости. Проверен frozen self-test; это не универсальная аппаратная проверка и не тест новых сценариев на реальном телефоне. Ранее распространявшиеся slim-выпуски не включали медиакомплект.

Для медиакомплекта подготовлена минимальная LGPL-сборка FFmpeg с SDL2 и NVENC headers. Перед распространением проверь фактическую конфигурацию, лицензии всех компонентов, соответствующие исходники и инструкции воспроизводимой сборки; приложи требуемые материалы к дистрибутиву. Это обязанность выпускающего сборку, не шаг обычного пользователя. Не считай чужую готовую сборку автоматически пригодной для публикации.

Follow the [packaging recipe](../packaging/README.md), not a copy of a working directory. The **Windows 1.0.4 installer** includes automatically selected FFmpeg/ffplay, Python and UI/TLS/QR dependencies. Frozen self-test passed; this is not universal hardware validation or real-phone testing of new features. Earlier slim releases did not include the media bundle.

A minimal LGPL FFmpeg build with SDL2 and NVENC headers has been prepared. Before distribution, verify the actual configuration and every component's license, corresponding sources and reproducible-build instructions, and ship the required materials. This is release preparation, not the normal user's task. A third-party prebuilt bundle is not automatically cleared for redistribution.

При изменении исходников frozen-приложение нужно пересобрать. `--self-test OUTPUT_JSON` проверяет импорты и встроенные зависимости в изолированной временной папке, но не заменяет установку, подключение телефона или проверку сети. Контроль целостности артефакта тоже не доказывает работоспособность и готовность к публикации.

Source changes require rebuilding the frozen app. `--self-test OUTPUT_JSON` checks imports and embedded dependencies using isolated temporary data; it is not an install/pairing/network integration test. Artifact integrity is not evidence of functionality or release readiness.

## Продолжение передачи файлов / Resumable uploads

Для готовящегося выпуска реализована возобновляемая передача телефон → ПК: пауза, восстановление после потери Wi-Fi и предложение незавершённой передачи после перезапуска. Это не утверждение о проверке текущего APK на реальном телефоне. Android сохраняет доступ к исходнику и сведения о незавершённой передаче; продолжение требует того же неизменённого файла и того же ПК. Перед первой отправкой вычисляется полный SHA-256, при повторном открытии проверяется идентичность исходника; подготовка большого файла может быть долгой. Держать приложение в фоне не обещаем.

Сервер хранит подтверждённый прогресс и частичные данные отдельно от готового файла, с восстановлением после перезапуска. Данные передаются блоками до 4 МиБ с проверкой смещения и SHA-256; окончательное имя становится доступно только после проверки всего файла, без перезаписи существующего. Публикация готового файла использует атомарное создание жёсткой ссылки с восстановлением после сбоя, поэтому файловая система назначения должна поддерживать hard links (например NTFS); FAT/exFAT отклоняются при создании сессии с понятной ошибкой. Папка назначения фиксируется при начале передачи: смена настройки не переносит уже начатую передачу. Пауза сохраняет частичные данные, удалённый отказ удаляет их; срок хранения незавершённых передач — 7 дней. «Только на телефоне» очищает только локальную запись и кэш, без сетевого запроса; частичные данные на ПК остаются до истечения срока. Отсутствующая или истёкшая серверная сессия требует явного отказа и повторного выбора файла, без скрытого перезапуска передачи. Восстановление не должно принимать изменённый исходник, повреждённые метаданные или чужую сессию. Существующий однопроходный маршрут остаётся совместимым, но новая возобновляемая передача не должна молча переключаться на него.

Resumable phone → PC uploads are implemented for the upcoming release: pause, recovery after Wi-Fi loss and a pending-transfer offer after restarting. This is not evidence of current-APK testing on a real phone. Android retains source access and pending-transfer details; resuming requires the same unchanged file and PC. A full SHA-256 is calculated before first sending and source identity is checked on reopening; large-file preparation may be slow. Background operation is not promised.

The server persists committed progress and partial data separately from finished files and recovers them after restart. Blocks of up to 4 MiB use offset and SHA-256 checks; final publication follows full-file verification without overwriting existing files. Final publication uses atomic hard-link creation with crash recovery, requiring a hard-link-capable destination filesystem such as NTFS; reject FAT/exFAT when creating the session with a readable error. The destination is fixed when the transfer begins, including subsequent resumes. Pause retains partial data, remote discard removes it, and incomplete transfers are retained for 7 days. Phone only clears the local pending entry/cache without a network request, leaving PC partial data until expiry. A missing or expired server session requires explicit discard and source reselection, never a silent restart. Recovery must reject changed sources, corrupt metadata and other sessions. The legacy one-shot route remains compatible, but a resumable transfer must not silently fall back to it.

Перед релизом отдельно проверить / Verify before release:

- Потерю Wi-Fi посреди блока, повторы запроса, паузу, продолжение, отказ и истечение 7 дней. / Mid-block Wi-Fi failure, request retries, pause, resume, discard and 7-day expiry.
- Перезапуск Android и сервера, доступ к исходнику, изменение файла, потерю разрешения и длительную подготовку. / Android/server restart, source access, changed files, permission loss and long preparation.
- Проверку полного файла, совпадение имён, смену папки после начала, недостаток места и повреждённое состояние без выдачи частичной копии как готовой. / Full-file verification, name collisions, destination changes, disk exhaustion and corrupt state without exposing partial data as complete.

## Проверка обновлений / Update checks

**Реализовано для 1.0.4.** Автоматический сценарий установки через предложение обновления и новые сценарии на реальном Android отдельно не подтверждены. Windows и Android проверяют новую версию при запуске и предлагают **«Позже» / «Обновить»**. Список версий приходит с фиксированного публичного адреса и проверяется по цифровой подписи. Пользователю не нужны учётная запись, собственный ключ или настройка адреса. Это не облачный транспорт управления. Первую версию с обновлятором необходимо установить вручную поверх прежней.

Windows должен сначала скачать и проверить установщик по подписанным сведениям о выпуске, и только затем закрыть свои дочерние компоненты и GUI для установки. Повторный запуск GUI допускается только после успешного завершения установки; отмена и ненулевой код не должны изображаться успехом. Сопряжение, папка приёма, каталог программ и ручная настройка медиа сохраняются; установка не должна молча сбрасывать профиль. Подпись списка обновлений не заменяет Windows Authenticode.

Android должен передать проверенный APK системному установщику. Согласие пользователя и разрешение установки из этого источника обязательны; скрытая установка и обход системного подтверждения не поддерживаются. Для обновления на месте сохраняются package ID и подпись APK. Возврат в приложение и уведомление после установки — best-effort с учётом фоновых ограничений и разрешений Android, а не гарантия автоматического открытия.

**Implemented for 1.0.4.** The automatic offered-update installation flow and new scenarios on a real Android device have not been separately confirmed. The flow checks at Windows/Android startup and offers **Later / Update**. Release information comes from a fixed public feed and is digitally verified. Users need no account, private key or feed configuration. This is not a cloud control transport. The first updater-capable version must be installed manually over the old one.

Windows must download and verify the installer against signed release information before closing its child components and GUI. Reopen the GUI only after a successful installer exit; cancellation or failure must not appear successful. Preserve pairing, received-file folder, application catalog and media override rather than resetting the user profile. Feed signatures do not replace Windows Authenticode.

Android must hand the verified APK to the system installer. User approval and install-from-this-source permission remain mandatory; no silent-install or consent bypass is supported. Keep package ID and APK signing identity for in-place updates. Reopening or a post-install notification is best-effort under Android background/permission restrictions, not a guaranteed automatic launch.

Перед заявлением о готовности проверь / Before claiming readiness, test:

- Подпись и содержимое списка, неподходящую платформу, старую версию, повреждённую загрузку, потерю сети; отказ без запуска установщика. / Feed signature/content, wrong platform, old version, corrupt downloads and network failure; refuse without executing the installer.
- **«Позже»**, явное согласие, успешную установку, отмену и ошибку; закрытие только своих компонентов и повторный запуск только после успеха. / Later, explicit approval, success, cancellation and failure; close only owned components and relaunch only on success.
- Обновление поверх старой установки с сохранением настроек на обеих платформах; обязательный системный запрос Android и ручной запуск, если автоматический возврат запрещён. / In-place updates preserving settings on both platforms; mandatory Android approval and manual reopening if automatic return is blocked.

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
- Чистая установка с пустым PATH и без внешнего FFmpeg: комплектные FFmpeg/ffplay найдены без диалога и запуска `-version`; отдельно проверить H.264 с поддерживаемыми NVIDIA NVENC/драйвером и ограничения неподдерживаемого оборудования. / Clean install without external FFmpeg or PATH entries: bundled tools found without a dialog or `-version` probe; separately test H.264 on supported NVIDIA NVENC hardware/drivers and unsupported-hardware limitations.
- Необязательная ручная настройка без изменения PATH: выбор обоих EXE, отказ от запуска проверки, ошибка/тайм-аут, сохранение только после успеха, перезапуск сервера и просмотрщика, недоступная выбранная папка без скрытого fallback, возврат к комплекту через автоматический поиск. / Optional manual override without PATH edits: both EXEs, declined probe consent, failure/timeout, save only on success, server/viewer restart, unavailable override without silent fallback and reset to the bundle.
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

Бренд PConDistance не совпадает с некоторыми прежними техническими именами; они сохранены для совместимости, а не являются отдельными приложениями:

Some technical names predate the PConDistance brand and remain for compatibility:

- Android package: `ru.alexv.pcmote`.
- Pairing URI: `pcmote://pair`.
- Windows profile directory: `%LOCALAPPDATA%/VzaimoPult`; launcher использует её для данных, компоненты получают `VZAIMOPULT_DATA_DIR`. / Launcher data lives here and is passed to components through `VZAIMOPULT_DATA_DIR`.
- Готовящийся Windows setup **1.0.4** и Android **1.15** — отдельные версии компонентов; релиз Windows может ссылаться на неизменённый APK предыдущего выпуска. Прямой QR скачивания APK по-прежнему может вести к релизу **1.0.2**: это не версия нового Windows-установщика. / Upcoming Windows setup 1.0.4 and Android 1.15 are independent component versions; a Windows release can reuse an earlier APK. The direct APK download QR may still target release 1.0.2; it is not the new Windows installer version.

Смена namespace, URI, подписывающего ключа или каталога данных требует плана миграции и проверки обновления поверх установленного приложения. Не удаляй пользовательские настройки для «исправления» несовместимости без понятного предупреждения и согласия.

Changing the namespace, URI scheme, signing key or data directory requires migration planning and in-place update testing. Do not silently delete user settings to resolve incompatibility.
