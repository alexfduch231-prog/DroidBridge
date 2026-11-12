# Изменения / Changelog

## 1.0.6 — в разработке / in development

Готовящийся выпуск, ещё не опубликован. Инструкции ниже относятся к новому интерфейсу; последняя доступная сборка находится на [странице релизов](https://github.com/alexfduch231-prog/DroidBridge/releases/latest).

- Основные действия Windows перенесены в одно основное окно с разделами слева: **«Подключение»**, **«Экран телефона»**, **«Программы»**, **«Приём файлов»**, **«Включение ПК»** и **«Настройки»**. Выбор файлов, подтверждения и системные запросы могут оставаться диалогами.
- QR скачивания Android-приложения и сопряжение находятся внутри **«Подключение»**. При уходе со страницы сопряжения временное подключение закрывается и QR перестаёт действовать; для повтора нужно создать новый.
- На сопряжённом телефоне достаточно нажать **«Трансляция на ПК»** и подтвердить системный захват экрана: при открытом основном окне и запущенном сервере ПК сам откроет **«Экран телефона»**, без ручного ввода IP. Управление включается автоматически только при уже разрешённой службе специальных возможностей Android; новые разрешения приложение само не выдаёт. Ручной ввод IP остаётся запасным вариантом. При переходе в другой раздел просмотр закрывается; остановить трансляцию на Android нужно на телефоне. Фоновая работа и автоматическое восстановление управления не гарантируются.
- В готовящемся Android **1.16** (сборка **26**) кнопки программ показывают значки выбранных на ПК EXE или ярлыков LNK. Нужен Windows **1.0.6**; если значок недоступен или одна из сторон старой версии, используется обычный значок программы.
- Раздел **«Включение ПК»** показывает проверку настроек Wake-on-LAN без изменений при запуске. **«Настроить Windows»** требует подтверждения и UAC и включает только поддерживаемый WakeOnMagicPacket выбранной физической карты, без автоматического перезапуска адаптера. BIOS/UEFI настраивается вручную; 100% означает завершённую проверку или настройку, а не гарантированное пробуждение. Компьютер не выключается автоматически для теста.
- Инструкции RU/EN обновлены под разделы единого окна. Android **1.15** остаётся совместимым для прежних функций. Новые сценарии на реальном телефоне пока не заявлены как проверенные.

Upcoming release, not published yet. These instructions describe the new interface; use the [release page](https://github.com/alexfduch231-prog/DroidBridge/releases/latest) for the latest available build.

- Windows tasks move into one main window with sidebar sections: **«Подключение»** (Connection), **«Экран телефона»** (Phone screen), **«Программы»** (Applications), **«Приём файлов»** (Received files), **«Включение ПК»** (Wake PC) and **«Настройки»** (Settings). File pickers, confirmations and system prompts can remain dialogs.
- The Android download QR and pairing are inside Connection. Leaving pairing closes its temporary session and invalidates the QR; create a new one to retry.
- On the paired phone, tap **Cast phone to PC** and approve system screen capture: with the main window open and server running, the PC opens Phone screen without manual IP entry. Control enables automatically only if Android's Accessibility service was already permitted; the app does not grant new permissions itself. Manual IP entry remains a fallback. Navigating away closes viewing; stop Android casting on the phone. Background operation and automatic control recovery are not guaranteed.
- Upcoming Android **1.16** (build **26**) shows program icons from the EXE files or LNK shortcuts selected on the PC. This requires Windows **1.0.6**; unavailable icons or an older app on either side use a generic program icon.
- **«Включение ПК»** (Wake PC) shows a read-only startup check of Wake-on-LAN settings. **«Настроить Windows»** (Configure Windows) requires confirmation and UAC and enables only the selected physical adapter's supported WakeOnMagicPacket setting without automatically restarting it. BIOS/UEFI setup remains manual; 100% means completed checks or configuration, not guaranteed waking. The PC is not shut down automatically for a test.
- RU/EN instructions now follow the single-window sections. Android **1.15** remains compatible with existing features. New scenarios on a real phone are not claimed as verified.

## 1.0.5 — 2026-11-12

- Windows-интерфейс приводится к стилю приложения на телефоне: общая светлая палитра, синие акценты, карточки и единое оформление окон.
- Главное окно разделено на понятные блоки подключения, просмотра экрана и настроек; содержимое доступно при небольшом размере окна.
- Оригинальный значок с монитором и телефоном заменяет стандартную иконку Python в приложении, установщике и ярлыках.
- Изменения касаются оформления Windows. Совместимая версия Android — 1.15; повторное сопряжение не требуется.

- The Windows interface is being aligned with the phone app: a shared light palette, blue accents, cards and consistent dialogs.
- The main window groups connection, screen viewing and settings; content remains accessible at smaller window sizes.
- An original monitor-and-phone icon replaces the standard Python icon in the app, installer and shortcuts.
- This is a Windows visual update. Android 1.15 remains compatible; pairing again is not required.

## 1.0.4 — 2026-11-12

Windows **1.0.4**, Android **1.15**. Ниже — изменения выпуска и проверенные сценарии; это не гарантия совместимости со всеми устройствами.

### Для пользователя

- **Видео и звук без отдельной установки инструментов.** Windows-установщик поставляется со встроенными FFmpeg и ffplay. Обычному пользователю не понадобятся Python, изменение PATH или отдельный поиск FFmpeg. При обнаруженном комплекте главное окно сообщает, что дополнительная установка не нужна.
- **Автоматический поиск медиакомплекта.** Учитываются ручной выбор, комплект рядом с приложением, PATH и стандартные места установки. Сам поиск не запускает найденные программы. Ручной выбор другой сборки остаётся дополнительной настройкой; запуск выбранных EXE для проверки требует подтверждения. Недоступная явно выбранная папка не должна незаметно подменяться другой.
- **Проверка обновлений при запуске на Windows и Android.** При новой версии предлагаются «Позже» и «Обновить». Используется публичный подписанный список выпусков; учётная запись и личные ключи не нужны. Первую версию с этой функцией придётся установить вручную.
- **Обновление Windows.** После согласия установщик скачивается и проверяется до закрытия собственных компонентов приложения. Повторное открытие главного окна — только после успешной установки, с сохранением пользовательских настроек. Отмена и ошибка не считаются успешным обновлением.
- **Обновление Android.** Проверенный APK передаётся системному установщику: согласие на установку и разрешение источника остаются обязательными. Повторное открытие приложения или уведомление после установки зависит от Android и не гарантируется.
- **Пауза и продолжение передачи файлов.** Передача телефон → ПК продолжается после потери Wi-Fi и предлагается снова после перезапуска приложения. Нужны тот же ПК и доступный неизменённый исходный файл. Перед отправкой выполняется проверка целостности: подготовка большого файла может занять время.
- **Незавершённые передачи.** «Пауза» сохраняет возможность продолжения, «Продолжить» возобновляет передачу. «Удалить передачу» удаляет частичную копию на доступном исходном ПК с прежним подключением, но не уже готовый файл. Вариант «Только на телефоне» очищает локальную запись без связи с ПК; частичная копия на ПК остаётся до истечения 7 дней. Незавершённые данные хранятся до 7 дней; частичная копия не выдаётся за готовый файл. Папка назначения сохраняется с начала передачи, существующие файлы не перезаписываются. Android во время подготовки и передачи нужно держать на экране.
- **Инструкции RU/EN.** Разделены обычная установка, необязательная ручная настройка и разработка; добавлены объяснения обновлений и возобновления передачи.

### Ограничения и проверка

- Исходники зафиксированы после автоматических проверок: listener — 112 тестов, desktop — 77, packaging — 38, Android — 16, client — 16; все прошли. APK **1.15** собран с прежней подписью приложения. Новые сценарии на реальном телефоне пока не проверены.
- Медиакомплект проверен синтетическим кодированием **8 кадров через NVIDIA NVENC** и запуском ffplay с тестовым аудиовыходом. Это не проверка изображения и звука на реальном телефоне или совместимости со всеми устройствами. Телефон недоступен через ADB, поэтому новые сценарии на нём не заявлены как проверенные.
- H.264 экрана ПК сейчас использует NVIDIA NVENC: нужны поддерживаемая видеокарта NVIDIA и подходящий драйвер. Комплектный FFmpeg не гарантирует поддержку каждого Windows-ПК.
- Продолжение передачи требует папки приёма на NTFS или другом диске с поддержкой жёстких ссылок. FAT/exFAT не поддерживаются: новая передача отклоняется заранее с понятной ошибкой, нужно выбрать другую папку.
- Максимальный файл — 50 ГиБ; испытание реальной передачи файла такого размера пока не подтверждено. Фоновая работа Android и автоматическое возвращение после системной установки не гарантируются.
- Основной транспорт команд, видео и файлов не зашифрован: только доверенная локальная сеть, без публичного проброса портов. Системные ограничения Android, защищённые экраны и Windows UAC не обходятся. Подписанный список обновлений не заменяет коммерческую подпись установщика и не отменяет SmartScreen.

[Начать работу](docs/GETTING_STARTED.md) · [Разработка и проверка](docs/DEVELOPMENT.md) · [README](README.md)

---

## English — 1.0.4 — 2026-11-12

Windows **1.0.4**, Android **1.15**. These are release changes and verified scenarios, not a guarantee of compatibility with every device.

### User-facing changes

- **Bundled video/audio tools.** The Windows installer includes FFmpeg and ffplay. Normal installation will not need separate Python, PATH edits or an external FFmpeg download. When tools are available, the main window explains that no extra installation is necessary.
- **Automatic media discovery.** Selection considers the manual override, the app-local bundle, PATH and standard installation locations. Discovery does not execute found programs. Manual override remains optional; probing selected EXEs requires explicit approval. An unavailable explicit override must not silently select something else.
- **Startup update checks on both platforms.** A newer version offers Later / Update using a fixed public, digitally signed release list. No account or personal key is needed. Install the first updater-capable version manually.
- **Windows updating.** After approval, download and verify the installer before closing the app's own components. Reopen the main window only after successful installation, preserving user settings. Cancellation or failure is not success.
- **Android updating.** Hand the verified APK to the system installer. Installation approval and install-source permission remain mandatory. Reopening or a post-install notification is subject to Android restrictions and is not guaranteed.
- **Pause and resume uploads.** Phone-to-PC transfers recover after Wi-Fi loss and are offered again after restarting the app. The same PC and accessible, unchanged source file are required. The initial integrity check can make large-file preparation take time.
- **Pending transfers.** Pause retains progress; Continue resumes. Discard transfer removes the partial copy on the original PC when online with the same saved connection, not an already completed file. Phone only clears the local entry without contacting the PC; the PC's partial copy remains until its 7-day expiry. Incomplete data is retained for up to 7 days and is not presented as a finished file. Keep the original destination across resumes and never overwrite existing files. Keep Android in the foreground during preparation and sending.
- **Russian/English guidance.** Separate normal installation, optional overrides and development instructions; explain updates and resumable transfers.

### Limitations and verification

- Sources were frozen after automated checks: listener — 112 tests, desktop — 77, packaging — 38, Android — 16, client — 16; all passed. APK **1.15** was built with the existing app signing identity. New scenarios on a real phone have not yet been tested.
- Media checks encoded **8 synthetic frames through NVIDIA NVENC** and ran ffplay with a dummy audio output. These do not verify real-phone video/audio or universal compatibility. The phone is unavailable over ADB, so new scenarios on it are not claimed as tested.
- PC-screen H.264 currently uses NVIDIA NVENC, requiring a supported NVIDIA GPU and driver. Bundled FFmpeg does not ensure compatibility with every Windows PC.
- Resumable uploads require a destination on NTFS or another hard-link-capable disk. FAT/exFAT is unsupported: new transfers are rejected early with an explanation; choose another folder.
- Maximum upload size is 50 GiB; an actual transfer of that size has not been confirmed. Android background operation and automatic post-install reopening are not guaranteed.
- Main command/video/file transport is unencrypted: trusted LAN only, no public port forwarding. Android protected screens, system restrictions and Windows UAC are not bypassed. Signed update information does not replace installer code signing or suppress SmartScreen.

[Getting started](docs/GETTING_STARTED.md#english) · [Development and verification](docs/DEVELOPMENT.md) · [README](README.md#english)
