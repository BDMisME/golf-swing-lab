import time
from playwright.sync_api import sync_playwright

SWING_ID = "5b8a6638-0610-4619-9063-dac118dd4043"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            headless=True
        )
        context = browser.new_context(viewport={'width': 1280, 'height': 850})
        page = context.new_page()

        print("Navigating to login...")
        page.goto('http://localhost:23000/login')
        page.fill('input[type="email"]', 'golfer@swinglab.local')
        page.fill('input[type="password"]', 'GolfSwingLab!2026')
        page.click('button[type="submit"]')
        page.wait_for_url('http://localhost:23000/', timeout=5000)

        print(f"Navigating to swing {SWING_ID}...")
        page.goto(f'http://localhost:23000/swings/{SWING_ID}')
        page.wait_for_load_state('networkidle')
        time.sleep(3)

        phases = ["address", "top", "downswing", "impact", "finish"]
        for phase in phases:
            print(f"Seeking to {phase} in Clean Coach Mode...")
            btn = page.locator(f'button:has-text("{phase}")')
            if btn.count() > 0:
                btn.first.click()
                time.sleep(1.0)
            else:
                if phase == "impact":
                    b2 = page.locator('button:has-text("impact_estimated")')
                    if b2.count() > 0:
                        b2.first.click()
                        time.sleep(1.0)

            player_el = page.locator('.relative.overflow-hidden.rounded-2xl')
            if player_el.count() > 0:
                player_el.first.screenshot(path=f'docs/screenshots/redesign_clean_motion/02_redesign_{phase}.png')
            else:
                page.screenshot(path=f'docs/screenshots/redesign_clean_motion/02_redesign_{phase}.png')
            print(f"Captured 02_redesign_{phase}.png")

        # 測試切換至專業分析模式 (Pro Mode)
        print("Testing Pro Mode toggle...")
        pro_btn = page.locator('button:has-text("專業分析模式")')
        if pro_btn.count() > 0:
            pro_btn.first.click()
            time.sleep(0.8)
            # 打開骨架開關
            skel_btn = page.locator('button:has-text("人體 33 點骨架"), button:has-text("人體骨架")')
            if skel_btn.count() > 0:
                skel_btn.first.click()
                time.sleep(0.5)
            player_el = page.locator('.relative.overflow-hidden.rounded-2xl')
            if player_el.count() > 0:
                player_el.first.screenshot(path='docs/screenshots/redesign_clean_motion/03_redesign_pro_mode.png')
            print("Captured 03_redesign_pro_mode.png")

        # 截取全頁面 (包含 AI 專屬體感洞察與 Drill 卡片)
        page.screenshot(path='docs/screenshots/redesign_clean_motion/04_full_page_insights_and_drills.png', full_page=True)
        print("Captured 04_full_page_insights_and_drills.png")

        browser.close()
        print("All redesign keyframes captured successfully!")

if __name__ == '__main__':
    main()
