# Первое подключение DroidBridge

[На главную](../README.md) · [English](#english) · [Скачать Windows и Android](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)

## Перед установкой

Нужны Windows 10/11 x64, Android 5+ и общая **доверенная локальная сеть**. Компьютер может быть подключён к роутеру кабелем, телефон — по Wi-Fi; важно, чтобы роутер разрешал связь между ними. Гостевая Wi-Fi-сеть часто её запрещает.

DroidBridge не подключается через облако. Основные команды, видео и файлы передаются без транспортного шифрования. Используй приложение только на своих устройствах или с согласия владельца и **не пробрасывай порты роутера в Интернет**.

Эта инструкция описывает готовящийся Windows-интерфейс **1.0.6** и Android **1.16** (сборка **26**). Android **1.15** остаётся совместимым для прежних функций, но для значков программ нужны обе новые версии. До публикации 1.0.6 ссылка загрузки ведёт на последнюю доступную версию, интерфейс которой может отличаться. Обычный Windows-установщик содержит FFmpeg и ffplay; у прежних slim-установщиков медиакомплект отсутствует. Проверка новых сценариев на реальном телефоне пока не подтверждена.

В 1.0.6 работа идёт в одном основном окне: слева **«Подключение»**, **«Экран телефона»**, **«Программы»**, **«Приём файлов»** и **«Настройки»**. Установка Android-приложения, сопряжение и просмотр телефона открываются внутри этих разделов. Выбор файлов, подтверждения и системные запросы разрешений могут оставаться отдельными диалогами.

## 1. Установи приложения

1. На [странице загрузки](https://github.com/alexfduch231-prog/DroidBridge/releases/latest) скачай установщик Windows и Android APK из списка **Assets**. Архивы **Source code** для установки не нужны. В разделе Windows **«Подключение»** нажми **«Установить на телефон»**: отсканируй QR обычной камерой телефона, чтобы скачать APK с GitHub. Если приложение уже есть, нажми **«Уже установлено → подключить к ПК»** — скачивание будет пропущено.
2. Запусти установщик Windows. В обычную установку входят Python, зависимости интерфейса, FFmpeg и ffplay; инструменты видео и звука выбираются автоматически. Ничего отдельно скачивать или добавлять в PATH не нужно. Сервер не запускается автоматически — его включаешь ты.
3. Открой APK на телефоне. Если Android запросит разрешение на установку из этого источника, разреши его только для приложения, которым открываешь скачанный файл. После установки разрешение можно отозвать. Не отключай Play Protect и другие средства защиты.

### Если Windows показывает предупреждение

Установщик не имеет коммерческой цифровой подписи, поэтому SmartScreen может показать неизвестного издателя. Само предупреждение не доказывает ни безопасность, ни вредоносность файла.

Проверь, что скачал файл именно из указанного GitHub-репозитория, и просканируй его защитником Windows. Если в релизе опубликована контрольная сумма, сравни её. Если источник или результат проверки вызывает сомнения — остановись. **Не отключай SmartScreen, антивирус и брандмауэр и не добавляй исключения ради установки.**

QR скачивания ведёт только к установочному файлу. Для подключения используется **другой QR** на странице сопряжения внутри раздела **«Подключение»**. После установки выбери **«Установлено → подключить к ПК»**; с начальной страницы — **«Уже установлено → подключить к ПК»**. Отдельное окно установки или сопряжения открывать не нужно.

## 2. Соедини телефон и ПК

1. Открой DroidBridge на ПК и нажми **«Запустить сервер»**. Статус запущенного процесса ещё не означает, что сеть доступна с телефона.
2. Слева открой **«Подключение» → «Уже установлено → подключить к ПК»**. На странице сопряжения выбери **«Сетевой адаптер»** домашней сети — Wi-Fi или Ethernet, через который ПК связан с телефоном. Если адаптеров несколько, не выбирай VPN или виртуальный адаптер наугад.
3. Нажми **«Создать новый QR»**. Оставайся на этой странице до завершения сопряжения: переход в другой раздел закрывает временное подключение и делает QR недействительным.
4. На телефоне отсканируй QR камерой и открой ссылку в DroidBridge. Если камера не открывает её, на ПК нажми **«Скопировать ссылку»**, а в Android открой **«Добавить ПК»**, вставь ссылку и нажми **«Подключиться»**. Не отправляй ссылку посторонним.
5. Сравни код на ПК и телефоне. Только если он совпадает и это твоё устройство, нажми **«Разрешить»** на ПК. Затем на телефоне нажми **«Сохранить ПК»**. Сохранение заменит текущую пару, если она уже была настроена.
6. Для проверки нажми на телефоне **«Заблокировать»**: Windows должна перейти на экран блокировки. Для дальнейшей работы разблокируй ПК обычным способом.

Сопряжение использует временное защищённое соединение, но **не делает последующее управление зашифрованным**. Не подтверждай незнакомые запросы. Если QR истёк, ты ушёл со страницы сопряжения, закрыл приложение или телефон повернулся во время сопряжения — создай новый QR и повтори процедуру. Автопоиск помогает уже сопряжённому телефону найти включённый ПК после смены IP; неизвестные ПК он не подключает.

Если Windows запросит сетевой доступ, разрешай его только для доверенного **частного** профиля, не для общедоступных сетей. Не меняй тип чужой сети на частный ради подключения. При ручной настройке брандмауэра ограничь правила локальной подсетью: TCP **8765** для управления и файлов, UDP **8766** для автопоиска, TCP **8767** на время сопряжения. Установщик сам таких правил не создаёт.

## 3. Видео и звук

**В обычной установке FFmpeg и ffplay уже входят в комплект и выбираются автоматически.** Слева открой **«Настройки»**, чтобы проверить медиакомплект. Если инструменты найдены, ручная настройка не нужна. Для автообнаружения приложение только ищет файлы: ничего не скачивает и не запускает для проверки.

H.264 экрана ПК сейчас использует **NVIDIA NVENC**: нужна поддерживаемая видеокарта NVIDIA и подходящий драйвер. Комплектный FFmpeg не гарантирует этот режим на любом Windows-ПК. Звук телефона требует Android 10+ и приложения, разрешающего захват.

### Необязательно: другая сборка или восстановление настройки

Эта настройка нужна для запуска из исходников, старого slim-установщика или осознанной замены медиакомплекта, а не при обычной установке.

1. Если инструментов нет, сначала восстанови обычную установку. Для своей сборки можно открыть **«Настройки» → «Официальный сайт FFmpeg»** или [страницу FFmpeg](https://ffmpeg.org/download.html) и выбрать доверенного поставщика Windows-сборки с **обоими** файлами: `ffmpeg.exe` и `ffplay.exe`. Распакуй её в постоянную папку.
2. Нажми **«Настройки» → «Выбрать папку…»**. Укажи `bin` с обоими EXE или родительскую папку, если внутри есть `bin`.
3. Прочитай **«Запустить выбранные программы для проверки?»**. Только после твоего согласия DroidBridge запустит оба выбранных EXE с `-version`, до 5 секунд на каждый. Дождись **«Проверка пройдена, папка сохранена»**. При отказе или ошибке настройки не меняются.
4. Перезапусти сервер кнопками **«Остановить» → «Запустить сервер»** вверху окна. Затем открой раздел **«Экран телефона»** и подключи просмотр заново. Закрывать DroidBridge не нужно.

**«Автоматический поиск»** отменяет ручной выбор и возвращает поиск комплектных инструментов, PATH и стандартных мест установки. Он ничего не устанавливает и не запускает EXE для проверки. Ручной выбор имеет приоритет: если выбранную папку удалили, выбери её заново или нажми **«Автоматический поиск»**; скрытой подмены другой сборкой нет.

Лицензии и соответствующие исходники комплектных компонентов — часть подготовки дистрибутива, а не отдельное действие для обычного пользователя. Без найденных инструментов команды, файлы и JPEG-просмотр могут работать, но H.264 и звук недоступны.

## Обновления

**Функция включена в 1.0.4.** Обновление на реальном телефоне пока не проверено. Первую версию с проверкой обновлений установи вручную со страницы релиза поверх текущей; старое приложение само эту возможность не получит. Не удаляй приложение ради обновления: удаление может стереть настройки.

- При запуске Windows- и Android-приложение проверят наличие новой версии через Интернет. Для этого используется фиксированный публичный адрес со списком версий и цифровой подписью; учётная запись, личный ключ или настройка сервера тебе не нужны. Это отдельная проверка обновлений, не облачный канал управления устройствами.
- Если есть новая версия, появятся **«Позже»** и **«Обновить»**. **«Позже»** оставляет текущую версию. Если Интернет недоступен или проверка не удалась, обновление не устанавливается; можно продолжить работу и попробовать позже.
- **Windows:** после **«Обновить»** приложение скачает установщик и проверит его по подписанным сведениям о выпуске. Только после успешной проверки закроет свой сервер, просмотр и главное окно, чтобы запустить установку. Сохрани работу и заверши передачу файлов заранее. Главное окно откроется снова только после успешной установки; настройки и сохранённые подключения должны остаться. При ошибке или отмене не считай обновление установленным — открой приложение вручную и проверь версию.
- **Android:** после скачивания и проверки APK откроется **системное подтверждение установки**. При необходимости разреши установку из этого источника именно для DroidBridge; подтверждение Android обязательно и не обходится. Обновляй поверх установленного приложения, чтобы сохранить настройки. После установки приложение попробует открыться снова или предложить уведомление, но Android может это ограничить; если не открылось — запусти его обычным способом.

Для ручного обновления всегда можно использовать страницу релиза. Цифровая подпись списка обновлений не означает, что Windows-установщик имеет коммерческую подпись или что SmartScreen не покажет предупреждение.

## Что делать после подключения

### Экран ПК на телефоне

На Android нажми **«Смотреть экран ПК»**. Включи управление в этом экране, если нужны клики и ввод: касание — левый клик, удержание — правый, движение — перетаскивание. Есть кнопки прокрутки и поле ввода текста. UAC и окна с повышенными правами могут не принимать ввод; приложение не обходит ограничения Windows.

### Экран телефона на ПК

Оставь основное окно DroidBridge на ПК открытым и запусти сервер. На Android нажми **«Трансляция на ПК»** и подтверди системный запрос на захват экрана. Запрос с телефона направляется в уже открытое основное окно, чтобы показать трансляцию внутри раздела **«Экран телефона»**, а не запустить отдельное окно просмотра. Если главное окно закрыто, открой DroidBridge и повтори запрос с телефона: один сервер без интерфейса может обслуживать команды, но не встроенный просмотр.

Для ручного подключения открой слева **«Экран телефона»**, введи локальный IP телефона и нажми **«Открыть экран телефона»**. Адрес телефона можно посмотреть в настройках текущей Wi-Fi-сети Android.

Для отключения просмотра перейди в другой раздел. Чтобы подключиться снова, вернись в **«Экран телефона»** и повтори открытие. Закрытие просмотра на ПК не заменяет остановку трансляции на Android: закончив работу, нажми на телефоне **«Остановить трансляцию»** или используй его уведомление.

Для управления телефоном отдельно открой **«Разрешить управление телефоном с ПК»** в Android, прочитай объяснение и включи службу **«Управление телефоном с ПК»** в системных специальных возможностях. Для жестов нужен Android 7+. Перезапусти трансляцию и включи управление в разделе просмотра на ПК. Разрешение можно отозвать в тех же системных настройках.

Звук приложений доступен с Android 10+, после выдачи запрошенного разрешения на запись аудио и только если само приложение разрешает захват воспроизведения. Это не обещание передачи звука любого приложения. Защищённые экраны могут быть чёрными. После обновления APK, включения службы управления или поворота экрана перезапусти трансляцию. Остановить её можно кнопкой **«Остановить трансляцию»** или через уведомление Android.

### Файлы и программы

- Для отправки файла выбери **«Загрузить файл на ПК»** на телефоне и укажи файл. Максимум — 50 ГиБ. Перед отправкой приложение читает файл для проверки целостности: подготовка большого файла может занять заметное время, ещё до появления переданных байтов.
- **В версии 1.0.4 реализовано продолжение передачи; проверка на реальном телефоне пока не подтверждена.** Используй **«Пауза»**, затем **«Продолжить»**; **«Позже»** откладывает продолжение. После краткого обрыва Wi-Fi приложение попробует восстановить передачу; если не удалось — восстанови соединение с тем же ПК и продолжи вручную. После перезапуска приложения незавершённая передача будет предложена снова. Нужен тот же доступный и неизменённый исходный файл: не удаляй, не перемещай и не редактируй его до окончания, не отзывай доступ приложения к нему. Если выбранный источник не позволяет сохранить доступ, приложение попросит выбрать файл через другого поставщика. Повторная проверка исходного файла при продолжении тоже может занять время.
- Незавершённая передача хранится до **7 дней**, после чего может потребоваться начать заново. Пауза сохраняет возможность продолжить. **«Удалить передачу»** позволяет удалить незавершённую копию на исходном ПК, если он доступен с прежним сохранённым подключением. Если ПК недоступен или подключение изменилось, выбери в следующем диалоге **«Только на телефоне»**: приложение забудет передачу и очистит её локальные данные, но частичная копия на ПК останется до истечения 7 дней. Уже готовый файл не удаляется. Если сохранённая передача на ПК уже истекла или отсутствует, **«Продолжить»** покажет ошибку, а не начнёт заново в другой папке; удали запись передачи и выбери файл снова явно. Частичная копия на ПК **ещё не готовый файл**: обычный файл появляется только после полной передачи и проверки. Во время подготовки и отправки держи Android-приложение **на экране** — работа в фоне или при заблокированном телефоне не гарантируется.
- Для продолжения передачи папка приёма должна находиться на диске с поддержкой жёстких ссылок, например **NTFS**. Диски **FAT/exFAT не поддерживаются**: приложение сообщит об этом до начала новой передачи. Выбери папку на NTFS; не форматируй диск ради этой функции.
- По умолчанию файл сохраняется в **«Загрузки»** на ПК. Чтобы изменить место, открой на Windows **«Приём файлов / Received files» → «Выбрать папку…»**. Новая папка применяется со следующей загрузки, уже начатую не переносит, в том числе при её продолжении. **«Сбросить в „Загрузки“»** возвращает папку по умолчанию. Если выбранная папка недоступна, выбери другую: приложение не сохраняет файл в другое место молча. Одноимённые файлы не перезаписываются.
- Для кнопок запуска программ открой **«Программы / Applications» → «Добавить…»** на ПК, выбери локальный EXE или ярлык LNK и задай название. На телефоне нажми **«Обновить программы»**, если список ещё не появился. В готовящихся Windows **1.0.6** и Android **1.16** (сборка **26**) телефон получает значки этих программ с ПК. Если значок неизвестен или извлечь его не удалось, показывается обычный значок программы; запуск от этого не меняется. Со старой версией на одной из сторон список и запуск остаются доступны, но без новых значков.

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
6. Команды работают, а видео или звук — нет? Проверь статус инструментов в разделе **«Настройки»**. Если они не найдены, восстанови установку; если ранее выбирал свою папку — проверь её или верни **«Автоматический поиск»**. После изменения настройки перезапусти сервер и просмотр. Для H.264 экрана ПК проверь поддержку NVIDIA NVENC и драйвер, для звука — версию Android и приложение, разрешающее захват.

Для вопроса в [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues) укажи версии Windows, Android и приложений, что нажал и какой текст ошибки увидел. Не публикуй ключ доступа, QR, ссылки сопряжения, личные адреса устройств и полные логи без проверки. О проблеме безопасности сообщай по [правилам безопасности](../SECURITY.md).

---

# English

[README](../README.md#english) · [Download Windows and Android](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)

This guide describes the upcoming Windows **1.0.6** interface and Android **1.16** (build **26**). Android **1.15** remains compatible with existing features, but program icons require both new versions. Until 1.0.6 is published, the download link opens the latest available release, whose interface may differ. The standard Windows installer includes FFmpeg/ffplay; earlier slim installers do not. Verification of new scenarios on a real phone is not yet confirmed.

In 1.0.6, one main window contains **«Подключение»** (Connection), **«Экран телефона»** (Phone screen), **«Программы»** (Applications), **«Приём файлов»** (Received files) and **«Настройки»** (Settings). Android download, pairing and phone viewing open inside these sections. File pickers, confirmations and system permission prompts can still open dialogs. The sidebar currently uses Russian labels.

## Before installing

You need Windows 10/11 x64, Android 5+ and a **trusted local network**. Ethernet on the PC and Wi-Fi on the phone are fine if the router allows communication between them. Guest Wi-Fi often blocks it. There is no cloud relay: the main command, video and file transport is unencrypted. Use only devices you own or have permission to control. **Do not forward router ports to the Internet.**

The download QR only downloads the APK. Pairing uses a **different QR** on the pairing page inside **«Подключение»** (Connection). After installing, choose **«Установлено → подключить к ПК»** (Installed → connect to PC); from the initial page, choose **«Уже установлено → подключить к ПК»** (Already installed → connect to PC). No separate setup or pairing window is needed.

## Install and pair

1. On the [download page](https://github.com/alexfduch231-prog/DroidBridge/releases/latest), download the Windows installer and Android APK from **Assets**. You do not need the **Source code** archives. In Windows **«Подключение»** (Connection), choose **«Установить на телефон»** (Install on phone) and scan the QR with your phone camera to download the APK from GitHub. Choose **«Уже установлено → подключить к ПК»** (Already installed → connect to PC) to skip downloading and open pairing. The standard Windows installer includes Python, UI dependencies, FFmpeg and ffplay; media tools are selected automatically. No separate download or PATH edit is needed. The server does not start automatically.
2. Install the APK. If Android asks, allow installation only for the app opening this download; you can revoke that permission afterwards. Do not disable Play Protect or other security tools.
3. Open DroidBridge on Windows and click **«Запустить сервер»** (Start server) at the top of the window. Open **«Подключение» → «Уже установлено → подключить к ПК»** (Connection → Already installed → connect to PC). The pairing page has a RU/EN selector.
4. Choose your home **Network adapter**, not a VPN or virtual adapter, and click **Create new QR**. Stay on this page until pairing finishes: navigating to another section closes the temporary session and invalidates its QR.
5. Scan the QR with your phone camera. If the camera cannot open the link, click **Copy pairing link** on the PC, paste it into **Add PC** on Android and tap **Connect**. Keep this temporary link private.
6. Compare the code on both devices. Only if it matches and this is your device, click **Allow** on the PC and **Save PC** on Android. Saving replaces an existing pair. Try **Lock** to check the connection, then unlock Windows normally.

If the QR expires, you leave the pairing page, close the app or the phone rotates during pairing, create a new QR and start again. Discovery only locates a previously paired, running PC; it does not pair unknown devices. TLS protects pairing, **not subsequent remote-control traffic**.

If Windows asks for network access, allow only a trusted **Private** network, never Public. The installer does not create firewall rules. For manual rules, limit inbound access to the local subnet: TCP **8765** for commands/files, UDP **8766** for discovery and TCP **8767** while pairing is active. Do not mark an untrusted network Private merely to connect.

### Windows security warning

The installer has no commercial code-signing certificate, so SmartScreen may report an unknown publisher. This alone proves neither safety nor harm. Check that the file came from the linked GitHub repository, scan it with Windows Security, and compare a checksum if the release provides one. Stop if the source or scan result is suspicious. **Do not disable SmartScreen, antivirus or the firewall, or add security exclusions just to install.**

## Video and audio

**The standard installer includes FFmpeg and ffplay and selects them automatically.** Open **«Настройки»** (Settings) to check the media tools. When tools are found, manual setup is unnecessary. Automatic discovery only looks for files: it downloads nothing and does not run executables to probe them.

Current PC-screen H.264 encoding uses **NVIDIA NVENC**, requiring a supported NVIDIA GPU and driver. Bundling FFmpeg does not guarantee this mode on every Windows PC. Phone audio requires Android 10+ and an app that permits capture.

### Optional: manual override or recovery

Use this for source runs, earlier slim installers or a deliberate media-bundle replacement, not for a standard installation.

1. If tools are missing, try repairing the standard installation first. For your own build, use **«Настройки» → «Официальный сайт FFmpeg»** (Settings → Official FFmpeg website), or the [FFmpeg download page](https://ffmpeg.org/download.html). Pick a trusted Windows build containing **both** `ffmpeg.exe` and `ffplay.exe` and extract it to a permanent folder.
2. Click **«Настройки» → «Выбрать папку…»** (Choose folder). Select `bin` containing both EXEs, or its parent folder if it contains `bin`. These controls currently use Russian labels.
3. Read **«Запустить выбранные программы для проверки?»** (Run selected programs to check?). Only with your consent does DroidBridge run both selected EXEs with `-version`, allowing up to 5 seconds each. Wait for **«Проверка пройдена, папка сохранена»** (Check passed, folder saved). Declining or a failed check leaves settings unchanged.
4. Click **«Остановить»** (Stop), then **«Запустить сервер»** (Start server) at the top of the window. Open **«Экран телефона»** (Phone screen) and reconnect the viewer. DroidBridge itself can stay open.

**«Автоматический поиск»** (Automatic search) clears the manual override and returns to the bundled tools, PATH and standard installation locations. It installs nothing and does not probe executables. A manual selection takes priority: if its folder is deleted, choose it again or reset to automatic search; another build is not silently substituted.

Bundled-component licenses and corresponding sources belong in distribution preparation, not in the normal user's installation checklist. Without available tools, commands, files and JPEG viewing may still work, but H.264 and audio are unavailable.

## Updates

**This feature is included in 1.0.4.** Updating on a real phone has not yet been tested. Install the first updater-capable version manually from the release page over your current installation; an older app cannot acquire the feature by itself. Do not uninstall just to update: uninstalling may erase settings.

- At startup, both Windows and Android will check for a newer version over the Internet using a fixed public, digitally signed release list. You do not need an account, personal key or server setup. This update check is separate from device control; it is not a cloud relay.
- If an update exists, choose **Later** or **Update**. **Later** keeps the current version. If the Internet is unavailable or verification fails, no update is installed; you can keep using the app and retry later.
- **Windows:** after **Update**, the app will download the installer and verify it against the signed release information. Only after successful verification will it close its server, viewer and main window for installation. Save work and finish file transfers first. The main window will reopen only after installation succeeds; settings and saved connections are intended to remain. If installation fails or is cancelled, do not assume it updated: open the app manually and check the version.
- **Android:** after downloading and verifying the APK, the app will open the **system installation confirmation**. If necessary, permit DroidBridge to install from this source. Android approval is mandatory and is not bypassed. Update in place to keep settings. Afterwards the app will try to reopen or offer a notification, but Android can restrict either action; open it normally if needed.

Manual updating from the release page remains available. A digitally signed release list does not give the Windows installer a commercial code-signing certificate or prevent SmartScreen warnings.

## Using it

- **PC screen:** tap **View PC screen** on Android and enable control in that screen for clicks and text. Tap for left click, hold for right click, move to drag. Scroll buttons and text input are available. Windows UAC/elevated windows are not bypassed.
- **Phone screen:** keep the DroidBridge main window open and start its server. Tap **Cast phone to PC** on Android and approve the system screen-capture prompt. The request is handed to the already-open main window to show the stream inside **«Экран телефона»** (Phone screen), rather than launching a separate viewer. If the main window is closed, open DroidBridge and retry on the phone; a server alone can handle commands, but not embedded viewing. For manual connection, open Phone screen, enter the phone's local IP and click **«Открыть экран телефона»** (Open phone screen). Find the phone IP in Android's current Wi-Fi network details. Navigating to another section closes the viewer connection; return and open it again to reconnect. Closing the PC viewer does not replace stopping Android casting: when finished, tap **Stop casting** on the phone or use its notification.
- **Phone control:** separately open **Allow phone control from PC** on Android and read the explanation. Enable **Control phone from PC** in system Accessibility settings, restart mirroring, then enable control in the PC viewer. Gestures require Android 7+. Revoke access in the same system settings at any time.
- **Phone audio:** requires Android 10+, the requested audio permission and an app that allows playback capture. Not every app allows it. Protected screens may appear black. Restart mirroring after an APK update, phone rotation or enabling Accessibility. Stop it with **Stop casting** or the Android notification.
- **Files:** choose **Upload file to PC** on Android. The maximum is 50 GiB. The app reads the source for an integrity check before sending, so preparing a large file may take time before any bytes are shown as sent.
- **Resumable transfers are implemented in 1.0.4; real-phone verification is not yet confirmed.** Use **Pause**, then **Continue**; **Later** postpones resuming. After a brief Wi-Fi outage, the app will try to recover; if that fails, reconnect to the same PC and resume manually. A pending transfer will be offered again after restarting the app. The original file must remain accessible and unchanged: do not delete, move or edit it, or revoke the app's access before completion. If the selected provider cannot retain access, the app will ask you to choose a different provider. Checking the original file again when resuming can also take time.
- Incomplete transfers are kept for up to **7 days**; afterwards you may need to start again. Pausing keeps the transfer available. **Discard transfer** can remove the incomplete copy on the original PC when it is online with the same saved connection. If the PC is unavailable or the connection has changed, choose **Phone only** in the next dialog: this clears the phone's pending entry and local data, but leaves the PC's partial copy until its 7-day expiry. An already completed file is not deleted. If the PC session has expired or is missing, **Continue** reports an error rather than silently restarting in another folder; explicitly discard the pending entry and select the file again. A partial copy on the PC **is not a finished file**: the normal file appears only after the entire transfer and integrity check succeed. Keep Android **in the foreground** during preparation and sending; background or locked-screen operation is not guaranteed.
- Resumable uploads require a destination disk that supports hard links, such as **NTFS**. **FAT/exFAT disks are unsupported** and will be rejected before a new transfer starts. Choose a folder on NTFS; do not format a disk just for this feature.
- On Windows, open **Приём файлов / Received files → Choose folder…** to select a destination, or **Reset to Downloads**. Changes affect the next upload, not the current one or its resumed transfer. An unavailable folder causes an error, not a silent save elsewhere. Existing files are not overwritten.
- **Programs:** open **Программы / Applications → Add…** on Windows, choose a local EXE or LNK shortcut and name it. Tap **Refresh programs** on Android if needed. Upcoming Windows **1.0.6** and Android **1.16** (build **26**) send these program icons from the PC to the phone. If an icon is unknown or cannot be extracted, a generic program icon is shown; launching is unchanged. With an older version on either side, the list and launching remain available without the new icons.
- **Wake-on-LAN:** enable it in the PC's BIOS/UEFI and network adapter settings if supported. Connect to the PC while it is on first, so the phone saves network details. A powered-off PC cannot answer discovery. Wired Ethernet is generally more reliable; sending a wake packet does not guarantee startup.
- **Shutdown/restart:** save work first. You have 20 seconds to tap **Cancel command**. A lost response does not mean the command failed; avoid repeating it blindly.

## Cannot connect?

1. Check that the PC is awake, DroidBridge is open and its server is running. **«Остановить»** (Stop), then **«Запустить сервер»** restarts it. A running-process status does not confirm network reachability.
2. Use home Wi-Fi, not mobile data. Avoid guest networks and client isolation. The same router can still separate the devices.
3. Check the home adapter selected for the QR and any VPN's local-network routing settings.
4. Check Private/local-subnet firewall rules for the ports above. Do not disable the firewall. Ask the network administrator on a managed network.
5. Generate a new pairing link and repeat approval on both devices. Never accept mismatched codes.
6. Commands work but video/audio does not? Check the media-tool status under **«Настройки»** (Settings). Repair the installation if tools are missing; if you previously chose your own folder, check it or reset to **«Автоматический поиск»** (Automatic search). Restart the server and viewer after settings changes. Check NVIDIA NVENC support and drivers for PC-screen H.264; for audio, check Android version and an app that permits capture.

For [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues), include Windows/Android/app versions, your steps and the exact error text. Do not share access keys, QR codes, pairing links, personal device addresses or unchecked full logs. See [security reporting](../SECURITY.md) for security concerns.
