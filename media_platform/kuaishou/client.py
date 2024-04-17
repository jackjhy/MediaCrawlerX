# -*- coding: utf-8 -*-
import asyncio
import json
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode
import re
import subprocess

import httpx
from playwright.async_api import BrowserContext, Page

import config
from base.base_crawler import AbstactApiClient
from tools import utils

from .exception import DataFetchError
from .graphql import KuaiShouGraphQL


class KuaiShouClient(AbstactApiClient):
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
        self._host = "https://www.kuaishou.com/graphql"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self.graphql = KuaiShouGraphQL()

    async def request(self, method, url, **kwargs) -> Any:
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(
                method, url, timeout=self.timeout,
                **kwargs
            )
        data: Dict = response.json()
        if data.get("errors"):
            raise DataFetchError(data.get("errors", "unkonw error"))
        else:
            return data.get("data", {})

    async def text_request(self, method, url, **kwargs) -> str:
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(
                method, url, timeout=self.timeout,
                **kwargs
            )
            return response.text()

    async def download(self,url,path,**kwargs):
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(
                'get', url, timeout=self.timeout,
                **kwargs
            )
            
            f = open(path, 'wb')
            f.write(response.content)
            f.close() 

    async def get(self, uri: str, params=None) -> Dict:
        final_uri = uri
        if isinstance(params, dict):
            final_uri = (f"{uri}?" f"{urlencode(params)}")
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=self.headers)

    async def post(self, uri: str, data: dict) -> Dict:
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """get a note to check if login state is ok"""
        utils.logger.info("[KuaiShouClient.pong] Begin pong kuaishou...")
        ping_flag = False
        try:
            post_data = {
                "operationName": "visionProfileUserList",
                "variables": {
                    "ftype": 1,
                },
                "query": self.graphql.get("vision_profile")
            }
            res = await self.post("", post_data)
            if res.get("visionProfileUserList", {}).get("result") == 1:
                ping_flag = True
        except Exception as e:
            utils.logger.error(f"[KuaiShouClient.pong] Pong kuaishou failed: {e}, and try to login again...")
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_info_by_keyword(self, keyword: str, pcursor: str):
        """
        KuaiShou web search api
        :param keyword: search keyword
        :param pcursor: limite page curson
        :return:
        """
        post_data = {
            "operationName": "visionSearchPhoto",
            "variables": {
                "keyword": keyword,
                "pcursor": pcursor,
                "page": "search"
            },
            "query": self.graphql.get("search_query")
        }
        return await self.post("", post_data)

    async def download_video(self,video_item: Dict):
        if not config.ENABLE_DOWNLOAD_VIDEO:
            utils.logger.info(f"[KuaishouCrawler.batch_download_videos] Crawling comment mode is not enabled")
            return
        url = video_item.get("photo", {}).get('photoUrl','')
        if not url:
            return
        if url.find('m3u8') < 0:
            photo_id = video_item.get("photo", {}).get('id','')
            await self.download(url,f'data/kuaishou/{photo_id}.mp4',headers=self.headers)
        else:
            m3u8 = await self.text_request('get', url, timeout=self.timeout,headers=self.headers)
            ts_match = re.sub('#E.*', '', m3u8).split()
            ts_urls = [f"{url.rsplit('/',1)[0]}/{ts_url}" for ts_url in ts_match]
            for i,ts_url in enumerate(ts_urls):
                await self.download(ts_url,f'data/kuaishou/{photo_id}_{i}.ts',headers=self.headers)
            subprocess.call(['ffmpeg', '-i', 'concat:'+'|'.join([f"data/kuaishou/{photo_id}_{i}.ts" for i in range(len(ts_urls))]),'-c','copy', '-y',f'data/kuaishou/{photo_id}_c.mp4'])

            
    async def get_video_info(self, photo_id: str) -> Dict:
        """
        Kuaishou web video detail api
        :param photo_id:
        :return:
        """
        post_data = {
            "operationName": "visionVideoDetail",
            "variables": {
                "photoId": photo_id,
                "page": "search"
            },
            "query": self.graphql.get("video_detail")
        }
        return await self.post("", post_data)

    async def get_video_comments(self, photo_id: str, pcursor: str = "") -> Dict:
        """get video comments
        :param photo_id: photo id you want to fetch
        :param pcursor: last you get pcursor, defaults to ""
        :return:
        """
        post_data = {
            "operationName": "commentListQuery",
            "variables": {
                "photoId": photo_id,
                "pcursor": pcursor
            },
            "query": self.graphql.get("comment_list")

        }
        return await self.post("", post_data)

    async def get_video_all_comments(self, photo_id: str, crawl_interval: float = 1.0, is_fetch_sub_comments=False,
                                        callback: Optional[Callable] = None):
        """
        get video all comments include sub comments
        :param photo_id:
        :param crawl_interval:
        :param is_fetch_sub_comments:
        :param callback:
        :return:
        """

        result = []
        pcursor = ""

        while pcursor != "no_more":
            comments_res = await self.get_video_comments(photo_id, pcursor)
            vision_commen_list = comments_res.get("visionCommentList", {})
            pcursor = vision_commen_list.get("pcursor", "")
            comments = vision_commen_list.get("rootComments", [])

            if callback:  # 如果有回调函数，就执行回调函数
                await callback(photo_id, comments)

            result.extend(comments)
            await asyncio.sleep(crawl_interval)
            if not is_fetch_sub_comments:
                continue
            # todo handle get sub comments
        return result
