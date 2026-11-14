# Contributing · Как предложить улучшение

Спасибо за помощь PConDistance!

## Ошибка или идея / Bug or feature

Открой Issue с описанием ожидаемого и фактического поведения. Укажи версию Android/Windows, версию приложения и шаги воспроизведения. Не публикуй ключ доступа, IP/MAC своих устройств, личные файлы, сырые логи и скриншоты без проверки.

Open an issue describing the expected and actual behavior, versions and reproduction steps. Never attach access keys, device IP/MAC addresses, personal files or unredacted logs/screenshots.

## Pull Requests

1. Fork the repository and create a feature branch.
2. Keep changes focused; add a regression test before fixing a bug.
3. Run both Python test suites from README. For Android changes, compile the app and check both Russian and English.
4. Open a Pull Request explaining the motivation, implementation and verification. Link the related issue.
5. Maintainers review and merge changes. Public access does not grant direct push rights.

Сделай fork, отдельную ветку, внеси изменение и открой Pull Request. Опиши зачем оно нужно и как проверено. Решение о принятии остаётся за владельцем проекта.

## Security

Do not propose bypassing Android consent, Accessibility opt-in, UAC, authentication or protected screens. Keep remote control explicit and disabled by default. See SECURITY.md for sensitive reports.

## License

By submitting a contribution, you agree to license your original code under the repository's MIT license. Do not submit third-party assets without redistribution rights.
