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

        # 確保開啟骨架
        skeleton_btn = page.locator('button:has-text("顯示人體骨架連線"), button:has-text("隱藏人體骨架")')
        if skeleton_btn.count() > 0:
            txt = skeleton_btn.first.inner_text()
            if "隱藏" not in txt:
                skeleton_btn.first.click()
                time.sleep(0.5)

        phases = ["address", "top", "downswing", "impact", "finish"]
        for phase in phases:
            print(f"Seeking to {phase}...")
            # 尋找包含該 phase 的按鈕
            btn = page.locator(f'button:has-text("{phase}")')
            if btn.count() > 0:
                btn.first.click()
                time.sleep(1.0)
            else:
                print(f"Button for {phase} not found, trying fuzzy match...")
                if phase == "impact":
                    b2 = page.locator('button:has-text("impact_estimated")')
                    if b2.count() > 0:
                        b2.first.click()
                        time.sleep(1.0)

            # 截取播放器區域或整個頁面上半部
            player_el = page.locator('.relative.overflow-hidden.rounded-2xl')
            if player_el.count() > 0:
                player_el.first.screenshot(path=f'docs/screenshots/baseline_clean_redesign/01_baseline_{phase}.png')
            else:
                page.screenshot(path=f'docs/screenshots/baseline_clean_redesign/01_baseline_{phase}.png')
            print(f"Captured 01_baseline_{phase}.png")

        browser.close()
        print("All baseline keyframes captured successfully!")

if __name__ == '__main__':
    main()
