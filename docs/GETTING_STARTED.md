# Первое подключение DroidBridge

[На главную](../README.md) · [English](#english) · [Скачать Windows и Android](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.2)

## Перед установкой

Нужны Windows 10/11 x64, Android 5+ и общая **доверенная локальная сеть**. Компьютер может быть подключён к роутеру кабелем, телефон — по Wi-Fi; важно, чтобы роутер разрешал связь между ними. Гостевая Wi-Fi-сеть часто её запрещает.

DroidBridge не подключается через облако. Основные команды, видео и файлы передаются без транспортного шифрования. Используй приложение только на своих устройствах или с согласия владельца и **не пробрасывай порты роутера в Интернет**.

## 1. Установи приложения

1. На [странице релиза 1.0.2](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.2) скачай установщик Windows из списка **Assets**. Для телефона нажми ссылку **«Скачать для Android»** в описании релиза: она ведёт к совместимому APK из предыдущего выпуска. Архивы **Source code** для установки не нужны.
2. Запусти установщик Windows. Python и зависимости интерфейса уже включены. Сервер не запускается автоматически — его включаешь ты.
3. Открой APK на телефоне. Если Android запросит разрешение на установку из этого источника, разреши его только для приложения, которым открываешь скачанный файл. После установки разрешение можно отозвать. Не отключай Play Protect и другие средства защиты.

### Если Windows показывает предупреждение

Установщик не имеет коммерческой цифровой подписи, поэтому SmartScreen может показать неизвестного издателя. Само предупреждение не доказывает ни безопасность, ни вредоносность файла.

Проверь, что скачал файл именно из указанного GitHub-репозитория, и просканируй его защитником Windows. Если в релизе опубликована контрольная сумма, сравни её. Если источник или результат проверки вызывает сомнения — остановись. **Не отключай SmartScreen, антивирус и брандмауэр и не добавляй исключения ради установки.**

## 2. Соедини телефон и ПК

1. Открой DroidBridge на ПК и нажми **«Запустить сервер»**. Статус запущенного процесса ещё не означает, что сеть доступна с телефона.
2. Нажми **«Подключить телефон безопасно»**. В окне сопряжения выбери **«Сетевой адаптер»** домашней сети — Wi-Fi или Ethernet, через который ПК связан с телефоном. Если адаптеров несколько, не выбирай VPN или виртуальный адаптер наугад.
3. Нажми **«Создать новый QR»**. Оставь окно открытым.
4. На телефоне отсканируй QR камерой и открой ссылку в DroidBridge. Если камера не открывает её, на ПК нажми **«Скопировать ссылку»**, а в Android открой **«Добавить ПК»**, вставь ссылку и нажми **«Подключиться»**. Не отправляй ссылку посторонним.
5. Сравни код на ПК и телефоне. Только если он совпадает и это твоё устройство, нажми **«Разрешить»** на ПК. Затем на телефоне нажми **«Сохранить ПК»**. Сохранение заменит текущую пару, если она уже была настроена.
6. Для проверки нажми на телефоне **«Заблокировать»**: Windows должна перейти на экран блокировки. Для дальнейшей работы разблокируй ПК обычным способом.

Сопряжение использует временное защищённое соединение, но **не делает последующее управление зашифрованным**. Не подтверждай незнакомые запросы. Если QR истёк, окно закрыто или телефон повернулся во время сопряжения — создай новый QR и повтори процедуру. Автопоиск помогает уже сопряжённому телефону найти включённый ПК после смены IP; неизвестные ПК он не подключает.

Если Windows запросит сетевой доступ, разрешай его только для доверенного **частного** профиля, не для общедоступных сетей. Не меняй тип чужой сети на частный ради подключения. При ручной настройке брандмауэра ограничь правила локальной подсетью: TCP **8765** для управления и файлов, UDP **8766** для автопоиска, TCP **8767** на время сопряжения. Установщик сам таких правил не создаёт.

## 3. Установи FFmpeg для видео и звука

**Windows-установщик 1.0.2 не включает FFmpeg и ffplay. Скачай их отдельно и выбери папку в DroidBridge — менять PATH не нужно.** Приложение ничего не скачивает автоматически.

1. Открой **«Настроить видео и звук» → «Официальный сайт FFmpeg»** либо [страницу загрузки FFmpeg](https://ffmpeg.org/download.html). Перейди к одному из указанных там поставщиков сборок для Windows. Условия лицензии и состав внешней сборки проверяй у её поставщика.
2. Скачай сборку с **обоими** файлами: `ffmpeg.exe` и `ffplay.exe`. Распакуй архив в постоянную папку на ПК. Не запускай программы из источника, которому не доверяешь.
3. В DroidBridge нажми **«Настроить видео и звук» → «Выбрать папку…»**. Укажи папку `bin` с обоими EXE; можно выбрать и её родительскую папку, если внутри есть `bin`.
4. Прочитай запрос **«Запустить выбранные программы для проверки?»**. При согласии DroidBridge запустит оба EXE с параметром `-version`: до 5 секунд на каждый. Дождись сообщения **«Проверка пройдена, папка сохранена»**. При ошибке настройки не меняются.
5. Останови сервер кнопкой **«Остановить»** и снова нажми **«Запустить сервер»**. Если окно просмотра телефона уже открыто, закрой и открой его заново. Закрывать само приложение DroidBridge не нужно.

Если распакованную папку переместили или удалили, выбери её заново. Кнопка **«Автоматический поиск»** сбрасывает выбранную папку и возвращает поиск в `media` рядом с приложением и в существующем PATH; она ничего не устанавливает. Для обычной настройки этот сброс не нужен.

Без этих инструментов обычные команды, файлы и JPEG-просмотр могут работать, но H.264 и звук недоступны.

## Что делать после подключения

### Экран ПК на телефоне

На Android нажми **«Смотреть экран ПК»**. Включи управление в этом экране, если нужны клики и ввод: касание — левый клик, удержание — правый, движение — перетаскивание. Есть кнопки прокрутки и поле ввода текста. UAC и окна с повышенными правами могут не принимать ввод; приложение не обходит ограничения Windows.

### Экран телефона на ПК

На Android нажми **«Трансляция на ПК»** и подтверди системный запрос на захват экрана. При работающем сервере приложение попытается открыть просмотр на ПК. Если окно не открылось, в главном окне Windows введи локальный IP телефона в разделе **«Экран телефона на ПК»** и нажми **«Открыть экран телефона»**. Адрес телефона можно посмотреть в настройках текущей Wi-Fi-сети Android.

Для управления телефоном отдельно открой **«Разрешить управление телефоном с ПК»** в Android, прочитай объяснение и включи службу **«Управление телефоном с ПК»** в системных специальных возможностях. Для жестов нужен Android 7+. Перезапусти трансляцию и включи управление в окне просмотра на ПК. Разрешение можно отозвать в тех же системных настройках.

Звук приложений доступен с Android 10+, после выдачи запрошенного разрешения на запись аудио и только если само приложение разрешает захват воспроизведения. Это не обещание передачи звука любого приложения. Защищённые экраны могут быть чёрными. После обновления APK, включения службы управления или поворота экрана перезапусти трансляцию. Остановить её можно кнопкой **«Остановить трансляцию»** или через уведомление Android.

### Файлы и программы

- Для отправки файла выбери **«Загрузить файл на ПК»** на телефоне и укажи файл. Не закрывай Android-приложение до окончания. Максимум — 50 ГиБ; после обрыва отправку нужно начать заново.
- По умолчанию файл сохраняется в **«Загрузки»** на ПК. Чтобы изменить место, открой на Windows **«Приём файлов / Received files» → «Выбрать папку…»**. Новая папка применяется со следующей загрузки, уже начатую не переносит. **«Сбросить в „Загрузки“»** возвращает папку по умолчанию. Если выбранная папка недоступна, выбери другую: приложение не сохраняет файл в другое место молча. Одноимённые файлы не перезаписываются.
- Для кнопок запуска программ открой **«Программы / Applications» → «Добавить…»** на ПК, выбери локальный EXE или ярлык LNK и задай название. На телефоне нажми **«Обновить программы»**, если список ещё не появился.

### Включение и выключение ПК

**«Включить»** использует Wake-on-LAN: эта функция должна поддерживаться и быть включена в BIOS/UEFI и настройках сетевой карты. Обычно надёжнее проводное подключение. Сначала подключи включённый ПК, чтобы телефон сохранил его сетевые данные. Выключенный компьютер не отвечает на автопоиск; отправка команды пробуждения не гарантирует запуск.

После **«Выключить»** или **«Перезагрузить»** есть 20 секунд для **«Отменить команду»**. Сохрани документы заранее. Если ответ потерялся, команда всё равно могла дойти: не нажимай её многократно.

## Если не подключается

Проверяй по порядку:

1. ПК включён и не спит, DroidBridge открыт, сервер запущен. Для чистого повтора нажми **«Остановить»**, затем **«Запустить сервер»**.
2. Телефон использует домашний Wi-Fi, не мобильную сеть. Устройства не находятся в гостевых или изолированных сегментах. Один и тот же роутер не всегда означает доступ между устройствами.
3. При создании QR выбран именно домашний адаптер ПК. VPN может менять маршруты; проверь его настройки локального доступа.
4. В брандмауэре разрешены нужные порты только для частной локальной сети. Не отключай брандмауэр целиком. В управляемой сети обратись к администратору.
5. Ссылка ещё действительна и подтверждена на обоих устройствах. Создай новую и выполни сопряжение заново, если есть сомнения. Коды должны совпадать.
6. Команды работают, а видео или звук — нет? В **«Настроить видео и звук»** заново выбери папку с обоими EXE, дождись успешной проверки, затем перезапусти сервер и окно просмотра. Убедись, что папку не перемещали и не удаляли. Для звука проверь версию Android и другое приложение, которое разрешает захват.

Для вопроса в [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues) укажи версии Windows, Android и приложений, что нажал и какой текст ошибки увидел. Не публикуй ключ доступа, QR, ссылки сопряжения, личные адреса устройств и полные логи без проверки. О проблеме безопасности сообщай по [правилам безопасности](../SECURITY.md).

---

# English

[README](../README.md#english) · [Download Windows and Android](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.2)

## Before installing

You need Windows 10/11 x64, Android 5+ and a **trusted local network**. Ethernet on the PC and Wi-Fi on the phone are fine if the router allows communication between them. Guest Wi-Fi often blocks it. There is no cloud relay: the main command, video and file transport is unencrypted. Use only devices you own or have permission to control. **Do not forward router ports to the Internet.**

## Install and pair

1. On the [1.0.2 release page](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.2), download the Windows installer from **Assets**. Use the **«Скачать для Android»** (Download for Android) link in the release description for the compatible APK from an earlier release. You do not need the **Source code** archives. Windows includes Python and UI dependencies; it does not start the server automatically.
2. Install the APK. If Android asks, allow installation only for the app opening this download; you can revoke that permission afterwards. Do not disable Play Protect or other security tools.
3. Open DroidBridge on Windows and click **«Запустить сервер»** (Start server), then **«Подключить телефон безопасно»** (Pair phone). The main Windows panel currently uses Russian labels; the pairing window has a RU/EN selector.
4. Choose your home **Network adapter**, not a VPN or virtual adapter, and click **Create new QR**. Keep the window open.
5. Scan the QR with your phone camera. If the camera cannot open the link, click **Copy pairing link** on the PC, paste it into **Add PC** on Android and tap **Connect**. Keep this temporary link private.
6. Compare the code on both devices. Only if it matches and this is your device, click **Allow** on the PC and **Save PC** on Android. Saving replaces an existing pair. Try **Lock** to check the connection, then unlock Windows normally.

If the QR expires, a pairing window closes or the phone rotates during pairing, create a new QR and start again. Discovery only locates a previously paired, running PC; it does not pair unknown devices. TLS protects pairing, **not subsequent remote-control traffic**.

If Windows asks for network access, allow only a trusted **Private** network, never Public. The installer does not create firewall rules. For manual rules, limit inbound access to the local subnet: TCP **8765** for commands/files, UDP **8766** for discovery and TCP **8767** while pairing is active. Do not mark an untrusted network Private merely to connect.

### Windows security warning

The installer has no commercial code-signing certificate, so SmartScreen may report an unknown publisher. This alone proves neither safety nor harm. Check that the file came from the linked GitHub repository, scan it with Windows Security, and compare a checksum if the release provides one. Stop if the source or scan result is suspicious. **Do not disable SmartScreen, antivirus or the firewall, or add security exclusions just to install.**

## FFmpeg and ffplay: separate download, no PATH editing

**The Windows 1.0.2 installer does not include FFmpeg or ffplay. Download them separately and select their folder in DroidBridge; no PATH change is needed.** The app never downloads these tools automatically.

1. Open **«Настроить видео и звук» → «Официальный сайт FFmpeg»** (Set up video and audio → Official FFmpeg website), or visit the [FFmpeg download page](https://ffmpeg.org/download.html). Choose a linked Windows build provider and check its license and package contents.
2. Download a build containing **both** `ffmpeg.exe` and `ffplay.exe`. Extract it to a permanent folder. Only use executables from a source you trust.
3. Click **«Настроить видео и звук» → «Выбрать папку…»** (Set up video and audio → Choose folder). Select `bin` containing both EXEs, or its parent folder if it contains `bin`. These Windows controls currently use Russian labels.
4. Read **«Запустить выбранные программы для проверки?»** (Run selected programs to check?). If you agree, DroidBridge runs both EXEs with `-version`, allowing up to 5 seconds each. Wait for **«Проверка пройдена, папка сохранена»** (Check passed, folder saved). A failed check leaves settings unchanged.
5. Click **«Остановить»** (Stop), then **«Запустить сервер»** (Start server). Close and reopen any already-running phone viewer too. You do not need to close DroidBridge itself.

If you move or delete the extracted folder, select it again. **«Автоматический поиск»** (Automatic search) resets your selection and searches the app's `media` folder and existing PATH; it installs nothing. Normal setup does not require this reset.

Without these tools, commands, files and JPEG viewing may still work, but H.264 and audio are unavailable.

## Using it

- **PC screen:** tap **View PC screen** on Android and enable control in that screen for clicks and text. Tap for left click, hold for right click, move to drag. Scroll buttons and text input are available. Windows UAC/elevated windows are not bypassed.
- **Phone screen:** tap **Cast phone to PC** on Android and approve the system screen-capture prompt. With the PC server running, the app attempts to open the viewer. If it does not open, enter the phone's local IP in the Windows **«Экран телефона на ПК»** section and click **«Открыть экран телефона»** (Open phone screen). Find the phone IP in Android's current Wi-Fi network details.
- **Phone control:** separately open **Allow phone control from PC** on Android and read the explanation. Enable **Control phone from PC** in system Accessibility settings, restart mirroring, then enable control in the PC viewer. Gestures require Android 7+. Revoke access in the same system settings at any time.
- **Phone audio:** requires Android 10+, the requested audio permission and an app that allows playback capture. Not every app allows it. Protected screens may appear black. Restart mirroring after an APK update, phone rotation or enabling Accessibility. Stop it with **Stop casting** or the Android notification.
- **Files:** choose **Upload file to PC** on Android. Keep the app open until complete. Maximum size is 50 GiB; interrupted uploads must restart. On Windows, open **Приём файлов / Received files → Choose folder…** to select a destination, or **Reset to Downloads**. Changes affect the next upload, not the current one. An unavailable folder causes an error, not a silent save elsewhere. Existing files are not overwritten.
- **Programs:** open **Программы / Applications → Add…** on Windows, choose a local EXE or LNK shortcut and name it. Tap **Refresh programs** on Android if needed.
- **Wake-on-LAN:** enable it in the PC's BIOS/UEFI and network adapter settings if supported. Connect to the PC while it is on first, so the phone saves network details. A powered-off PC cannot answer discovery. Wired Ethernet is generally more reliable; sending a wake packet does not guarantee startup.
- **Shutdown/restart:** save work first. You have 20 seconds to tap **Cancel command**. A lost response does not mean the command failed; avoid repeating it blindly.

## Cannot connect?

1. Check that the PC is awake, DroidBridge is open and its server is running. **«Остановить»** (Stop), then **«Запустить сервер»** restarts it. A running-process status does not confirm network reachability.
2. Use home Wi-Fi, not mobile data. Avoid guest networks and client isolation. The same router can still separate the devices.
3. Check the home adapter selected for the QR and any VPN's local-network routing settings.
4. Check Private/local-subnet firewall rules for the ports above. Do not disable the firewall. Ask the network administrator on a managed network.
5. Generate a new pairing link and repeat approval on both devices. Never accept mismatched codes.
6. Commands work but video/audio does not? Open **«Настроить видео и звук»**, select the folder containing both EXEs again and wait for a successful check. Restart the server and viewer. Check that the extracted folder has not moved or been deleted. For audio, check Android version and an app that permits capture.

For [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues), include Windows/Android/app versions, your steps and the exact error text. Do not share access keys, QR codes, pairing links, personal device addresses or unchecked full logs. See [security reporting](../SECURITY.md) for security concerns.
