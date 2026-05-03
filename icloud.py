"""
Selenium-автоматизация Apple iCloud (fallback для Playwright).
"""
import asyncio
import os
import shutil
import time
from typing import Optional

import db
from logger import get_logger

logger = get_logger()

URL_FINDMY = "https://www.icloud.com/find/"
URL_MAIL = "https://www.icloud.com/mail/"
URL_MANAGE = "https://account.apple.com/account/manage"
URL_DEVICES = "https://account.apple.com/account/manage/section/devices"

WAIT_SHORT = 8
WAIT_MEDIUM = 15
WAIT_LONG = 30

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

def _get_driver(acc_id: Optional[int] = None, headless: bool = True):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1400,900")
        opts.add_argument("--lang=ru-RU,ru")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        if acc_id is not None:
            profile_dir = os.path.abspath(f"{SESSIONS_DIR}/{acc_id}")
            os.makedirs(profile_dir, exist_ok=True)
            opts.add_argument(f"--user-data-dir={profile_dir}")

        driver = webdriver.Chrome(options=opts)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        logger.error(f"[icloud] WebDriver init error: {e}")
        return None

def clear_session(acc_id: int) -> None:
    path = os.path.abspath(f"{SESSIONS_DIR}/{acc_id}")
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
    logger.info(f"[icloud] session cleared for acc_id={acc_id}")

def apple_login(
    email: str,
    password: str,
    acc_id: int,
    target_url: str = URL_FINDMY,
    tfa_queue: Optional[asyncio.Queue] = None,
    main_loop=None,
) -> Optional[object]:
    """Selenium-based login (fallback)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    driver = _get_driver(acc_id=acc_id)
    if not driver:
        return None

    try:
        logger.info(f"[icloud] login → {target_url} for {email}")
        driver.get(target_url)
        time.sleep(3)

        # Check if already logged in
        current = driver.current_url.lower()
        if "signin" not in current and "auth" not in current:
            if target_url.split("/")[2] in current or "icloud.com" in current:
                logger.info(f"[icloud] session reused for {email}")
                db.update_last_login(acc_id)
                return driver

        # Email input
        email_sels = [
            (By.CSS_SELECTOR, "input[name='accountName']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.ID, "account_name_text_field"),
        ]
        el = None
        for by, sel in email_sels:
            try:
                el = driver.find_element(by, sel)
                if el.is_displayed():
                    break
            except Exception:
                el = None
        
        if not el:
            logger.error("[icloud] email field not found")
            driver.quit()
            return None
        
        el.clear()
        el.send_keys(email)
        time.sleep(0.5)
        el.send_keys(Keys.RETURN)
        time.sleep(2)

        # Password input
        pwd_sels = [
            (By.CSS_SELECTOR, "input[name='password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.ID, "password_text_field"),
        ]
        pwd_el = None
        for by, sel in pwd_sels:
            try:
                pwd_el = driver.find_element(by, sel)
                if pwd_el.is_displayed():
                    break
            except Exception:
                pwd_el = None
        
        if not pwd_el:
            logger.error("[icloud] password field not found")
            driver.quit()
            return None
        
        pwd_el.clear()
        pwd_el.send_keys(password)
        time.sleep(0.5)
        pwd_el.send_keys(Keys.RETURN)
        time.sleep(3)

        db.update_last_login(acc_id)
        logger.info(f"[icloud] logged in: {email}")
        return driver

    except Exception as e:
        logger.error(f"[icloud] login error: {e}")
        try:
            driver.quit()
        except Exception:
            pass
        return None

def fetch_devices_findmy(driver, acc_id: int) -> list[dict]:
    """Парсит устройства со страницы Find My."""
    from selenium.webdriver.common.by import By
    import re
    devices = []
    try:
        driver.get(URL_FINDMY)
        time.sleep(5)
        
        items = driver.find_elements(By.CSS_SELECTOR, "[class*='device'], [class*='Device']")
        for item in items:
            try:
                text = item.text
                name = text.split("\n")[0] if "\n" in text else text[:50]
                imei = ""
                imei_match = re.search(r"IMEI[:\s]+(\d{15})", text)
                if imei_match:
                    imei = imei_match.group(1)
                if name:
                    dev = {"device_id": name, "name": name, "model": "", "imei": imei, "status": "online"}
                    devices.append(dev)
                    db.upsert_device(acc_id, dev)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[icloud] fetch_devices_findmy error: {e}")
    return devices
