# SelfDocs

SelfDocs - локальное веб-приложение для подготовки документов по заказам.

Приложение позволяет:

- хранить заказчиков;
- создавать заказы;
- формировать счета;
- формировать акты выполненных работ;
- формировать приложения к договору;
- хранить реквизиты исполнителя;
- добавлять подпись в документы;
- выгружать документы в PDF.

Проект рассчитан прежде всего на локальное использование индивидуальным исполнителем или небольшой организацией.

## Возможности

- локальная база данных SQLite;
- авторизация администратора;
- первоначальная настройка через веб-интерфейс;
- смена логина и пароля;
- управление заказчиками и заказами;
- генерация документов в PDF;
- загрузка изображения подписи;
- защита форм от CSRF;
- хранение паролей в виде Argon2-хеша;
- встроенная самопроверка.

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

Рекомендуемая система:

- Debian 12 или Debian 13;
- Python 3.11 или новее;
- nginx;
- systemd;
- не менее 512 МБ оперативной памяти.

## Установка на Debian

### 1. Установить системные зависимости

```bash
apt update

apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  nginx \
  libcairo2 \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libgdk-pixbuf-2.0-0 \
  libffi-dev \
  shared-mime-info
```

### 2. Создать системного пользователя

```bash
useradd \
  --system \
  --home /opt/selfdocs \
  --shell /usr/sbin/nologin \
  selfdocs
```

### 3. Разместить приложение

```bash
mkdir -p /opt/selfdocs
```

Скопировать файлы проекта в каталог:

```text
/opt/selfdocs
```

### 4. Создать виртуальное окружение

```bash
cd /opt/selfdocs

python3 -m venv venv

./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

### 5. Создать каталог данных

```bash
install -d \
  -o selfdocs \
  -g selfdocs \
  -m 700 \
  /opt/selfdocs/data
```

Исходный код рекомендуется оставить владельцу `root`, а рабочие данные передать пользователю `selfdocs`:

```bash
chown -R root:root \
  /opt/selfdocs/app \
  /opt/selfdocs/scripts \
  /opt/selfdocs/static \
  /opt/selfdocs/tests

chown -R selfdocs:selfdocs /opt/selfdocs/data
```

## Настройка systemd

Создать файл:

```text
/etc/systemd/system/selfdocs.service
```

Содержимое:

```ini
[Unit]
Description=SelfDocs document generator
After=network.target

[Service]
Type=simple
User=selfdocs
Group=selfdocs
WorkingDirectory=/opt/selfdocs

ExecStart=/opt/selfdocs/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1

Restart=on-failure
RestartSec=3

PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/selfdocs/data

[Install]
WantedBy=multi-user.target
```

Активировать сервис:

```bash
systemctl daemon-reload
systemctl enable --now selfdocs
```

Проверить состояние:

```bash
systemctl status selfdocs --no-pager -l
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Настройка nginx

Создать файл:

```text
/etc/nginx/sites-available/selfdocs
```

Пример конфигурации:

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 10m;

    location /static/ {
        alias /opt/selfdocs/static/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активировать конфигурацию:

```bash
ln -s /etc/nginx/sites-available/selfdocs \
  /etc/nginx/sites-enabled/selfdocs

rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx
```

После этого приложение будет доступно по адресу:

```text
http://IP_СЕРВЕРА/
```

## Первый запуск

При первом открытии приложение перенаправит пользователя на страницу:

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

## Смена логина и пароля

Логин и пароль можно изменить через интерфейс:

```text
Настройки -> Безопасность
```

После смены учетных данных прежние сессии становятся недействительными.

## Аварийный сброс пароля

Выполнить:

```bash
runuser -u selfdocs -- \
  /opt/selfdocs/venv/bin/python \
  /opt/selfdocs/scripts/reset_password.py
```

После изменения учетных данных рекомендуется перезапустить сервис:

```bash
systemctl restart selfdocs
```

## Хранение данных

Все изменяемые данные находятся в каталоге:

```text
/opt/selfdocs/data
```

В нем могут находиться:

```text
selfdocs.sqlite3
admin-username.txt
admin-password.hash
.session-secret
private/signature.png
```

Каталог `data`:

- не должен добавляться в Git;
- не должен раздаваться через nginx;
- должен быть доступен на запись только пользователю `selfdocs`.

## Резервное копирование

Для полного резервного копирования достаточно сохранить каталог `data`.

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

### Восстановление

```bash
systemctl stop selfdocs

rm -rf /opt/selfdocs/data

tar -C /opt/selfdocs \
  -xzf /root/selfdocs-data-backup.tar.gz

chown -R selfdocs:selfdocs /opt/selfdocs/data
chmod 700 /opt/selfdocs/data

systemctl start selfdocs
```

## Обновление

Перед обновлением необходимо сохранить каталог `data`.

Пример:

```bash
systemctl stop selfdocs

cp -a \
  /opt/selfdocs/data \
  /opt/selfdocs-data-backup
```

После замены исходного кода:

```bash
cd /opt/selfdocs

./venv/bin/pip install -r requirements.txt

chown -R root:root app scripts static tests
chown -R selfdocs:selfdocs data

systemctl restart selfdocs
```

## Проверка установки

Проверка синтаксиса Python:

```bash
cd /opt/selfdocs

./venv/bin/python -m compileall -q app scripts
```

Встроенная самопроверка:

```bash
runuser -u selfdocs -- \
  /opt/selfdocs/venv/bin/python \
  /opt/selfdocs/scripts/selftest.py
```

Проверка HTTP:

```bash
curl http://127.0.0.1:8000/health
```

## Безопасность

SelfDocs рассчитан прежде всего на работу в локальной сети.

При публикации приложения в интернет необходимо дополнительно настроить:

- HTTPS;
- firewall;
- ограничение доступа по IP или VPN;
- регулярное резервное копирование;
- обновление операционной системы и Python-зависимостей;
- надежный пароль администратора.

Порт Uvicorn `8000` не следует публиковать наружу. Он должен слушать только:

```text
127.0.0.1
```

Внешние подключения должны проходить через nginx или другой обратный прокси.

## Структура проекта

```text
app/                         код приложения
app/routes/                  HTTP-маршруты
app/templates/               HTML-шаблоны
app/templates/documents/     шаблоны документов
static/                      CSS и JavaScript
scripts/                     служебные скрипты
tests/                       автоматические тесты
data/                        рабочие данные, не входит в Git
requirements.txt             зависимости Python
```

## Лицензия

SelfDocs распространяется на условиях GNU General Public License версии 3
или любой более поздней версии по выбору пользователя.

Полный текст лицензии находится в файле [LICENSE](LICENSE).

При распространении измененной версии исходный код производной работы
также должен быть доступен на условиях GNU GPL.
