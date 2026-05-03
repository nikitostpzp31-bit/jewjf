import asyncio
import logging
import re

logger = logging.getLogger(__name__)

# ТВОИ ТОЧНЫЕ ОТВЕТЫ
QA_MAP = {
    "你少年时代最好的朋友叫什么名字": "py777",
    "你少年时代最好的朋友叫什么名字？": "py777",
    "你的理想工作是什么": "gz777",
    "你的理想工作是什么？": "gz777",
    "你的父母是在哪里认识的": "fm777",
    "你的父母是在哪里认识的？": "fm777",
}

FALLBACK_ORDER = ["py777", "gz777", "fm777"]

def _norm(t):
    if not t:
        return ""
    return re.sub(r'[？?！!，、。.\s\u3000\uff1f\uff01\uff0c\u3001\u3002]', '', t).strip().lower()

def _log(msg):
    print(f"[apple_signin] {msg}", flush=True)
    logger.info(msg)

async def fill_security_questions(page, q1_text=None, q1_answer=None, q2_text=None, q2_answer=None, q3_text=None, q3_answer=None, sq_queue=None):
    _log("=" * 70)
    _log("FILL_SECURITY_QUESTIONS vFINAL STARTED")
    _log("=" * 70)

    try:
        await page.screenshot(path="/tmp/apple_sec_before.png")
        _log("📸 BEFORE screenshot saved")
    except: pass

    await asyncio.sleep(2)

    try:
        txt = await page.evaluate("() => document.body.innerText")
        _log(f"PAGE TEXT (first 2000 chars):\n{txt[:2000]}")
    except Exception as e:
        _log(f"get text error: {e}")

    # Ищем поля ввода
    inputs = []
    for selector in ["input[type='text']", "input:not([type='hidden']):not([type='password'])", "input"]:
        try:
            els = await page.query_selector_all(selector)
            _log(f"Selector {selector} → {len(els)} inputs")
            if els:
                inputs = els
                break
        except: pass

    _log(f"TOTAL INPUTS FOUND: {len(inputs)}")

    if not inputs:
        _log("❌ NO INPUT FIELDS")
        return False

    filled = 0
    for idx, inp in enumerate(inputs[:3]):
        # Получаем текст вопроса над полем
        question_text = ""
        try:
            question_text = await inp.evaluate("""el => {
                let prev = el.previousElementSibling;
                if (prev && prev.innerText && prev.innerText.trim().length > 3) return prev.innerText.trim();
                let parent = el.parentElement;
                if (parent) {
                    for (let c of parent.children) {
                        if (c !== el && c.innerText && c.innerText.trim().length > 3 && !c.querySelector('input')) {
                            return c.innerText.trim();
                        }
                    }
                }
                if (el.id) {
                    let label = document.querySelector('label[for="' + el.id + '"]');
                    if (label) return label.innerText.trim();
                }
                return el.placeholder || '';
            }""")
        except: pass

        clean_q = _norm(question_text)
        _log(f"FIELD {idx+1} question: '{question_text[:100]}' → clean: '{clean_q}'")

        # Ищем совпадение
        answer = None
        for known_q, known_a in QA_MAP.items():
            if _norm(known_q) == clean_q or _norm(known_q) in clean_q or clean_q in _norm(known_q):
                answer = known_a
                _log(f"✅ MATCH FOUND: {known_a}")
                break

        if not answer:
            if idx < len(FALLBACK_ORDER):
                answer = FALLBACK_ORDER[idx]
                _log(f"🔄 FALLBACK {idx+1}: {answer}")
            else:
                answer = FALLBACK_ORDER[-1]

        # Заполняем
        try:
            await inp.scroll_into_view_if_needed()
            await inp.click()
            await asyncio.sleep(0.3)
            await inp.fill(answer)
            filled += 1
            _log(f"✅ FILLED field {idx+1} with {answer}")
        except Exception as e:
            _log(f"Fill error: {e}")
            try:
                await inp.type(answer)
                filled += 1
                _log(f"✅ TYPE fallback worked")
            except: pass

    _log(f"FILLED {filled} fields")

    # Кнопка
    clicked = False
    for btn_sel in ["button:has-text('Продолжить')", "button:has-text('Continue')", "button[type='submit']", "button"]:
        try:
            btn = await page.query_selector(btn_sel)
            if btn:
                await btn.click()
                clicked = True
                _log(f"✅ CLICKED button {btn_sel}")
                break
        except: pass

    if not clicked:
        await page.keyboard.press("Enter")
        _log("✅ PRESSED Enter")

    await asyncio.sleep(4)

    try:
        await page.screenshot(path="/tmp/apple_sec_after.png")
        _log("📸 AFTER screenshot saved")
    except: pass

    _log("FINISHED fill_security_questions")
    return True


# Вспомогательные функции
async def get_browser(account_id: int):
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = await browser.new_context(locale="ru-RU")
    return browser, context

async def new_page(ctx):
    return await ctx.new_page()
