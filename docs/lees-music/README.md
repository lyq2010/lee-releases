<div align="center">

<img src="app-icon.png" width="104" height="104" alt="应用图标" />

# Lee’s Music

### 你的音乐，随身聆听。

为自建音乐库打造的 Android 播放器。
连接 Navidrome、Emby、Plex，或播放设备上的本地音乐。

![Android 8.0+](https://img.shields.io/badge/Android-8.0%2B-3DDC84?logo=android&logoColor=white)
![专有许可](https://img.shields.io/badge/License-Proprietary-blue)
![Status](https://img.shields.io/badge/状态-正式版-8B7CF8)

[下载版本](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Music) · [更新记录](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Music) · [反馈问题](https://github.com/lyq2010/lee-releases/issues)

</div>

---

## 好好听歌，也好好管理收藏

- **浏览你的音乐库** — 歌曲、专辑、艺术家、收藏与个人歌单，集中呈现。
- **发现下一首** — 每日推荐、最近添加、最近播放与随机推荐。
- **快速找到想听的** — 按歌曲、专辑和艺术家搜索。
- **沉浸式歌词** — 跟随播放进度高亮，支持手动浏览与点击跳转；歌词内容取决于服务器提供的数据。
- **安排接下来的音乐** — 下一首播放、加入队列、调整顺序，以及随机与循环播放。
- **随时离线收听** — 下载原音质歌曲，查看下载状态与存储占用。

## 按你的习惯播放

| 功能 | 体验 |
| --- | --- |
| 后台播放 | 通知栏控制、耳机断开暂停、通知栏歌词 |
| 桌面小组件 | 1×1、2×2、3×2、4×1 四种规格，快捷控制播放 |
| 接着听 | 恢复上次的歌曲、队列与进度，启动保持暂停 |
| 播放手势 | 播放页下滑收起，底部播放条左右切歌 |
| 聆听调节 | 均衡器预设、歌曲间淡入淡出、播放速度、睡眠定时 |
| 外观个性化 | 跟随系统、浅色或深色模式，多种主题配色 |
| 网络与存储 | 在线音质选择、计费网络控制、播放缓存容量与清理 |
| 多音乐源 | 保存并切换 Navidrome、Emby、Plex 和本地音乐 |
| 局域网发现 | 自动发现服务器，点击填入连接地址 |

## 开始使用

1. 在 [Releases](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Music) 下载 APK，安装到 Android 8.0 或更高版本的设备。
2. 添加音乐源：选择自动发现的服务器后只需填写登录信息；保存过的唯一账号可直接连接。也可手动添加 Navidrome/Emby 地址和账号，或 Plex 地址与 `X-Plex-Token`；本地音乐授予音乐读取权限。
3. 打开音乐库，选择喜欢的歌曲。

支持 **Navidrome、Emby、Plex、本地音乐**。Emby 登录后保存加密令牌；Plex 使用服务器访问令牌。原音质使用直接音频流，音频格式需设备支持；选择压缩音质时通过 Emby/Plex HLS 转码，支持拖动进度，服务器需允许转码。歌词读取服务器提供的歌词流，本地支持 MP3 ID3/FLAC 内嵌歌词和 LRC/TXT 导入。公开歌单链接按服务器能力提供，目前仅 Navidrome 支持该入口。

添加音乐源页面会自动扫描已获授权的局域网，发现结果即时出现，单一发现协议失败不影响其他结果；支持 Emby UDP、Plex GDM、HTTP 服务广播，以及当前 IPv4 网段的常用端口探测（4533、8096、32400，最多 254 个邻近地址）。NAT 模拟器、跨网段、隔离网络或未广播的自定义端口可手动添加。Android 17 及以上需要允许局域网/附近设备权限。本地曲库读取系统媒体库，可浏览、搜索、收藏、管理歌单，并使用现有后台播放器；新增或移除音乐后可刷新列表。最近播放和常听专辑按实际播放记录排序。转码播放需要实时访问服务器，离线收听请下载原音质歌曲。

## 音乐属于你

连接你自己的服务器，使用你自己的音乐收藏。无广告，不内置使用统计或第三方崩溃上报；服务器登录信息保存在设备本地。

## 反馈与参与

欢迎通过 [Issues](https://github.com/lyq2010/lee-releases/issues) 报告问题或提出建议。反馈时请附上应用版本、设备型号、Android 版本及复现步骤，避免提交密码、令牌或私人服务器地址。

## 软件许可

Copyright © 2026 lyq2010。Lee’s Music 闭源发行，仅限个人、非商业用途，见 [使用许可](LICENSE)。第三方组件仍遵循各自许可证，见 [第三方声明](THIRD_PARTY_NOTICES.md)。
