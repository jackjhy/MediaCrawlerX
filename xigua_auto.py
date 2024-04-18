from playwright.sync_api import Playwright, sync_playwright, expect
import re

def run(playwright: Playwright,video:dict,state_storage:str) -> None:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=state_storage)
    page = context.new_page()
    page.goto("https://studio.ixigua.com/upload")
    # page.get_by_text("发布视频").click()
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("点击上传或将文件拖入此区域").click()
    file_chooser = fc_info.value
    file_chooser.set_files(video.get("url"))
    # page.locator("body").set_input_files("./data/kuaishou/3xc4x9nmqa5825y.mp4")
    # page.pause()
    # page.wait_for_timeout(5000)
    page.locator("div").filter(has_text=re.compile(r"^上传成功$")).wait_for()
    # page.locator("div").filter(has_text=re.compile(r"^5-30个字符，标题含有关键词，可以被更多人看到0/30$")).get_by_role("combobox").locator("div").nth(2).click()
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
    page.wait_for_timeout(5000)
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    video = dict(
        name='什么都不是',
        url='./data/kuaishou/3xc4x9nmqa5825y.mp4',
        cover_url='',
        topic='网海钩陈'
    )
    run(playwright,video,state_storage='./auth/state.json')
