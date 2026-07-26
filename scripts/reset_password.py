from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import set_credentials


def main() -> None:
    username = input("Имя пользователя [admin]: ").strip() or "admin"

    while True:
        password = getpass.getpass("Новый пароль: ")
        confirmation = getpass.getpass("Повтори пароль: ")

        if password != confirmation:
            print("Пароли не совпадают. Попробуй еще раз.")
            continue

        try:
            set_credentials(username, password)
        except ValueError as exc:
            print(f"Ошибка: {exc}")
            continue

        print("Учетные данные администратора обновлены.")
        return


if __name__ == "__main__":
    main()
