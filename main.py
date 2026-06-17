from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from src.ai.transcriber import Transcriber
from src.api.icourse import ICourseClient
from src.api.webvpn import (
    CaptchaRequiredError,
    create_access_session,
    get_manual_login_url,
)
from src.runtime import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取指定 iCourse 课程的指定课次音频并转写为文本。",
    )
    parser.add_argument(
        "--course-id",
        required=True,
        help="课程 ID。",
    )
    parser.add_argument(
        "--lecture-index",
        type=int,
        help="课次编号（从 playback 课次列表的 1 开始计数）。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅列出该课程可转写的 playback 课次编号。",
    )
    parser.add_argument(
        "--output-dir",
        default=config.OUTPUT_DIR,
        help="输出目录，默认使用 OUTPUT_DIR 或 output。",
    )
    parser.add_argument(
        "--ffmpeg-timeout",
        type=int,
        default=7200,
        help="抽取音频时 ffmpeg 的超时时间（秒）。",
    )
    return parser.parse_args()


def prompt_manual_login(exc: CaptchaRequiredError) -> bool:
    print(f"  登录失败：{exc}")
    if not sys.stdin.isatty():
        print("  当前不是交互终端，无法继续人工验证。请在浏览器完成验证后重试。")
        return False
    print("  UIS 需要人工验证码验证，正在打开官方登录页。")
    webbrowser.open(get_manual_login_url())
    input("  完成验证后按回车继续重试...")
    return True


def login_with_retry(max_attempts: int = 5):
    for attempt in range(max_attempts):
        try:
            session = create_access_session()
            mode = getattr(session, "access_mode", config.ICOURSE_ACCESS_MODE)
            print(f"[Login] {mode} ({attempt + 1}/{max_attempts})")
            session.login()
            session.authenticate_icourse()
            return session
        except CaptchaRequiredError as exc:
            if attempt < max_attempts - 1 and prompt_manual_login(exc):
                continue
            raise
        except Exception as exc:
            if attempt == max_attempts - 1:
                raise
            print(f"  失败：{type(exc).__name__}: {exc}，5 秒后重试。")
            time.sleep(5)
    raise RuntimeError("unreachable")


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        return
    raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并确保其在 PATH 中。")


def filename_safe(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned or fallback


def list_playback_lectures(client: ICourseClient, course_id: str) -> tuple[str, str, list[dict]]:
    detail = client.get_course_detail(course_id)
    lectures = sorted(
        [lecture for lecture in detail["lectures"] if lecture.get("has_playback")],
        key=lambda lecture: (
            lecture.get("date", ""),
            str(lecture.get("sub_id", "")),
        ),
    )

    deduped: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for lecture in lectures:
        key = (
            lecture.get("date", ""),
            lecture.get("sub_title", "") or str(lecture.get("sub_id", "")),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(lecture)

    return detail["title"], detail["teacher"], deduped


def print_lecture_list(course_title: str, teacher: str, lectures: list[dict]) -> None:
    print(f"\n课程：{course_title}")
    print(f"教师：{teacher}")
    print(f"可转写 playback 课次：{len(lectures)}\n")
    for index, lecture in enumerate(lectures, start=1):
        date = lecture.get("date", "")
        sub_title = lecture.get("sub_title") or str(lecture.get("sub_id"))
        sub_id = lecture.get("sub_id")
        print(f"[{index}] {date} | {sub_title} | sub_id={sub_id}")


def select_lecture(lectures: list[dict], lecture_index: int) -> dict:
    if lecture_index < 1 or lecture_index > len(lectures):
        raise ValueError(
            f"--lecture-index 超出范围：{lecture_index}，可选范围为 1 到 {len(lectures)}。"
        )
    return lectures[lecture_index - 1]


def extract_audio(
    client: ICourseClient,
    course_id: str,
    lecture: dict,
    output_path: Path,
    timeout: int,
) -> Path:
    video_url = client.get_video_url(course_id, str(lecture["sub_id"]))
    if not video_url:
        raise RuntimeError("未能获取该课次的可播放视频 URL。")

    stream_url, headers = client.get_stream_params(video_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-headers",
        headers,
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
        "-i",
        stream_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace")[-800:]
        raise RuntimeError(f"ffmpeg 抽取音频失败：\n{stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"ffmpeg 在 {timeout}s 内未完成音频抽取。") from exc

    return output_path


def write_transcript(transcript_path: Path, lecture: dict, transcript: str) -> Path:
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"course_id: {lecture['course_id']}",
        f"sub_id: {lecture['sub_id']}",
        f"date: {lecture.get('date', '')}",
        f"title: {lecture.get('sub_title', '')}",
        "",
    ]
    transcript_path.write_text(
        "\n".join(header) + (transcript or "").strip() + "\n",
        encoding="utf-8",
    )
    return transcript_path


def main() -> int:
    args = parse_args()
    ensure_ffmpeg()

    vpn = login_with_retry()
    client = ICourseClient(vpn)

    course_title, teacher, lectures = list_playback_lectures(client, args.course_id)
    if not lectures:
        print("该课程没有可用的 playback 课次。")
        return 1

    if args.list:
        print_lecture_list(course_title, teacher, lectures)
        if args.lecture_index is None:
            return 0

    if args.lecture_index is None:
        print("请提供 --lecture-index，或先用 --list 查看课次编号。", file=sys.stderr)
        return 2

    lecture = select_lecture(lectures, args.lecture_index)
    lecture["course_id"] = args.course_id

    sub_id = str(lecture["sub_id"])
    sub_title = lecture.get("sub_title") or sub_id
    date = lecture.get("date", "")
    slug = filename_safe(
        f"{args.lecture_index:02d}_{date}_{sub_id}_{sub_title}",
        f"{args.course_id}_{sub_id}",
    )

    base_dir = Path(args.output_dir) / f"course_{args.course_id}"
    audio_path = base_dir / "audio" / f"{slug}.wav"
    transcript_path = base_dir / "transcripts" / f"{slug}.txt"

    print(f"\n课程：{course_title}")
    print(f"教师：{teacher}")
    print(f"选中课次：[{args.lecture_index}] {date} | {sub_title} | sub_id={sub_id}")
    print(f"输出目录：{base_dir}")

    print("\n[1/2] 抽取音频...")
    extract_audio(client, args.course_id, lecture, audio_path, args.ffmpeg_timeout)
    print(f"音频已保存：{audio_path}")

    print("\n[2/2] 转写文本...")
    transcriber = Transcriber()
    transcript, _segments = transcriber.transcribe_file(str(audio_path))
    write_transcript(transcript_path, lecture, transcript)
    print(f"转写已保存：{transcript_path}")
    print(f"转写长度：{len(transcript)} 字符")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
