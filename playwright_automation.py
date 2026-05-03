"""
Apple ID Playwright Automation
"""
import asyncio
import random
import logging
import re
from typing import Optional

logger = logging.getLogger("apple_bot")
from playwright.async_api import async_playwright, Page

URL_SIGNIN = "https://account.apple.com/sign-in"
URL_MANAGE = "https://account.apple.com/account/manage"
URL_DEVICES = "https://account.apple.com/account/manage/section/devices"
URL_SECURITY = "https://account.apple.com/account/manage/section/security"
URL_FINDMY = "https://www.icloud.com/find/"
URL_MAIL = "https://www.icloud.com/mail/"


async def _rnd(lo=0.3, hi=0.9):
    await asyncio.sleep(random.uniform(lo, hi))


async def _screenshot(page) -> Optional[bytes]:
    try:
        return await page.screenshot(full_page=True)
    except:
        return None


def _all_targets(page):
    return [page] + list(page.frames)


async def _page_text(page) -> str:
    parts = []
    for t in _all_targets(page):
        try:
            txt = await t.evaluate("() => document.body ? document.body.innerText : ''")
            if txt:
                parts.append(txt)
        except:
            pass
    return " ".join(parts).lower()


async def _get_idmsa(page):
    for f in page.frames:
        if "idmsa.apple.com" in f.url:
            return f
    return page


async def _click_in_frames(page, texts: list, timeout=2500) -> bool:
    for target in _all_targets(page):
        for text in texts:
            try:
                btn = target.get_by_role("button", name=re.compile(re.escape(text), re.I)).first
                if await btn.is_visible(timeout=timeout):
                    await btn.click()
                    logger.info(f"[pw] clicked '{text}'")
                    return True
            except:
                pass
    return False


async def _fill_in_frames(page, selectors: list, value: str, timeout=2500) -> bool:
    for target in _all_targets(page):
        for sel in selectors:
            try:
                el = target.locator(sel).first
                if await el.is_visible(timeout=timeout):
                    await el.click()
                    await asyncio.sleep(0.25)
                    await el.fill(value)
                    if await el.input_value() == value:
                        logger.info(f"[pw] filled '{sel}'")
                        return True
            except:
                pass
    return False


async def _get_browser(account_id: str = "default"):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    )
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        locale="ru-RU",
        timezone_id="Europe/Moscow",
    )
    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        window.chrome = { runtime: {} };
    """)
    return pw, ctx


async def _new_page(ctx):
    return await ctx.new_page()


async def _answer_security_questions(page, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="") -> bool:
    logger.info(f"[secq] called q1={q1_answer} q2={q2_answer}")
    try:
        await asyncio.sleep(2)
        target = await _get_idmsa(page)
        ft = await target.evaluate("() => document.body.innerText || ''")
        ft_lower = ft.lower()
        
        all_qa = [(q1_text, q1_answer), (q2_text, q2_answer), (q3_text, q3_answer)]
        ordered_answers = []
        for qt, qa in all_qa:
            if qt and qa:
                if qt[:5].lower() in ft_lower or qt[:10].lower() in ft_lower:
                    ordered_answers.append(qa)
                    logger.info(f"[secq] matched: {qt[:25]} -> {qa}")
        if not ordered_answers:
            ordered_answers = [qa for qt, qa in all_qa if qt and qa]
        
        fillable = []
        for _ in range(10):
            loc = target.locator("input[type='password'], input[type='text']")
            cnt = await loc.count()
            if cnt >= 1:
                for i in range(cnt):
                    inp = loc.nth(i)
                    try:
                        vis = await inp.is_visible(timeout=1000)
                        ro = await inp.get_attribute("readonly")
                        dis = await inp.get_attribute("disabled")
                        if vis and ro is None and dis is None:
                            fillable.append(inp)
                    except:
                        pass
                if fillable:
                    break
            await asyncio.sleep(1)
        
        logger.info(f"[secq] fillable inputs: {len(fillable)}")
        if not fillable:
            return False
        
        filled = 0
        for i, inp in enumerate(fillable[:len(ordered_answers)]):
            ans = ordered_answers[i]
            try:
                await inp.scroll_into_view_if_needed()
                await inp.click()
                await asyncio.sleep(0.3)
                await inp.fill("")
                await inp.fill(ans)
                filled += 1
                await asyncio.sleep(0.4)
            except:
                try:
                    await inp.type(ans)
                    filled += 1
                except:
                    pass
        
        logger.info(f"[secq] filled {filled}/{len(ordered_answers)}")
        if filled == 0:
            return False
        
        await asyncio.sleep(0.5)
        clicked = await _click_in_frames(page, ["Продолжить", "Continue", "Далее", "Next"])
        if not clicked:
            try:
                await target.locator("body").press("Return")
            except:
                pass
        
        await asyncio.sleep(3)
        logger.info(f"[secq] url after: {page.url}")
        return True
    except Exception as e:
        logger.error(f"[secq] error: {e}")
        return False


async def do_login(
    page, email: str, password: str,
    q1_text: str, q1_answer: str,
    q2_text: str, q2_answer: str,
    q3_text: str = "", q3_answer: str = "",
    tfa_queue: Optional[asyncio.Queue] = None,
    on_step=None
) -> dict:
    """Вход в Apple ID. Возвращает {"ok": bool, "error": str, "screenshot": bytes}"""
    result = {"ok": False, "error": "", "screenshot": None}
    try:
        logger.info(f"[login] starting for {email}")
        await page.goto(URL_SIGNIN, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Email
        email_sels = [
            "input[type='email']", "input[name='accountName']",
            "input[autocomplete='username']", "input[type='text']"
        ]
        filled = False
        for _ in range(6):
            if await _fill_in_frames(page, email_sels, email):
                filled = True
                break
            await asyncio.sleep(1)
        if not filled:
            result["error"] = "Поле email не найдено"
            result["screenshot"] = await _screenshot(page)
            return result
        
        await _rnd(0.5, 1.0)
        await _click_in_frames(page, ["Продолжить", "Continue", "Next"])
        await asyncio.sleep(3)
        
        # Password
        pwd_sels = ["input[type='password']", "input[name='password']"]
        filled = False
        for _ in range(10):
            if "account/manage" in page.url:
                result["ok"] = True
                return result
            if await _fill_in_frames(page, pwd_sels, password, timeout=3000):
                filled = True
                break
            await asyncio.sleep(1)
        if not filled:
            result["error"] = "Поле пароля не найдено"
            result["screenshot"] = await _screenshot(page)
            return result
        
        await _rnd(0.5, 1.0)
        await _click_in_frames(page, ["Войти", "Sign In", "Продолжить", "Continue"])
        await asyncio.sleep(4)
        
        # Основной цикл обработки
        for attempt in range(25):
            await asyncio.sleep(2)
            url = page.url
            content = await _page_text(page)
            logger.info(f"[login] iter {attempt}: {url[:60]}")
            
            # Успех
            if "account/manage" in url or "appleid.apple.com" in url:
                logger.info(f"[login] SUCCESS")
                result["ok"] = True
                return result
            
            # Контрольные вопросы
            has_q = "контрольн" in content or "security question" in content or "ответьте" in content
            if has_q:
                logger.info("[login] >> security questions")
                ok = await _answer_security_questions(page, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer)
                if not ok:
                    result["error"] = "Не удалось ответить на вопросы"
                    result["screenshot"] = await _screenshot(page)
                    return result
                await asyncio.sleep(2)
                continue
            
            # 2FA
            if "verification code" in content or "код подтверждения" in content or "код" in content:
                logger.info("[login] >> 2FA required")
                if on_step:
                    await on_step("2fa_required", await _screenshot(page))
                if tfa_queue:
                    try:
                        code = await asyncio.wait_for(tfa_queue.get(), timeout=120)
                        for target in _all_targets(page):
                            try:
                                inputs = target.locator("input[maxlength='1']")
                                if await inputs.count() >= 6:
                                    for i, ch in enumerate(code[:6]):
                                        await inputs.nth(i).fill(ch)
                                    await _click_in_frames(page, ["Продолжить", "Continue"])
                                    break
                            except:
                                pass
                        await asyncio.sleep(3)
                        continue
                    except asyncio.TimeoutError:
                        result["error"] = "Таймаут 2FA"
                        result["screenshot"] = await _screenshot(page)
                        return result
                else:
                    result["error"] = "Требуется 2FA код"
                    result["screenshot"] = await _screenshot(page)
                    return result
            
            # Trust
            if "trust" in content or "доверять" in content:
                await _click_in_frames(page, ["Не сейчас", "Not Now"])
                await asyncio.sleep(2)
                continue
        
        result["error"] = "Превышено число попыток"
        result["screenshot"] = await _screenshot(page)
    except Exception as e:
        logger.error(f"[login] exception: {e}")
        result["error"] = str(e)
        result["screenshot"] = await _screenshot(page)
    return result


async def get_devices_info(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="", tfa_queue=None, on_step=None) -> dict:
    """Получить список устройств."""
    r = await do_login(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer, tfa_queue, on_step)
    if not r["ok"]:
        return {**r, "devices": []}
    
    try:
        await page.goto(URL_DEVICES, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        devices = []
        text = await _page_text(page)
        
        # Парсим устройства из текста
        for m in re.finditer(r"(iphone|ipad|mac[\w\s]*|apple watch)[\s\S]*?imei[:\s]*([0-9\s]{15,20})", text, re.I):
            devices.append({
                "model": m.group(1).strip(),
                "imei": m.group(2).strip().replace(" ", "")
            })
        
        r["ok"] = True
        r["devices"] = devices
    except Exception as e:
        r["error"] = str(e)
    return r


async def do_change_password(page, current_pass, new_pass, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="", tfa_queue=None, on_step=None) -> dict:
    """Сменить пароль."""
    r = await do_login(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer, tfa_queue, on_step)
    if not r["ok"]:
        return r
    
    try:
        await page.goto(URL_MANAGE, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await _click_in_frames(page, ["Пароль", "Password"])
        await asyncio.sleep(2)
        
        pwd_fields = page.locator("input[type='password']")
        cnt = await pwd_fields.count()
        if cnt >= 3:
            await pwd_fields.nth(0).fill(current_pass)
            await pwd_fields.nth(1).fill(new_pass)
            await pwd_fields.nth(2).fill(new_pass)
        elif cnt == 2:
            await pwd_fields.nth(0).fill(new_pass)
            await pwd_fields.nth(1).fill(new_pass)
        
        await _click_in_frames(page, ["Изменить", "Change", "Сохранить", "Save"])
        await asyncio.sleep(3)
        r["ok"] = True
    except Exception as e:
        r["error"] = str(e)
    return r


async def open_find_my(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="", tfa_queue=None, on_step=None) -> dict:
    """Открыть Find My."""
    r = await do_login(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer, tfa_queue, on_step)
    if not r["ok"]:
        return r
    
    try:
        await page.goto(URL_FINDMY, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        r["screenshot"] = await _screenshot(page)
        r["ok"] = True
    except Exception as e:
        r["error"] = str(e)
    return r


async def open_mail(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="", tfa_queue=None, on_step=None) -> dict:
    """Открыть почту."""
    r = await do_login(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer, tfa_queue, on_step)
    if not r["ok"]:
        return r
    
    try:
        await page.goto(URL_MAIL, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        r["screenshot"] = await _screenshot(page)
        r["ok"] = True
    except Exception as e:
        r["error"] = str(e)
    return r


async def get_security_info(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text="", q3_answer="", tfa_queue=None, on_step=None) -> dict:
    """Получить информацию о безопасности."""
    r = await do_login(page, email, password, q1_text, q1_answer, q2_text, q2_answer, q3_text, q3_answer, tfa_queue, on_step)
    if not r["ok"]:
        return r
    
    try:
        await page.goto(URL_SECURITY, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        text = await page.evaluate("() => document.body.innerText || ''")
        r["info"] = text[:2000]
        r["ok"] = True
    except Exception as e:
        r["error"] = str(e)
    return r
