#!/usr/bin/env python3
"""Тестовый скрипт для проверки отправки email через Gmail SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'heelpeers@gmail.com'
SMTP_PASS = 'cmthypytlhplzuig'
SMTP_FROM = 'heelpeers@gmail.com'
TEST_EMAIL = 'lamperougeees@gmail.com'
TEST_CODE = '123456'

print(f"[TEST] Подключение к {SMTP_HOST}:{SMTP_PORT}...")
print(f"[TEST] Использование пользователя: {SMTP_USER}")

try:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Yukitery — тестовый код: {TEST_CODE}'
    msg['From'] = SMTP_FROM
    msg['To'] = TEST_EMAIL
    
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0f0f14;color:#e0e0e0;border-radius:12px;">
        <h2 style="color:#a78bfa;margin:0 0 16px;">Yukitery</h2>
        <p>Тестовый код подтверждения:</p>
        <div style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#fff;background:#1a1a2e;padding:16px 24px;border-radius:8px;text-align:center;margin:16px 0;">
            {TEST_CODE}
        </div>
    </div>
    """
    msg.attach(MIMEText(html, 'html'))
    
    print("[TEST] Подключение к SMTP серверу...")
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.ehlo()
    print("[TEST] Запуск TLS...")
    server.starttls()
    server.ehlo()
    print(f"[TEST] Логин как {SMTP_USER}...")
    server.login(SMTP_USER, SMTP_PASS)
    print("[TEST] Отправка письма...")
    server.sendmail(SMTP_FROM, TEST_EMAIL, msg.as_string())
    server.quit()
    print("[SUCCESS] Письмо отправлено успешно!")
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()
