from playwright.sync_api import Playwright, sync_playwright, expect,Page
import datetime,json,re,subprocess
from random import randint

def run(playwright: Playwright,video:dict,state_storage:str) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state=state_storage)
    page = context.new_page()
    try:
        page.goto("https://studio.ixigua.com/upload")
        page.pause()
        with page.expect_file_chooser() as fc_info:
            page.get_by_text("点击上传或将文件拖入此区域").click()
        file_chooser = fc_info.value
        file_chooser.set_files(video.get("url"))
        page.pause()
        page.locator("div").filter(has_text=re.compile(r"^上传成功$")).wait_for(timeout=120000)

        if page.locator("div").filter(has_text=re.compile(r"^5-30个字符，标题含有关键词，可以被更多人看到0/30$")).is_visible():
            page_w(page,video)
        else:
            page_h(page,video)
        page.wait_for_timeout(5000)
    finally:
        page.close()
        context.close()
        browser.close()
    
def page_w(page:Page,video:dict) -> None:
    page.locator("div").filter(has_text=re.compile(r"^5-30个字符，标题含有关键词，可以被更多人看到0/30$")).get_by_role("combobox").fill(video.get("name","什么都不是"))
    # page.get_by_placeholder("输入合适的话题").click()
    page.get_by_placeholder("输入合适的话题").fill(video.get("topic","网海钩陈"))
    page.pause()
    page.get_by_text("什么都不是5/30@ 提到").click()
    page.locator("div").filter(has_text=re.compile(r"^上传封面$")).nth(2).click()
    page.get_by_text("本地上传").click()
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("点击上传或将图片拖入此区域").click()
    file_chooser = fc_info.value
    file_chooser.set_files(video.get("cover_url"))
    page.get_by_text("完成裁剪", exact=True).click()
    page.get_by_role("button", name="确定").click()
    page.pause()
    page.locator("div").filter(has_text=re.compile(r"^取消确定$")).get_by_role("button", name="确定").click()
    # page.locator("label").filter(has_text="转载").locator("div").click()
    page.locator("label").filter(has_text="原创").locator("div").click()
    page.get_by_role("button", name="发布").click()
    
def page_h(page:Page,video:dict) -> None:
    page.get_by_role("combobox").locator("div").nth(2).click()
    page.get_by_role("combobox").fill(video.get("name","什么都不是"))
    page.locator("div").filter(has_text=re.compile(r"^上传封面清晰美观的封面有利于推荐$")).get_by_role("img").click()
    page.get_by_text("本地上传").click()
    page.pause()
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("点击上传或将图片拖入此区域").click()
    file_chooser = fc_info.value
    file_chooser.set_files(video.get("cover_url"))
    page.get_by_role("button", name="确定").click()
    page.pause()
    page.locator("div").filter(has_text=re.compile(r"^取消确定$")).get_by_role("button", name="确定").click()
    page.get_by_role("button", name="发布").click()    


with sync_playwright() as playwright:
    dt = datetime.datetime.today().strftime('%Y-%m-%d')
    flag = False
    for pt in ['bilibili','kuaishou']:
        if not flag:
            with open(f'./data/{pt}/search_contents_{dt}.json', 'rb') as f:
                content:dict = json.load(f)
                while not flag:
                    try:
                        idx = randint(0,len(content)-1)
                        item:dict = content[idx]
                        id = item.get('video_id')
                        print(f'try to upload {id} at {pt}')
                        video = dict(
                            name=item.get('title'),
                            url=f'./data/{pt}/{id}.mp4',
                            cover_url=f'./data/{pt}/{id}.jpeg',
                            topic='网海钩陈'
                        )
                        run(playwright,video,state_storage='./auth/state.json')
                        flag = True
                    except Exception as e:
                        flag = False
            subprocess.call(['rm', '-rf', f'data/{pt}/*'])