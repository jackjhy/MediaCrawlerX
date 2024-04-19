# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/2 18:44
# @Desc    : bilibili 请求客户端
import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import httpx
import config
import re
import subprocess
import shutil
import os
from playwright.async_api import BrowserContext, Page
import requests

from base.base_crawler import AbstactApiClient
from tools import utils

from .exception import DataFetchError
from .field import CommentOrderType, SearchOrderType
from .help import BilibiliSign


class BilibiliClient(AbstactApiClient):
    def __init__(
            self,
            timeout=10,
            proxies=None,
            *,
            headers: Dict[str, str],
            playwright_page: Page,
            cookie_dict: Dict[str, str],
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.headers = headers
        self._host = "https://api.bilibili.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict

    async def request(self, method, url, **kwargs) -> Any:
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(
                method, url, timeout=self.timeout,
                **kwargs
            )
        data: Dict = response.json()
        if data.get("code") != 0:
            raise DataFetchError(data.get("message", "unkonw error"))
        else:
            return data.get("data", {})

    async def text_request(self, method, url, **kwargs) -> str:
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(
                method, url, timeout=self.timeout,
                **kwargs
            )
            return response.text

    async def download(self,url,path,**kwargs) -> bool:
        try:
            response = requests.get(url=url,headers=self.headers,timeout=(5,15))
            # async with httpx.AsyncClient(proxies=self.proxies) as client:
            #     response = await client.request(
            #         'get', url, timeout=self.timeout,
            #         **kwargs
            #     )
            f = open(path, 'wb')
            f.write(response.content)
            f.close() 
            return True
        except Exception as e:
            utils.logger.error(f"[BilibiliCrawler.download] may be been blocked, err:{e}")
            return False
        

    async def pre_request_data(self, req_data: Dict) -> Dict:
        """
        发送请求进行请求参数签名
        需要从 localStorage 拿 wbi_img_urls 这参数，值如下：
        https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png-https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png
        :param req_data:
        :return:
        """
        if not req_data:
            return {}
        img_key, sub_key = await self.get_wbi_keys()
        return BilibiliSign(img_key, sub_key).sign(req_data)

    async def get_wbi_keys(self) -> Tuple[str, str]:
        """
        获取最新的 img_key 和 sub_key
        :return:
        """
        local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        wbi_img_urls = local_storage.get("wbi_img_urls", "") or local_storage.get(
            "wbi_img_url") + "-" + local_storage.get("wbi_sub_url")
        if wbi_img_urls and "-" in wbi_img_urls:
            img_url, sub_url = wbi_img_urls.split("-")
        else:
            resp = await self.request(method="GET", url=self._host + "/x/web-interface/nav")
            img_url: str = resp['wbi_img']['img_url']
            sub_url: str = resp['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return img_key, sub_key

    async def get(self, uri: str, params=None, enable_params_sign: bool = True) -> Dict:
        final_uri = uri
        if enable_params_sign:
            params = await self.pre_request_data(params)
        if isinstance(params, dict):
            final_uri = (f"{uri}?"
                        f"{urlencode(params)}")
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=self.headers)

    async def post(self, uri: str, data: dict) -> Dict:
        data = await self.pre_request_data(data)
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}",data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """get a note to check if login state is ok"""
        utils.logger.info("[BilibiliClient.pong] Begin pong bilibili...")
        ping_flag = False
        try:
            check_login_uri = "/x/web-interface/nav"
            response = await self.get(check_login_uri)
            if response.get("isLogin"):
                utils.logger.info("[BilibiliClient.pong] Use cache login state get web interface successfull!")
                ping_flag = True
        except Exception as e:
            utils.logger.error(f"[BilibiliClient.pong] Pong bilibili failed: {e}, and try to login again...")
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_video_by_keyword(self, keyword: str, page: int = 1, page_size: int = 20,
                                      order: SearchOrderType = SearchOrderType.DEFAULT):
        """
        KuaiShou web search api
        :param keyword: 搜索关键词
        :param page: 分页参数具体第几页
        :param page_size: 每一页参数的数量
        :param order: 搜索结果排序，默认位综合排序
        :return:
        """
        uri = "/x/web-interface/wbi/search/type"
        post_data = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": order.value
        }
        return await self.get(uri, post_data)

    async def get_video_info(self, aid: Union[int, None] = None, bvid: Union[str, None] = None) -> Dict:
        """
        Bilibli web video detail api, aid 和 bvid任选一个参数
        :param aid: 稿件avid
        :param bvid: 稿件bvid
        :return:
        """
        if not aid and not bvid:
            raise ValueError("请提供 aid 或 bvid 中的至少一个参数")

        uri = "/x/web-interface/view/detail"
        params = dict()
        if aid:
            params.update({"aid": aid})
        else:
            params.update({"bvid": bvid})
        return await self.get(uri, params, enable_params_sign=False)
    
    async def download_vedio(self,id:str):
        try:
            if not config.ENABLE_DOWNLOAD_VIDEO:
                utils.logger.info(f"[BilibiliCrawler.batch_download_videos] Crawling comment mode is not enabled")
                return

            res = await self.text_request(method='get',url=f'https://www.bilibili.com/video/av{id}/',headers=self.headers)
        
            # 获取window.__playinfo__的json对象,[20:]表示截取'window.__playinfo__='后面的json字符串
            videoPlayInfo = re.findall('<script>window\.__playinfo__=(.*?)</script>',res)[0]
            videoJson = json.loads(videoPlayInfo)
            # 获取视频链接和音频链接
            # 2018年以后的b站视频由.audio和.video组成 flag=0表示分为音频与视频
            videos = videoJson['data']['dash']['video']
            audios = videoJson['data']['dash']['audio']
            v_url = videos[0]['baseUrl']
            if v_url:
                if await self.download(v_url,f'data/bilibili/{id}.mp4',headers=self.headers):
                    if audios:
                        a_url = audios[0]['baseUrl']
                        if await self.download(a_url,f'data/bilibili/{id}.mp3',headers=self.headers):
                            # ffmpeg = f'ffmpeg -i data/bilibili/{id}.mp4 -i data/bilibili/{id}.mp3 -acodec copy -vcodec copy data/bilibili/{id}_c.mp4'
                            subprocess.run(['ffmpeg','-i',f'data/bilibili/{id}.mp4','-i',f'data/bilibili/{id}.mp3','-acodec', 'copy','-vcodec','copy',f'data/bilibili/{id}_c.mp4'])
                            os.remove(f'data/bilibili/{id}.mp3')
                            os.remove(f'data/bilibili/{id}.mp4')
                            shutil.move(f'data/bilibili/{id}_c.mp4',f'data/bilibili/{id}.mp4')
                subprocess.call(['ffmpeg', '-i', f'data/bilibili/{id}.mp4','-ss','00:00:05', '-f','image2', '-frames:v', '1','-q:v','2', '-y',f'data/bilibili/{id}.jpeg'])
            else:
                videoURL = videoJson['data']['durl'][0]['url']
                if await self.download(videoURL,f'data/bilibili/{id}.flv',headers=self.headers):
                    subprocess.call(['ffmpeg', '-i', f'data/bilibili/{id}.flv','-ss','00:00:05', '-f','image2', '-frames:v', '1','-q:v','2', '-y',f'data/bilibili/{id}.jpeg'])
        except Exception as e:
            utils.logger.info(f"[BilibiliCrawler.batch_download_videos] download failed {id}",e)

    async def get_video_comments(self,
                                 video_id: str,
                                 order_mode: CommentOrderType = CommentOrderType.DEFAULT,
                                 next: int = 0
                                 ) -> Dict:
        """get video comments
        :param video_id: 视频 ID
        :param order_mode: 排序方式
        :param next: 评论页选择
        :return:
        """
        uri = "/x/v2/reply/wbi/main"
        post_data = {
            "oid": video_id,
            "mode": order_mode.value,
            "type": 1,
            "ps": 20,
            "next": next
        }
        return await self.get(uri, post_data)

    async def get_video_all_comments(self, video_id: str, crawl_interval: float = 1.0, is_fetch_sub_comments=False,
                                     callback: Optional[Callable] = None, ):
        """
        get video all comments include sub comments
        :param video_id:
        :param crawl_interval:
        :param is_fetch_sub_comments:
        :param callback:
        :return:
        """

        result = []
        is_end = False
        next_page =0
        while not is_end:
            comments_res = await self.get_video_comments(video_id, CommentOrderType.DEFAULT, next_page)
            curson_info: Dict = comments_res.get("cursor")
            comment_list: List[Dict] = comments_res.get("replies", [])
            is_end = curson_info.get("is_end")
            next_page = curson_info.get("next")
            if callback:  # 如果有回调函数，就执行回调函数
                await callback(video_id, comment_list)
            await asyncio.sleep(crawl_interval)
            if not is_fetch_sub_comments:
                result.extend(comment_list)
                continue
            # todo handle get sub comments
        return result
