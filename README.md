<div align="center">

# Lee Releases

**Lee 系列原生桌面工具与 Lee's Mail 的公开下载、安装与使用中心**

这里集中发布原生工具箱和个人邮箱客户端。每个产品使用独立标签、
安装包名称与更新清单。

</div>

## 产品介绍

本仓库提供 Lee 系列 Windows/macOS 原生工具箱，以及 Lee's Mail 邮件客户端的公开安装包与更新清单。

主要能力：

- 原生工具箱提供文本处理、计算器、批量重命名和快捷启动器等本地工具；
- Lee's Mail 提供 Windows 与 macOS 原生邮件客户端；
- 各产品使用独立更新通道，并校验更新包来源、哈希和签名。

## 下载与版本选择

| 版本 | 适用系统 | 下载入口 | 安装文件 |
|---|---|---|---|
| Lee's Toolbox Windows | Windows 11 22H2+ x64 | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20%E5%B7%A5%E5%85%B7%E7%AE%B1%20Windows&expanded=true) | `lees-toolbox-windows_*_x64-setup.exe` |
| Lee's 系统工具箱 | Windows 11 22H2+ x64 | [公开发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20%E7%B3%BB%E7%BB%9F%E5%B7%A5%E5%85%B7%E7%AE%B1&expanded=true) | `lees-system-toolbox_*_x64-setup.exe` |
| Lee’s Toolbox Mac | Apple Silicon | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%E2%80%99s%20Toolbox%20Mac&expanded=true) | `Lee’s Toolbox Mac_*_macOS_arm64.dmg` |
| Lee's Mail | Windows 11 22H2+ x64 | [最新稳定版](https://github.com/lyq2010/lee-releases/releases/latest) | `LeesMail_*_x64-setup.exe` |
| Lee’s Mail Mac | Apple Silicon、macOS 15+ | [最新稳定版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Mac&expanded=true) | `Lees-Mail-*-arm64.dmg` |

### 怎么选择

- 使用 Windows 11，希望获得原生界面、较快启动和较低后台占用，可选择 Lee's Toolbox Windows。
- 使用 Apple Silicon Mac，希望使用 SwiftUI 原生界面和原生业务引擎，可选择 Lee’s Toolbox Mac。
- 使用 Apple Silicon Mac，希望使用独立的原生邮件客户端，可选择 Lee’s Mail Mac。
- 各产品使用独立的应用身份、数据目录和更新通道，可以并行安装。

## 安装

### Windows

1. 下载对应的 `setup.exe`。
2. 双击运行安装程序。
3. 安装完成后，从开始菜单启动应用。

Lee's Mail 通过本仓库的 Release 安装和更新。下载 `LeesMail_*_x64-setup.exe` 后直接运行，
安装器会请求管理员权限，把内置的 `CN=Lee` 证书导入本机“受信任人”，再安装内置 MSIX，
无需手工导入证书。安装后由应用内更新提示后续版本。
Release 同时附带原始 MSIX、公钥证书、SHA-256、版本清单和 GPL 对应源码归档，
供离线校验与高级安装使用。

### macOS

1. 下载对应的 `.dmg`。
2. 打开 DMG，将应用拖入「应用程序」。
3. 如果系统阻止首次打开，请前往「系统设置 → 隐私与安全性」确认允许。

Lee’s Mail Mac 与 Lee’s Toolbox Mac 一样使用 ad-hoc 应用签名，不申请 Developer ID，
也不执行 Apple 公证。首次安装需要按上一步在系统设置中确认；后续应用内更新会同时
校验 HTTPS 来源、文件大小、SHA-256 和内置公钥对应的 Minisign 签名。

## 隐私与数据

- 邮件与工具数据由对应应用在本机处理；
- 更新包会校验来源、大小、哈希和签名；
- 私有配置与密钥不写入公开仓库。

## 获取帮助

遇到问题时，请提供应用版本、平台、失败步骤和必要日志；不要在公开位置上传包含隐私或账户信息的原始数据。

公司内部使用，保留所有权利。
