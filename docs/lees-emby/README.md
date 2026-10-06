<div align="center">

<img src="app-icon.png" width="104" height="104" alt="Lee's Emby 应用图标" />

# Lee's Emby

### 你的片库，舒适地看。

为 Windows 打造的原生 Emby 媒体客户端。
浏览自己的片库，也能直接打开本地视频、音频与蓝光文件夹。

![Windows 11 22H2+](https://img.shields.io/badge/Windows-11_22H2%2B-0078D4)
![mpv](https://img.shields.io/badge/播放内核-mpv-8B7CF8)

[下载版本](https://github.com/lyq2010/lee-releases/releases?q=lees-emby&expanded=true) · [更新记录](https://github.com/lyq2010/lee-releases/releases?q=lees-emby&expanded=true) · [反馈问题](https://github.com/lyq2010/lee-releases/issues)

Copyright © 2026 lyq2010

</div>

---

## 从找到影片，到安心看完

- **浏览自己的片库** — 媒体库海报墙、搜索与条目详情，按电影、剧集和分季查看内容。
- **整理收藏与观看状态** — 支持多选，批量收藏或标记已看。
- **按习惯播放** — 切换音轨和字幕、选择分集、调整倍速，查看章节与播放信息。
- **直接播放本地内容** — 无需登录，打开视频、音频或蓝光文件夹，也支持拖入文件。
- **接着上次看** — 本地保存最近播放与续播点，历史最多保留 30 条。
- **管理媒体信息** — 拥有服务器管理员权限时，可编辑条目图片、刷新元数据。

## 播放体验，由你调节

| 功能 | 体验 |
| --- | --- |
| 原生播放器 | mpv 播放内核，窗口与全屏播放 |
| 音轨与字幕 | 按账户保存默认语言与字幕开关，支持拖入本地外挂字幕 |
| 连续观看 | 选择相邻分集，按设置自动跳过片头片尾；标记可用性取决于服务器数据 |
| Anime4K | 在播放面板选择画面处理模式，实际效果取决于片源与设备性能 |
| 弹幕 | 连接自行配置的兼容弹幕服务，支持匹配与绑定；未配置时不可用 |
| 外观 | 跟随系统、浅色或深色主题 |

## 开始使用

1. 在 [Releases](https://github.com/lyq2010/lee-releases/releases?q=lees-emby&expanded=true) 下载 `LeesEmby_*_x64-setup.exe`。
2. 运行安装程序；应用安装到当前用户目录，无需管理员权限。
3. 打开应用，填写自己的 Emby 服务器地址并登录；也可选择本地播放，无需服务器账户。
4. 浏览片库或打开文件，开始播放。

支持 **Windows 11 22H2 或更高版本、x64**。服务器播放需要已有的 Emby 服务与可用账户，本应用不提供媒体资源。

安装器将内置的 `CN=Lee` 证书写入当前用户证书库。卸载默认保留用户数据，勾选清理后才全部删除。

## 服务与数据由你掌握

Emby 访问令牌保存在 Windows 凭据管理器中，不写入数据库或诊断摘要。应用不做遥测上报；媒体访问、弹幕和评分查询按你配置的服务执行。

本地弹幕默认关闭。首次启用时会说明将向已配置的弹幕服务发送文件名、大小和时长。

后续版本通过应用内提示更新，安装前校验大小、SHA-256、Minisign 签名与版本。发行版同时提供签名、公钥证书和版本清单。

## 反馈与许可

通过 [Issues](https://github.com/lyq2010/lee-releases/issues) 提交应用版本、Windows 版本、片源类型与复现步骤。诊断信息请先脱敏，不要提交服务器令牌、私人地址或媒体文件。

许可证与第三方声明随安装包提供，发行版不附带源码包。

---

[返回 Lee Releases](../../README.md)
