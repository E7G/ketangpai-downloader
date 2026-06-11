# 课堂派资料批量下载

批量下载 [课堂派](https://www.ketangpai.com/) 课程资料栏中的文件，支持命令行与图形界面。

## 功能

- 按课程 ID 或资料页 URL 下载全部资料
- 递归遍历文件夹，保持目录结构
- 跳过已下载文件、仅预览模式
- GUI：刷新课程列表、选择课程、进度条与日志

## 环境要求

- Python 3.10+
- 依赖见 `requirements.txt`

## 安装

```bash
git clone <your-repo-url>
cd ketangpai-downloader
pip install -r requirements.txt
```

## 配置

复制示例配置并填写自己的信息：

```bash
cp config.example.json config.json
```

| 字段 | 说明 |
|------|------|
| `token` | 浏览器登录后，F12 → Application → Local Storage → `token` |
| `email` / `password` | 可选；未填 token 时用账号密码自动登录并写回 token |
| `course_id` | 目标课程 ID |
| `course_url` | 或填资料页 URL，自动解析 courseId |
| `output` | 下载保存目录，默认 `downloads` |
| `list_courses` | 设为 `true` 可列出所有课程及 ID |
| `dry_run` | `true` 时只列出文件，不实际下载 |
| `skip_existing` | 跳过本地已存在的文件 |

> **注意**：`config.json` 含登录凭证，已在 `.gitignore` 中忽略，请勿提交到公开仓库。

## 使用

### 命令行

```bash
# 查看课程列表（先在 config.json 中设置 "list_courses": true）
python ketangpai_batch_download.py

# 正常下载
python ketangpai_batch_download.py
```

### 图形界面

```bash
python ketangpai_gui.py
```

## 免责声明

本工具仅供个人学习与研究使用。请遵守课堂派服务条款与课程版权规定，不得用于未授权传播或商业用途。使用本工具产生的后果由使用者自行承担。

## License

MIT
