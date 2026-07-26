# SelfDocs

SelfDocs - локальное веб-приложение для подготовки документов по заказам.

Приложение позволяет:

- хранить заказчиков;
- создавать заказы;
- формировать счета;
- формировать акты выполненных работ;
- формировать приложения к договору;
- хранить реквизиты исполнителя;
- добавлять изображение подписи;
- выгружать документы в PDF.

Проект рассчитан прежде всего на индивидуального исполнителя или небольшую организацию.

## Возможности

- локальная база SQLite;
- первоначальная настройка через веб-интерфейс;
- авторизация администратора;
- смена логина и пароля;
- управление заказчиками;
- управление заказами;
- генерация PDF;
- загрузка изображения подписи;
- защита форм от CSRF;
- хранение пароля в виде Argon2-хеша;
- встроенные тесты и самопроверка.

## Технологии

- Python;
- FastAPI;
- Uvicorn;
- SQLAlchemy;
- SQLite;
- Jinja2;
- WeasyPrint;
- pypdf;
- nginx;
- systemd.

## Требования

Поддерживаемая конфигурация:

- Debian 12 или Debian 13 (установка проверена на обеих версиях);
- Python 3.11 или новее;
- systemd;
- nginx;
- не менее 512 МБ оперативной памяти;
- доступ к серверу с правами root.

## Быстрая установка

На чистой Debian сначала обновить индекс пакетов и установить Git:

```bash
apt update
apt install -y git ca-certificates
```

Клонировать репозиторий:

```bash
cd /root

git clone \
  https://github.com/pterodaktil02/selfdocs.git \
  selfdocs-src

cd selfdocs-src
```

Запустить установщик:

```bash
./deploy/install-debian.sh
```

Установщик автоматически:

- установит системные зависимости;
- создаст системного пользователя `selfdocs`;
- скопирует приложение в `/opt/selfdocs`;
- создаст виртуальное окружение Python;
- установит зависимости из `requirements.txt`;
- создаст пустой каталог рабочих данных;
- установит unit systemd;
- настроит nginx;
- запустит приложение;
- проверит endpoint `/health`.

После завершения установки открыть:

```text
http://IP_СЕРВЕРА/setup
```

Логин и пароль заранее не создаются.

## Первый запуск

При первом открытии приложение перенаправит на страницу:

```text
/setup
```

На ней необходимо задать:

- имя администратора;
- пароль администратора.

Минимальная длина пароля - 6 символов.

После завершения настройки приложение создаст рабочие файлы в каталоге:

```text
/opt/selfdocs/data
```

Пароль в открытом виде не сохраняется.

## Управление сервисом

Статус:

```bash
systemctl status selfdocs --no-pager -l
```

Перезапуск:

```bash
systemctl restart selfdocs
```

Остановка:

```bash
systemctl stop selfdocs
```

Запуск:

```bash
systemctl start selfdocs
```

Журнал:

```bash
journalctl -u selfdocs -n 100 --no-pager
```

Проверка работоспособности:

```bash
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Смена логина и пароля

Логин и пароль можно изменить через интерфейс:

```text
Настройки -> Безопасность
```

После изменения учетных данных прежние сессии становятся недействительными.

## Аварийный сброс пароля

Выполнить:

```bash
runuser -u selfdocs -- \
  /opt/selfdocs/venv/bin/python \
  /opt/selfdocs/scripts/reset_password.py
```

После изменения учетных данных:

```bash
systemctl restart selfdocs
```

## Хранение данных

Все изменяемые данные находятся в каталоге:

```text
/opt/selfdocs/data
```

Там могут находиться:

```text
selfdocs.sqlite3
admin-username.txt
admin-password.hash
.session-secret
private/signature.png
```

Каталог `data`:

- не входит в Git;
- не должен раздаваться через nginx;
- должен принадлежать пользователю `selfdocs`;
- должен быть включен в резервное копирование.

## Резервное копирование

Остановить приложение:

```bash
systemctl stop selfdocs
```

Создать архив:

```bash
tar -C /opt/selfdocs \
  -czf /root/selfdocs-data-backup.tar.gz \
  data
```

Запустить приложение:

```bash
systemctl start selfdocs
```

## Восстановление

Остановить приложение:

```bash
systemctl stop selfdocs
```

Удалить текущий каталог данных и распаковать резервную копию:

```bash
rm -rf /opt/selfdocs/data

tar -C /opt/selfdocs \
  -xzf /root/selfdocs-data-backup.tar.gz
```

Восстановить владельца и права:

```bash
chown -R selfdocs:selfdocs /opt/selfdocs/data
chmod 700 /opt/selfdocs/data
```

Запустить приложение:

```bash
systemctl start selfdocs
```

## Обновление

Перед обновлением сохранить данные:

```bash
systemctl stop selfdocs

cp -a \
  /opt/selfdocs/data \
  /opt/selfdocs-data-backup
```

Получить свежую версию исходного кода:

```bash
cd /root/selfdocs-src
git pull
```

Повторно запустить установщик:

```bash
./deploy/install-debian.sh
```

Каталог `/opt/selfdocs/data` установщик не удаляет и не перезаписывает.

## Ручная установка

Для ручной установки используются готовые файлы:

```text
deploy/systemd/selfdocs.service
deploy/nginx/selfdocs.conf
```

Основной каталог приложения:

```text
/opt/selfdocs
```

Рабочий процесс запускается от отдельного системного пользователя:

```text
selfdocs
```

Uvicorn слушает только локальный адрес:

```text
127.0.0.1:8000
```

Внешний доступ осуществляется через nginx.

## Проверка проекта

Проверка синтаксиса Python:

```bash
cd /opt/selfdocs

./venv/bin/python -m compileall -q \
  app \
  scripts \
  tests
```

Встроенная самопроверка:

```bash
runuser -u selfdocs -- \
  /opt/selfdocs/venv/bin/python \
  /opt/selfdocs/scripts/selftest.py
```

Запуск тестов:

```bash
cd /opt/selfdocs

./venv/bin/python -m pytest
```

## Безопасность

SelfDocs рассчитан прежде всего на работу в локальной сети.

При публикации в интернет необходимо дополнительно настроить:

- HTTPS;
- firewall;
- доступ через VPN или ограничение по IP;
- регулярное резервное копирование;
- обновление операционной системы;
- обновление Python-зависимостей;
- надежный пароль администратора.

Порт `8000` не должен быть доступен извне. Внешние подключения должны проходить через nginx или другой обратный прокси.

Каталог `/opt/selfdocs/data` не должен находиться внутри статического web-каталога и не должен раздаваться nginx.

## Структура проекта

```text
app/                         код приложения
app/routes/                  HTTP-маршруты
app/templates/               HTML-шаблоны
app/templates/documents/     шаблоны документов
static/                      CSS и JavaScript
scripts/                     служебные скрипты
tests/                       автоматические тесты
deploy/                      установщик и конфигурации
requirements.txt             зависимости Python
README.md                    документация
LICENSE                      текст лицензии
```

## Лицензия

SelfDocs распространяется на условиях GNU General Public License версии 3 или любой более поздней версии по выбору пользователя.

Полный текст лицензии находится в файле [LICENSE](LICENSE).

При распространении измененной версии исходный код производной работы также должен быть доступен на условиях GNU GPL.
