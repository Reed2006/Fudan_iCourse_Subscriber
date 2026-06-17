"""Minimal iCourse API client for enumerating lectures and extracting replay audio."""

from __future__ import annotations

import hashlib
import time
import uuid
from urllib.parse import urlparse

from src.api.webvpn import WebVPNSession, get_vpn_url
from src.runtime import config


class ICourseClient:
    def __init__(self, vpn_session: WebVPNSession):
        self.vpn = vpn_session
        self.base_url = config.ICOURSE_BASE
        self._userinfo = None

    def get_userinfo(self) -> dict:
        if self._userinfo is not None:
            return self._userinfo

        url = f"{self.base_url}/userapi/v1/infosimple"
        resp = self.vpn.get(url)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, 200):
            raise RuntimeError(f"Failed to get userinfo: {data.get('msg')}")

        self._userinfo = data.get("params") or data.get("data", {})
        return self._userinfo

    def check_alive(self) -> bool:
        try:
            resp = self.vpn.get(
                f"{self.base_url}/userapi/v1/infosimple",
                timeout=10,
            )
            return resp.status_code == 200 and resp.json().get("code") in (0, 200)
        except Exception:
            return False

    def sign_video_url(self, video_url: str, now: int | None = None) -> str:
        userinfo = self.get_userinfo()
        user_id = userinfo.get("id", "")
        tenant_id = userinfo.get("tenant_id", "")
        phone = str(userinfo.get("phone", ""))

        if now is None:
            now = int(time.time())

        reversed_phone = phone[::-1]
        pathname = urlparse(video_url).path
        hash_input = f"{pathname}{user_id}{tenant_id}{reversed_phone}{now}"
        md5_hash = hashlib.md5(hash_input.encode()).hexdigest()
        t_param = f"{user_id}-{now}-{md5_hash}"

        client_uuid = str(uuid.uuid4())
        sep = "&" if "?" in video_url else "?"
        return f"{video_url}{sep}clientUUID={client_uuid}&t={t_param}"

    def get_course_detail(self, course_id: str) -> dict:
        url = f"{self.base_url}/courseapi/v3/multi-search/get-course-detail"
        resp = self.vpn.get(url, params={"course_id": course_id})
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"API error for course {course_id}: {data.get('msg')}")

        course_data = data.get("data", {})
        lectures: list[dict] = []
        sub_list = course_data.get("sub_list", {})
        for year, months in sub_list.items():
            for month, days in months.items():
                for day, items in days.items():
                    for item in items:
                        if "id" not in item:
                            continue
                        lectures.append(
                            {
                                "sub_id": item["id"],
                                "sub_title": item.get("sub_title", ""),
                                "lecturer_name": item.get("lecturer_name", ""),
                                "date": f"{year}-{month}-{day}",
                                "has_playback": str(item.get("playback_status")) == "1",
                            }
                        )

        return {
            "title": course_data.get("title", "Unknown"),
            "teacher": course_data.get("realname", "Unknown"),
            "lectures": lectures,
        }

    def get_sub_detail(self, course_id: str, sub_id: str) -> dict:
        url = f"{self.base_url}/courseapi/v3/multi-search/get-sub-detail"
        resp = self.vpn.get(url, params={"course_id": course_id, "sub_id": sub_id})
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"API error for sub {sub_id}: {data.get('msg')}")
        return data.get("data", {})

    def get_sub_info(self, course_id: str, sub_id: str) -> dict:
        url = f"{self.base_url}/courseapi/v3/portal-home-setting/get-sub-info"
        resp = self.vpn.get(url, params={"course_id": course_id, "sub_id": sub_id})
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or {}
        if data.get("code") != 0 and not payload:
            raise RuntimeError(f"API error for sub-info {sub_id}: {data.get('msg')}")
        return payload

    def get_video_url(self, course_id: str, sub_id: str) -> str | None:
        try:
            info = self.get_sub_info(course_id, sub_id)
        except Exception as exc:
            print(f"    sub-info unavailable for {sub_id} ({type(exc).__name__}); falling back.")
            info = {}

        now = info.get("now")
        if isinstance(now, str):
            now = int(now)

        base_url = None

        video_list = info.get("video_list", {})
        if isinstance(video_list, dict):
            for video_item in video_list.values():
                if not isinstance(video_item, dict):
                    continue
                preview = video_item.get("preview_url")
                if preview and preview.endswith(".mp4"):
                    base_url = preview
                    break

        if not base_url:
            playurl = info.get("playurl", {})
            if isinstance(playurl, dict):
                for key, value in playurl.items():
                    if key == "now":
                        continue
                    if isinstance(value, str) and value.endswith(".mp4"):
                        base_url = value
                        break

        if not base_url:
            playback = (info.get("content") or {}).get("playback") or {}
            nested = playback.get("url")
            if isinstance(nested, str) and nested.endswith(".mp4"):
                base_url = nested
                if not now:
                    content_now = (info.get("content") or {}).get("now")
                    if isinstance(content_now, (int, str)):
                        now = int(content_now)

        if not base_url:
            try:
                detail = self.get_sub_detail(course_id, sub_id)
                playback = (detail.get("content") or {}).get("playback") or {}
                candidate = playback.get("url")
                if candidate:
                    base_url = candidate
            except Exception:
                pass

        if not base_url:
            return None

        return self.sign_video_url(base_url, now=now)

    def get_stream_params(self, video_url: str) -> tuple[str, str]:
        wrap_url = getattr(self.vpn, "wrap_url", get_vpn_url)
        stream_url = wrap_url(video_url)
        cookies = "; ".join(
            f"{cookie.name}={cookie.value}" for cookie in self.vpn.session.cookies
        )
        headers = f"Cookie: {cookies}\r\nUser-Agent: {config.USER_AGENT}\r\n"
        return stream_url, headers
