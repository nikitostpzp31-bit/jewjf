import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ru-RU")
        page = await context.new_page()
        
        # Заходим на страницу авторизации Apple (эмулируем вход)
        await page.goto("https://appleid.apple.com/sign-in")
        await asyncio.sleep(2)
        
        # Вводим логин и пароль (нужны реальные данные, но мы просто посмотрим)
        # Пропускаем — нам нужно сохранить HTML страницы с вопросами
        
        # Сохраняем HTML всей страницы
        html = await page.content()
        with open("/tmp/apple_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML сохранён в /tmp/apple_page.html")
        print(f"Размер: {len(html)} символов")
        
        # Также скриншот
        await page.screenshot(path="/tmp/apple_page_full.png")
        print("Скриншот сохранён")
        
        await browser.close()

asyncio.run(main())
