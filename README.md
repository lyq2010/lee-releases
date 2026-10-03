<div align="center">

# Lee Releases

**Lee 系列应用的公开下载与使用中心**

Windows 与 macOS 原生工具箱、邮件客户端、Emby 媒体客户端，以及 Android 音乐播放器。

</div>

## 产品介绍

| 产品 | 用途 |
| --- | --- |
| Lee's 系统工具箱 | Windows 原生系统维护工具 |
| Lee’s Toolbox Mac | Apple Silicon 原生业务工具箱，提供建筑板、冷库板等工具 |
| Lee's Mail | Windows 与 macOS 邮件客户端 |
| Lee's Emby | Windows 原生 Emby 媒体客户端 |
| [Lee’s Music](docs/lees-music/README.md) | 连接自建 Navidrome 音乐库的 Android 播放器 |

各产品使用独立的应用身份、安装包、数据目录和更新通道，可以并行安装。

## 下载与版本选择

| 版本 | 适用系统 | 下载入口 | 安装文件 |
|---|---|---|---|
| Lee's 系统工具箱 | Windows 11 22H2+ x64 | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20%E7%B3%BB%E7%BB%9F%E5%B7%A5%E5%85%B7%E7%AE%B1&expanded=true) | `lees-system-toolbox_*_x64-setup.exe` |
| Lee’s Toolbox Mac | Apple Silicon | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%E2%80%99s%20Toolbox%20Mac&expanded=true) | `Lee.s.Toolbox.Mac_*_macOS_arm64.dmg` |
| Lee's Mail for Windows | Windows 11 22H2+ x64 | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Windows&expanded=true) | `LeesMail_*_x64-setup.exe` |
| Lee's Mail for Mac | Apple Silicon、macOS 15+ | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Mac&expanded=true) | `LeesMail-*-arm64.dmg` |
| Lee's Emby | Windows 11 22H2+ x64 | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Emby&expanded=true) | `LeesEmby_*_x64-setup.exe` |

请通过对应产品的下载入口选择版本。仓库的 Latest 标记只代表一个产品，不作为其他产品的下载依据。Android 音乐播放器的下载和使用入口见下方说明。

## 安装与使用

### Windows

下载所选产品的 `setup.exe`，运行安装程序，完成后从开始菜单启动应用。

- **Lee's 系统工具箱**：适用于 Windows 11 22H2+ x64，提供本机系统维护能力。
- **Lee's Mail for Windows**：安装器请求管理员权限，将内置的 `CN=Lee` 证书导入本机“受信任人”，再安装 MSIX，无需手工导入证书。发行版同时提供原始 MSIX、公钥证书、SHA-256、版本清单和 GPL 对应源码归档，供离线校验与高级安装使用。
- **Lee's Emby**：安装到当前用户目录，无需管理员；安装器将内置的 `CN=Lee` 证书写入当前用户证书库。卸载默认保留用户数据，勾选清理后才全部删除。发行版同时提供 minisign 签名、公钥证书、版本清单和 GPL 对应源码归档。

Mail 与 Emby 安装后可通过应用内提示更新后续版本。

### macOS

1. 下载对应产品的 `.dmg`。
2. 打开 DMG，将应用拖入“应用程序”。
3. 如果系统阻止首次打开，请前往“系统设置 → 隐私与安全性”确认允许。

Lee's Mail for Mac 与 Lee’s Toolbox Mac 使用 ad-hoc 应用签名，不申请 Developer ID，也不执行 Apple 公证。首次安装需要按上面的步骤确认；后续应用内更新会校验 HTTPS 来源、文件大小、SHA-256 和对应签名。

### Android · Lee’s Music

[下载音乐安装包](https://github.com/lyq2010/lee-releases/releases?q=lees-music&expanded=true) · [功能介绍与使用说明](docs/lees-music/README.md)

1. 下载 `lees-music-*.apk`，安装到 Android 8.0 或更高版本的设备。
2. 添加自己的 Navidrome 服务器，填写地址与登录信息。
3. 浏览音乐库，开始播放；需要离线收听时可在应用内下载歌曲。

音乐版本沿用原签名，支持覆盖升级，无需清除数据。Lee’s Music 闭源发行，仅限个人、非商业用途，不提供项目源码；[使用许可](docs/lees-music/LICENSE)与[第三方声明](docs/lees-music/THIRD_PARTY_NOTICES.md)可在文档和应用内查看。

## 隐私与更新

- 邮件、媒体与工具数据由对应应用在本机处理。
- 各产品通过独立通道获取更新，并校验更新包来源、大小、哈希或签名。
- 私有配置、签名密钥和账户凭据不写入公开仓库。
- 各产品的使用许可和第三方声明以对应发行版及应用内说明为准。

## 问题反馈

通过 [Issues](https://github.com/lyq2010/lee-releases/issues) 报告问题或提出建议，请注明产品名称、应用版本、系统版本、复现步骤和必要日志。

不要在公开位置上传密码、令牌、私人服务器地址或包含个人隐私的原始数据。
