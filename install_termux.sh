#!/data/data/com.termux/files/usr/bin/bash
# Скрипт установки бота в Termux
# Запуск: chmod +x install_termux.sh && ./install_termux.sh

set -e

echo "=== Установка iCloud Monitor Bot в Termux ==="

# Обновление системы
echo "[1/5] Обновление системы..."
pkg update -y && pkg upgrade -y

# Установка Python и зависимостей
echo "[2/5] Установка Python и зависимостей..."
pkg install -y python git libffi openssl

# Установка pip зависимостей
echo "[3/5] Установка Python пакетов..."
pip install --upgrade pip
pip install aiogram==3.7.0 python-dotenv==1.0.1 cryptography==42.0.8 loguru==0.7.2

# Опционально: pandas и matplotlib (большие, можно пропустить)
echo "[4/5] Установка дополнительных пакетов (опционально)..."
pip install pandas matplotlib || echo "Пропущено (не критично)"

# Генерация FERNET_KEY если нет
if ! grep -q "^FERNET_KEY=." .env 2>/dev/null; then
    echo "[5/5] Генерация FERNET_KEY..."
    FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    if [ -f .env ]; then
        sed -i "s/^FERNET_KEY=.*/FERNET_KEY=$FERNET_KEY/" .env
    fi
    echo "FERNET_KEY сгенерирован: $FERNET_KEY"
else
    echo "[5/5] FERNET_KEY уже установлен"
fi

echo ""
echo "=== Установка завершена! ==="
echo ""
echo "Проверьте файл .env:"
echo "  cat .env"
echo ""
echo "Запуск бота:"
echo "  python main.py"
echo ""
echo "Для фонового запуска:"
echo "  nohup python main.py > bot.log 2>&1 &"
echo ""
