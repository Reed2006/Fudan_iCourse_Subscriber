# iCourse Audio Transcriber

单一用途工具：登录复旦 iCourse，选择某门课程的某个 playback 课次，抽取该课次音频并转写成文本。

项目只保留这条链路：

1. 登录 iCourse / WebVPN
2. 列出指定课程可转写的课次
3. 抽取指定课次的音频
4. 输出本地音频文件和转写文本

已移除：

- GitHub Actions
- 前端页面
- 订阅/定时检查
- 数据库持久化
- 邮件发送
- PPT OCR
- LLM 摘要

## 环境要求

- Python 3.10+
- `ffmpeg`
- sherpa-onnx 所需 ASR 模型文件

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 环境变量

可使用 `.env.example` 作为参考。

必填：

- `StuId`
- `UISPsw`

常用可选项：

- `ICOURSE_ACCESS_MODE`
- `OUTPUT_DIR`
- `ASR_MODEL_DIR`
- `SILERO_VAD_PATH`
- `ASR_BACKEND`
- `ASR_NUM_THREADS`

## 模型文件

默认使用 SenseVoice。你需要自行准备：

- `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/`
- `silero_vad.onnx`

默认路径可通过以下环境变量覆盖：

- `ASR_MODEL_DIR`
- `SILERO_VAD_PATH`

## 用法

### 1. 先列出某门课可转写的课次

```bash
python main.py --course-id 34904 --list
```

输出示例：

```text
[1] 2026-03-04 | 第6-9节 | sub_id=563873
[2] 2026-03-11 | 第6-9节 | sub_id=568585
```

这里的编号就是后面 `--lecture-index` 要用的编号，按 playback 课次列表从 1 开始计数。

### 2. 抓取指定课次音频并转写

```bash
python main.py --course-id 34904 --lecture-index 1
```

也可以先列出再直接转写：

```bash
python main.py --course-id 34904 --list --lecture-index 1
```

## 输出

默认输出到 `output/course_<course_id>/`：

- `audio/*.wav`
- `transcripts/*.txt`

文本文件头部会保留基础元信息：

- `course_id`
- `sub_id`
- `date`
- `title`

## 常见问题

### 1. 登录时要求验证码

程序会尝试打开官方登录页，让你在浏览器中手动完成验证，然后回到终端继续。

### 2. 找不到 `ffmpeg`

先安装 `ffmpeg` 并确保它在 `PATH` 中可执行。

### 3. 转写很慢

主要取决于：

- 课程时长
- 本机 CPU
- `ASR_NUM_THREADS`
- ASR 模型类型

## 隐私

- 不要把 `.env`、`output/`、`data/`、模型文件或任何转写结果提交到仓库。
- 学号和密码只应放在本地环境变量中。
