<div align="center">

# Lee Releases

**Lee 系列原生桌面工具、Lee's Mail、Lee's Emby 与 Lee’s Music 的公开下载、安装与使用中心**

这里集中发布原生工具箱、个人邮箱客户端、Emby 客户端和 Android 音乐播放器。每个产品使用独立标签、
安装包名称与更新清单。

</div>

## 产品介绍

本仓库提供 Lee 系列 Windows/macOS 原生工具箱、Lee's Mail 邮件客户端，以及 Lee's Emby 媒体客户端与 Lee’s Music Android 音乐播放器的公开安装包与更新清单。

主要能力：

- Lee's 系统工具箱提供 Windows 原生系统维护工具；
- Lee’s Toolbox Mac 提供 Apple Silicon 原生业务工具箱；
- Lee's Mail 提供 Windows 与 macOS 邮件客户端；
- Lee's Emby 提供 Windows 原生 Emby 媒体客户端；
- [Lee’s Music](docs/lees-music/README.md) 提供连接自建 Navidrome 音乐库的 Android 播放器；
- 各产品使用独立更新通道，并校验更新包来源、哈希和签名。

## 下载与版本选择

| 版本 | 适用系统 | 下载入口 | 安装文件 |
|---|---|---|---|
| Lee's 系统工具箱 | Windows 11 22H2+ x64 | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20%E7%B3%BB%E7%BB%9F%E5%B7%A5%E5%85%B7%E7%AE%B1&expanded=true) | `lees-system-toolbox_*_x64-setup.exe` |
| Lee’s Toolbox Mac | Apple Silicon | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%E2%80%99s%20Toolbox%20Mac&expanded=true) | `Lee.s.Toolbox.Mac_*_macOS_arm64.dmg` |
| Lee's Mail for Windows | Windows 11 22H2+ x64 | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Windows&expanded=true) | `LeesMail_*_x64-setup.exe` |
| Lee's Mail for Mac | Apple Silicon、macOS 15+ | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Mac&expanded=true) | `LeesMail-*-arm64.dmg` |
| Lee's Emby | Windows 11 22H2+ x64 | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Emby&expanded=true) | `LeesEmby_*_x64-setup.exe` |
| [Lee’s Music](docs/lees-music/README.md) | Android 8.0+ | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=lees-music&expanded=true) | `lees-music-*.apk` |

### 怎么选择

- 使用 Windows 11，需要原生系统维护能力，可选择 Lee's 系统工具箱。
- 使用 Apple Silicon Mac，需要建筑板、冷库板等原生业务工具，可选择 Lee’s Toolbox Mac。
- 需要邮件客户端时，按当前系统选择 Lee's Mail for Windows 或 Lee's Mail for Mac。
- 需要 Emby 媒体客户端时，选择 Lee's Emby。GitHub 仓库的 Latest 标记固定给 Lee's Mail for Windows，Emby 请按上表产品入口下载。
- 需要在 Android 上收听自建 Navidrome 音乐库时，选择 [Lee’s Music](docs/lees-music/README.md)。
- 各产品使用独立的应用身份、数据目录和更新通道，可以并行安装。

## 安装

### Windows

1. 下载对应的 `setup.exe`。
2. 双击运行安装程序。
3. 安装完成后，从开始菜单启动应用。

Lee's Emby 通过本仓库的 Release 安装和更新。下载 `LeesEmby_*_x64-setup.exe` 后直接运行，
安装到当前用户目录，无需管理员。安装器把内置的 `CN=Lee` 证书写入当前用户证书库；
卸载默认保留用户数据，勾选清理后才全量删除。安装后由应用内更新提示后续版本。
Release 同时附带 minisign 签名、公钥证书、版本清单和 GPL 对应源码归档。

Lee's Mail for Windows 通过本仓库的 Release 安装和更新。下载 `LeesMail_*_x64-setup.exe` 后直接运行，
安装器会请求管理员权限，把内置的 `CN=Lee` 证书导入本机“受信任人”，再安装内置 MSIX，
无需手工导入证书。安装后由应用内更新提示后续版本。
Release 同时附带原始 MSIX、公钥证书、SHA-256、版本清单和 GPL 对应源码归档，
供离线校验与高级安装使用。

### macOS

1. 下载对应的 `.dmg`。
2. 打开 DMG，将应用拖入“应用程序”。
3. 如果系统阻止首次打开，请前往“系统设置 → 隐私与安全性”确认允许。

Lee's Mail for Mac 与 Lee’s Toolbox Mac 一样使用 ad-hoc 应用签名，不申请 Developer ID，
也不执行 Apple 公证。首次安装需要按上一步在系统设置中确认；后续应用内更新会同时
校验 HTTPS 来源、文件大小、SHA-256 和对应签名。

### Android

Lee’s Music 的功能介绍与使用说明见 [音乐项目 README](docs/lees-music/README.md)。下载 `lees-music-*.apk` 后安装，连接自己的 Navidrome 服务器即可使用。音乐版本沿用原签名，支持覆盖升级；闭源发行，仅限个人、非商业用途，不提供项目源码。使用许可及第三方声明见音乐文档和应用内“软件许可”。

## 隐私与数据

- 邮件、媒体与工具数据由对应应用在本机处理；
- 更新包会校验来源、大小、哈希和签名；
- 私有配置与密钥不写入公开仓库。

## 获取帮助

遇到问题时，请提供应用版本、平台、失败步骤和必要日志；不要在公开位置上传包含隐私或账户信息的原始数据。

公司内部使用，保留所有权利。
