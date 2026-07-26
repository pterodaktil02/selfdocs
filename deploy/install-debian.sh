#!/usr/bin/env bash
# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later


set -Eeuo pipefail

readonly INSTALL_DIR="/opt/selfdocs"
readonly SERVICE_USER="selfdocs"
readonly SERVICE_GROUP="selfdocs"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

log() {
    printf '\n==> %s\n' "$*"
}

fail() {
    printf '\nОшибка: %s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Установщик необходимо запускать от root."
fi

if [[ ! -f "${SOURCE_DIR}/requirements.txt" ]] ||
   [[ ! -d "${SOURCE_DIR}/app" ]] ||
   [[ ! -d "${SOURCE_DIR}/static" ]] ||
   [[ ! -f "${SOURCE_DIR}/deploy/systemd/selfdocs.service" ]] ||
   [[ ! -f "${SOURCE_DIR}/deploy/nginx/selfdocs.conf" ]]; then
    fail "Не найден полный комплект файлов проекта SelfDocs."
fi

if [[ "${SOURCE_DIR}" == "${INSTALL_DIR}" ]]; then
    fail "Установщик нельзя запускать из ${INSTALL_DIR}. Клонируйте репозиторий в другой каталог, например /root/selfdocs-src."
fi

log "Установка системных пакетов"

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    nginx \
    rsync \
    curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation

log "Создание системного пользователя"

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
    groupadd --system "${SERVICE_GROUP}"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd \
        --system \
        --gid "${SERVICE_GROUP}" \
        --home-dir "${INSTALL_DIR}" \
        --shell /usr/sbin/nologin \
        "${SERVICE_USER}"
fi

log "Копирование приложения в ${INSTALL_DIR}"

install -d -o root -g root -m 755 "${INSTALL_DIR}"

rsync -a --delete \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='data/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    "${SOURCE_DIR}/" "${INSTALL_DIR}/"

log "Создание виртуального окружения"

python3 -m venv "${INSTALL_DIR}/venv"

"${INSTALL_DIR}/venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/venv/bin/python" -m pip install \
    -r "${INSTALL_DIR}/requirements.txt"

log "Создание каталога рабочих данных"

install -d \
    -o "${SERVICE_USER}" \
    -g "${SERVICE_GROUP}" \
    -m 700 \
    "${INSTALL_DIR}/data"

log "Настройка владельцев и прав"

chown -R root:root \
    "${INSTALL_DIR}/app" \
    "${INSTALL_DIR}/static" \
    "${INSTALL_DIR}/scripts" \
    "${INSTALL_DIR}/tests" \
    "${INSTALL_DIR}/deploy"

find \
    "${INSTALL_DIR}/app" \
    "${INSTALL_DIR}/static" \
    "${INSTALL_DIR}/scripts" \
    "${INSTALL_DIR}/tests" \
    "${INSTALL_DIR}/deploy" \
    -type d -exec chmod 755 {} +

find \
    "${INSTALL_DIR}/app" \
    "${INSTALL_DIR}/static" \
    "${INSTALL_DIR}/scripts" \
    "${INSTALL_DIR}/tests" \
    "${INSTALL_DIR}/deploy" \
    -type f -exec chmod 644 {} +

chmod 755 \
    "${INSTALL_DIR}/scripts/reset_password.py" \
    "${INSTALL_DIR}/scripts/selftest.py" \
    "${INSTALL_DIR}/scripts/smoke_test.py" \
    "${INSTALL_DIR}/deploy/install-debian.sh"

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}/data"
chmod 700 "${INSTALL_DIR}/data"

log "Проверка Python-кода"

"${INSTALL_DIR}/venv/bin/python" -m compileall -q \
    "${INSTALL_DIR}/app" \
    "${INSTALL_DIR}/scripts"

log "Установка systemd unit"

install -o root -g root -m 644 \
    "${INSTALL_DIR}/deploy/systemd/selfdocs.service" \
    /etc/systemd/system/selfdocs.service

systemctl daemon-reload

log "Установка nginx-конфигурации"

install -o root -g root -m 644 \
    "${INSTALL_DIR}/deploy/nginx/selfdocs.conf" \
    /etc/nginx/sites-available/selfdocs

ln -sfn \
    /etc/nginx/sites-available/selfdocs \
    /etc/nginx/sites-enabled/selfdocs

rm -f /etc/nginx/sites-enabled/default

nginx -t

log "Запуск SelfDocs и nginx"

systemctl enable --now selfdocs
systemctl enable --now nginx
systemctl reload nginx

sleep 2

if ! systemctl is-active --quiet selfdocs; then
    systemctl status selfdocs --no-pager -l || true
    journalctl -u selfdocs -n 100 --no-pager || true
    fail "Сервис SelfDocs не запустился."
fi

if ! curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    journalctl -u selfdocs -n 100 --no-pager || true
    fail "Health check не прошел."
fi

IP_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"

printf '\n'
printf 'SelfDocs установлен.\n'
printf 'Каталог: %s\n' "${INSTALL_DIR}"
printf 'Первоначальная настройка: http://%s/setup\n' "${IP_ADDRESS:-IP_СЕРВЕРА}"
printf '\n'
printf 'Логин и пароль заранее не создаются.\n'
printf 'При первом открытии необходимо пройти страницу /setup.\n'
