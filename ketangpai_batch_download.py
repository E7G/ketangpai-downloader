#!/usr/bin/env python3
"""
课堂派课程资料批量下载工具

编辑 config.json 后运行:
  python ketangpai_batch_download.py

获取 token: 浏览器登录课堂派 -> F12 -> Application -> Local Storage -> token
查看课程 ID: config.json 中设置 "list_courses": true 后运行一次
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

LogFn = Callable[[str], None]

import requests

BASE_URL = "https://openapiv5.ketangpai.com"
CONTENT_TYPE_MATERIAL = 2
PAGE_SIZE = 50
REQUEST_TIMEOUT = 60
DEFAULT_CONFIG = Path("config.json")


class KetangpaiClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://w.ketangpai.com/",
                "Content-Type": "application/json;charset=UTF-8",
                "token": token,
            }
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {**payload, "reqtimestamp": int(time.time() * 1000)}
        resp = self.session.post(
            f"{BASE_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 1:
            raise RuntimeError(data.get("message") or f"API 错误: {path}")
        return data.get("data") or {}

    @staticmethod
    def login(email: str, password: str) -> str:
        resp = requests.post(
            f"{BASE_URL}/UserApi/login",
            json={
                "email": email,
                "password": password,
                "remember": "0",
                "code": "",
                "mobile": "",
                "type": "login",
                "reqtimestamp": int(time.time() * 1000),
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 1:
            raise RuntimeError(data.get("message") or "登录失败")
        token = data.get("data", {}).get("token")
        if not token:
            raise RuntimeError("登录响应中未找到 token")
        return token

    def list_courses(self) -> list[dict[str, Any]]:
        data = self._post(
            "/CourseApi/semesterCourseList",
            {"isstudy": 1, "search": ""},
        )
        if isinstance(data, list):
            return data
        return data.get("list") or data.get("courseList") or []

    def list_materials_flat(self, course_id: str) -> list[dict[str, Any]]:
        all_files: list[dict[str, Any]] = []
        self._walk_materials(course_id, drid=0, path_parts=[], out=all_files)
        return all_files

    def _walk_materials(
        self,
        course_id: str,
        drid: int,
        path_parts: list[str],
        out: list[dict[str, Any]],
    ) -> None:
        page = 1
        while True:
            data = self._post(
                "/FutureV2/CourseMeans/getCourseContent",
                {
                    "contenttype": CONTENT_TYPE_MATERIAL,
                    "courseid": course_id,
                    "coruserole": 0,
                    "desc": 3,
                    "drid": drid,
                    "lessonlink": [],
                    "limit": PAGE_SIZE,
                    "page": page,
                },
            )
            items = data.get("list") or []
            if not items:
                break

            for item in items:
                if self._is_folder(item):
                    folder_name = sanitize_filename(
                        item.get("title") or item.get("name") or f"folder_{item.get('id')}"
                    )
                    sub_drid = int(item.get("id") or 0)
                    self._walk_materials(
                        course_id, sub_drid, path_parts + [folder_name], out
                    )
                else:
                    item["_relative_dir"] = os.path.join(*path_parts) if path_parts else ""
                    out.append(item)

            if len(items) < PAGE_SIZE:
                break
            page += 1

    def get_file_detail(self, course_id: str, file_id: str) -> dict[str, Any]:
        return self._post(
            "/FutureV2/Courseware/query",
            {
                "id": file_id,
                "courseid": course_id,
                "contenttype": str(CONTENT_TYPE_MATERIAL),
            },
        )

    @staticmethod
    def _is_folder(item: dict[str, Any]) -> bool:
        if item.get("isfolder") in (1, "1", True):
            return True
        if item.get("isdir") in (1, "1", True):
            return True
        if item.get("type") in (3, "3"):
            return True
        if not item.get("attachment") and item.get("filecount", 0) > 0:
            return True
        return False


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
    name = name.rstrip(". ")
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[:190] + ext
    return name or "unnamed"


def extract_course_id(url: str) -> str | None:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("courseId", "courseid", "course_id"):
        if key in qs and qs[key]:
            return qs[key][0]
    fragment = parsed.fragment or ""
    m = re.search(r"course[/=]([A-Za-z0-9]+)", fragment + parsed.path)
    if m:
        return m.group(1)
    return None


def pick_filename(item: dict[str, Any], detail: dict[str, Any]) -> str:
    attachments = detail.get("attachment") or item.get("attachment") or []
    if attachments:
        name = attachments[0].get("name")
        if name:
            return sanitize_filename(name)
    for key in ("title", "name", "filename"):
        if item.get(key):
            return sanitize_filename(str(item[key]))
    return sanitize_filename(f"file_{item.get('id', 'unknown')}")


def pick_download_url(detail: dict[str, Any], item: dict[str, Any]) -> str | None:
    for source in (detail, item):
        attachments = source.get("attachment") or []
        for att in attachments:
            url = att.get("url") or att.get("downloadurl") or att.get("download_url")
            if url:
                return url
    return None


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"未找到配置文件: {path}")
        print(f"请复制 config.example.json 为 {path.name} 并填写")
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_config(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def download_file(session: requests.Session, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成唯一文件名: {path}")


def resolve_token(
    config: dict[str, Any],
    config_path: Path | None = None,
    log: LogFn = print,
    save_token: bool = True,
) -> str:
    token = (config.get("token") or "").strip()
    if token:
        return token

    email = (config.get("email") or "").strip()
    password = (config.get("password") or "").strip()
    if email and password:
        log("正在使用账号密码登录...")
        token = KetangpaiClient.login(email, password)
        config["token"] = token
        if save_token and config_path:
            save_config(config_path, config)
            log(f"登录成功，token 已写入 {config_path}")
        else:
            log("登录成功")
        return token

    raise ValueError(
        "请填写 token，或填写 email + password\n"
        "token 获取: 浏览器登录课堂派 -> F12 -> Application -> Local Storage -> token"
    )


def resolve_course_id(config: dict[str, Any]) -> str:
    course_id = (config.get("course_id") or "").strip()
    course_url = (config.get("course_url") or "").strip()
    if course_url:
        parsed = extract_course_id(course_url)
        if parsed:
            return parsed
        raise ValueError(f"无法从 course_url 解析 courseId: {course_url}")
    return course_id


def run_list_courses(client: KetangpaiClient, log: LogFn = print) -> list[dict[str, Any]]:
    courses = client.list_courses()
    if not courses:
        log("未找到课程，请确认 token 有效且已加入课程。")
        return []
    log(f"共 {len(courses)} 门课程:\n")
    for i, c in enumerate(courses, 1):
        cid = c.get("id") or c.get("courseid")
        name = c.get("coursename") or c.get("name") or "未命名"
        teacher = c.get("teachername") or c.get("teacher") or ""
        extra = f" ({teacher})" if teacher else ""
        log(f"  {i}. {name}{extra}")
        log(f"     course_id: {cid}")
    return courses


def run_download(
    client: KetangpaiClient,
    config: dict[str, Any],
    log: LogFn = print,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    course_id = resolve_course_id(config)
    if not course_id:
        raise ValueError("请填写 course_id 或 course_url")

    output = config.get("output") or "downloads"
    dry_run = bool(config.get("dry_run"))
    skip_existing = config.get("skip_existing", True)

    log(f"课程 ID: {course_id}")
    log("正在获取资料列表...")

    materials = client.list_materials_flat(course_id)
    if not materials:
        log("该课程资料栏为空，或当前账号无权访问。")
        return {"ok": 0, "skip": 0, "fail": 0, "output_root": None}

    log(f"共找到 {len(materials)} 个文件\n")

    output_root = Path(output) / course_id
    ok, skip, fail = 0, 0, 0
    total = len(materials)

    for idx, item in enumerate(materials, 1):
        if on_progress:
            on_progress(idx, total)

        file_id = str(item.get("id") or "")
        if not file_id:
            log(f"[{idx}/{total}] 跳过: 无 id 的条目")
            fail += 1
            continue

        rel_dir = item.get("_relative_dir", "")
        title = item.get("title") or item.get("name") or file_id

        try:
            detail = client.get_file_detail(course_id, file_id)
        except RuntimeError as e:
            log(f"[{idx}/{total}] 获取详情失败: {title} -> {e}")
            fail += 1
            continue

        filename = pick_filename(item, detail)
        dest_dir = output_root / rel_dir if rel_dir else output_root
        dest = dest_dir / filename

        if skip_existing and dest.exists() and dest.stat().st_size > 0:
            log(f"[{idx}/{total}] 已存在，跳过: {dest}")
            skip += 1
            continue

        download_url = pick_download_url(detail, item)
        if not download_url:
            log(f"[{idx}/{total}] 无下载链接: {title}")
            fail += 1
            continue

        if dry_run:
            log(f"[{idx}/{total}] {dest}")
            ok += 1
            continue

        dest = unique_path(dest)
        try:
            download_file(client.session, download_url, dest)
            size_kb = dest.stat().st_size / 1024
            log(f"[{idx}/{total}] 已下载: {dest} ({size_kb:.1f} KB)")
            ok += 1
        except Exception as e:
            log(f"[{idx}/{total}] 下载失败: {title} -> {e}")
            fail += 1

        time.sleep(0.3)

    log("\n" + "=" * 40)
    action = "列出" if dry_run else "下载"
    log(f"{action}完成: 成功 {ok}, 跳过 {skip}, 失败 {fail}")
    if not dry_run:
        log(f"保存目录: {output_root.resolve()}")

    return {
        "ok": ok,
        "skip": skip,
        "fail": fail,
        "output_root": output_root.resolve() if not dry_run else None,
    }


def main() -> None:
    config_path = DEFAULT_CONFIG
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    config = load_config(config_path)
    try:
        token = resolve_token(config, config_path)
    except ValueError as e:
        print(e)
        sys.exit(1)

    client = KetangpaiClient(token)

    if config.get("list_courses"):
        run_list_courses(client)
    else:
        try:
            run_download(client, config)
        except (ValueError, RuntimeError) as e:
            print(e)
            sys.exit(1)


if __name__ == "__main__":
    main()
