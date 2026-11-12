# Изменения / Changelog

## 1.0.10 / Android 1.20 — 2026-11-13

Добавлена передача файлов с ПК на телефон: локальная очередь выбранных файлов, выбор папки Android системным диалогом, прогресс, пауза и продолжение, проверка блоков и итогового SHA-256. Лимит — 50 ГиБ на файл, очередь до 7 дней; исходные пути ПК не публикуются телефону. Для докачки и сохранения нужна дополнительная память. Одноимённые файлы не перезаписываются. На ПК доступны отмена подготовки и удаление файла из очереди.

Added PC-to-phone file transfer: a local queue of explicitly selected files, Android system folder selection, progress, pause/resume, chunk validation and full SHA-256 checks. The limit is 50 GiB per file, with a seven-day queue lifetime; original PC paths are not exposed to the phone. Resuming and saving require extra storage. Existing files are not overwritten. Windows can cancel staging and remove queued files.

На телефоне убрана командная полоса под экраном ПК. Свайп одним пальцем перемещает указатель как на трекпаде; тап нажимает в выбранном месте, долгий тап вызывает правую кнопку, два пальца прокручивают. Кнопка клавиатуры открывает текущую системную клавиатуру Android. После нажатия на текстовое поле приложение запрашивает только признак возможности ввода через Windows UI Automation, без чтения содержимого поля. Если приложение не предоставляет этот признак, клавиатуру можно открыть вручную. Для новых жестов нужны обновления обеих частей.

The phone's PC-view command strip is removed. One-finger swipes move the pointer like a trackpad; taps click the selected position, long taps right-click, and two fingers scroll. The keyboard button opens the current Android system keyboard. After a click, Windows UI Automation supplies only editable-focus metadata, without reading field contents. If an application does not expose that metadata, the keyboard remains available manually. Update both components for the new gestures.

## Android 1.19 — 2026-11-12

Добавлены темы: системная, светлая, тёмная, «Океан», «Лес», «Слива». Выбор сохраняется на телефоне. В настройках появился встроенный сканер QR сопряжения: камера включается только на экране сканера, распознавание выполняется на устройстве, кадры не сохраняются и не отправляются. Подтверждение сопряжения на ПК остаётся обязательным; ручной ввод ссылки сохранён.

Added system, light, dark, Ocean, Forest and Plum themes, saved locally on the phone. Settings now include an in-app pairing QR scanner. The camera is used only on the scanner screen; decoding stays on-device and frames are neither saved nor uploaded. PC-side pairing approval remains required; manual link entry is still available.

## 1.0.9 — 2026-11-12

В Windows видео прижато к правому краю и поднято к верхней строке сервера; углы изображения скруглены. Управление оформлено отдельными строками с переключателями, кнопками общей темы и полем отправки текста. В Android **1.18** просмотр экрана ПК получил полный экран и режимы «Вписать» / «Заполнить»; кнопка «Назад» сначала выходит из полного экрана.

On Windows, video aligns to the right edge and the server header's top level, with rounded image corners. Controls use labeled switch rows, themed buttons and a text field. Android **1.18** adds fullscreen PC viewing with Fit / Fill modes; Back first exits fullscreen.

Просмотр телефона сохраняет портретные пропорции и занимает отдельную правую колонку на всю доступную высоту. Управление, звук и ввод текста сгруппированы слева; шрифт и цвета соответствуют приложению. Исправлено создание декодера с размером 1×2 при открытии ещё не показанной страницы. Воспроизведение звука использует явный pipe:0, поддерживаемый комплектным проигрывателем. Устранена гонка при выключении звука, из-за которой аудиопоток мог завершиться.

The phone view preserves its portrait aspect ratio in a separate right-hand column using the full available height. Controls, audio and text input are grouped on the left with the app's fonts and colors. Fixed a 1×2 decoder size caused by opening an unmapped page. Audio uses explicit pipe:0 supported by the bundled player. Fixed an audio-toggle race that could terminate the audio worker.

## 1.0.8 — 2026-11-12

Повторный запуск Windows-приложения активирует уже открытое главное окно вместо создания второй копии. Сервер и механизм обновления работают независимо от этого ограничения.

Launching the Windows app again activates its existing main window instead of creating another copy. Internal server and update processes are not blocked by this restriction.

Компактная боковая панель и единая верхняя строка выполнены в духе Harness. Справа сверху — рабочие кнопки сворачивания, разворачивания/восстановления и закрытия; закрытие сохраняет подтверждение для активных процессов.

Windows получает выбор оформления в настройках: **как в Windows**, светлое, тёмное и готовые цветовые темы «Океан», «Лес» и «Слива». Выбор сохраняется и применяется без перезапуска. В системном режиме приложение следует переключению светлой и тёмной темы Windows. Изображение телефона и QR не перекрашиваются. Внизу видны версия и ручная проверка обновлений. В Android **1.17** добавлено боковое меню с категориями, версией и ручной проверкой обновлений в настройках; используется системный шрифт телефона. Боковое меню плавно выезжает и следует за пальцем при свайпе, закрывается крестиком и учитывает системное отключение анимаций. Кнопки Android приведены к общей теме вместо стандартных серых плашек; оформление учитывает светлый и тёмный режим. Windows выбирает Segoe UI Variable при наличии, иначе Segoe UI. Кнопки Windows получили скругления, нейтральные оттенки и единые состояния наведения, нажатия, отключения и фокуса во всех темах. Убраны лишние разделители и контрастные подложки; прокрутка появляется только при нехватке места, а её тонкий ползунок и дорожка оформлены в цветах темы без белых плашек.

A compact sidebar and unified title bar take inspiration from Harness. Top-right controls minimize, maximize/restore and close; closing preserves confirmation for active processes.

Windows gains appearance settings: **follow Windows**, light, dark and Ocean, Forest and Plum presets. The selection is saved and applied without restarting. System mode follows changes to the Windows light/dark preference. Video and QR images retain their original colors. The footer shows the version and a manual update check. Android **1.17** adds a sidebar with categories and the app version, plus a manual update check in Settings; it uses the phone's system font. The drawer slides smoothly, follows swipe gestures and closes with a compact cross, respecting disabled system animations. Windows chooses Segoe UI Variable when available, otherwise Segoe UI. Android buttons now share the app theme instead of standard gray blocks. Windows buttons have rounded corners, neutral shades and consistent hover, pressed, disabled and focus states across themes. Unnecessary dividers and contrasting panels are removed; scrolling appears only when space is insufficient, with a slim thumb and track matching the selected theme instead of white blocks.

## 1.0.7 — 2026-11-12

Windows **1.0.7**; Android без изменений — **1.16** (сборка **26**).

- Перед новым сопряжением нужно один раз завершить настройку Wake-on-LAN внутри **«Подключение»**, затем нажать **«Продолжить сопряжение»**. Свежая проверка Windows должна подтвердить включённый Magic Packet у той же физической карты; также нужны явные подтверждения ручной проверки BIOS/UEFI и совместимости локальной сети. «Выключено», «не поддерживается», «неизвестно», отсутствие карты и ошибки проверки завершить шаг не позволяют.
- Завершение сохраняется локально: при старте Windows не опрашивается и напоминание каждый раз не появляется. Свежая проверка нужна только при явном новом сопряжении; сохранённый результат для той же карты с включённым Magic Packet позволяет пропустить повторную настройку. Существующая рабочая пара не отключается и не требует повторного сопряжения ради обновления.
- Проверка не меняет настройки. Изменения Windows — только после согласия и UAC; BIOS/UEFI настраивается вручную. Приложение не принуждает к правам администратора, не входит в BIOS и не выключает ПК для теста. Завершение и 100% не доказывают реальное пробуждение.
- Одноразовый шаг доступен внутри подключения; обычный раздел **«Включение ПК»** остаётся для диагностики и настройки.

Windows **1.0.7**; Android is unchanged at **1.16** (build **26**).

- Before new pairing, complete Wake-on-LAN setup once inside **«Подключение»** (Connection), then choose **«Продолжить сопряжение»** (Continue pairing). A fresh Windows check must confirm Magic Packet enabled on the same physical adapter, with explicit acknowledgements of a manual BIOS/UEFI check and local-network compatibility. Disabled, unsupported or unknown status, a missing adapter and check errors cannot complete the step.
- Completion is saved locally: startup does not probe Windows or repeat a reminder. A fresh check runs only for explicit new pairing; saved completion for the same adapter with Magic Packet enabled skips repeated setup. An existing working pair is not disconnected and does not need re-pairing just to update.
- Checking changes no settings. Windows changes require consent and UAC; BIOS/UEFI setup stays manual. The app does not force administrator access, enter BIOS or shut down the PC for a test. Completion and 100% do not prove real waking.
- The one-time step is inside Connection; the regular Wake PC section remains for diagnostics and configuration.

## 1.0.6 — 2026-11-12

Windows **1.0.6**, Android **1.16** (сборка **26**). Скачать — на [странице релизов](https://github.com/alexfduch231-prog/DroidBridge/releases/latest).

- Основные действия Windows перенесены в одно основное окно с разделами слева: **«Подключение»**, **«Экран телефона»**, **«Программы»**, **«Приём файлов»**, **«Включение ПК»** и **«Настройки»**. Выбор файлов, подтверждения и системные запросы могут оставаться диалогами.
- QR скачивания Android-приложения и сопряжение находятся внутри **«Подключение»**. При уходе со страницы сопряжения временное подключение закрывается и QR перестаёт действовать; для повтора нужно создать новый.
- На сопряжённом телефоне достаточно нажать **«Трансляция на ПК»** и подтвердить системный захват экрана: при открытом основном окне и запущенном сервере ПК сам откроет **«Экран телефона»**, без ручного ввода IP. Управление включается автоматически только при уже разрешённой службе специальных возможностей Android; новые разрешения приложение само не выдаёт. Ручной ввод IP остаётся запасным вариантом. При переходе в другой раздел просмотр закрывается; остановить трансляцию на Android нужно на телефоне. Фоновая работа и автоматическое восстановление управления не гарантируются.
- В Android **1.16** (сборка **26**) кнопки программ показывают значки выбранных на ПК EXE или ярлыков LNK. Нужен Windows **1.0.6**; если значок недоступен или одна из сторон старой версии, используется обычный значок программы.
- Раздел **«Включение ПК»** показывает проверку настроек Wake-on-LAN без изменений при запуске. **«Настроить Windows»** требует подтверждения и UAC и включает только поддерживаемый WakeOnMagicPacket выбранной физической карты, без автоматического перезапуска адаптера. BIOS/UEFI настраивается вручную; 100% означает завершённую проверку или настройку, а не гарантированное пробуждение. Компьютер не выключается автоматически для теста.
- Инструкции RU/EN обновлены под разделы единого окна. Android **1.15** остаётся совместимым для прежних функций. Новые сценарии на реальном телефоне пока не заявлены как проверенные.

Windows **1.0.6**, Android **1.16** (build **26**). Download from the [release page](https://github.com/alexfduch231-prog/DroidBridge/releases/latest).

- Windows tasks move into one main window with sidebar sections: **«Подключение»** (Connection), **«Экран телефона»** (Phone screen), **«Программы»** (Applications), **«Приём файлов»** (Received files), **«Включение ПК»** (Wake PC) and **«Настройки»** (Settings). File pickers, confirmations and system prompts can remain dialogs.
- The Android download QR and pairing are inside Connection. Leaving pairing closes its temporary session and invalidates the QR; create a new one to retry.
- On the paired phone, tap **Cast phone to PC** and approve system screen capture: with the main window open and server running, the PC opens Phone screen without manual IP entry. Control enables automatically only if Android's Accessibility service was already permitted; the app does not grant new permissions itself. Manual IP entry remains a fallback. Navigating away closes viewing; stop Android casting on the phone. Background operation and automatic control recovery are not guaranteed.
- Android **1.16** (build **26**) shows program icons from the EXE files or LNK shortcuts selected on the PC. This requires Windows **1.0.6**; unavailable icons or an older app on either side use a generic program icon.
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
