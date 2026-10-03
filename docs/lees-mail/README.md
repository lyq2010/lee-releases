<div align="center">

<img src="app-icon.png" width="104" height="104" alt="Lee's Mail 应用图标" />

# Lee's Mail

### 邮件有序，隐私由你掌握。

本地优先的桌面邮件客户端。
在 Windows 与 Mac 上收发邮件，让邮箱回到自己的工作节奏。

![Windows 11 22H2+](https://img.shields.io/badge/Windows-11_22H2%2B-0078D4)
![macOS 15+](https://img.shields.io/badge/macOS-15%2B-333333?logo=apple&logoColor=white)
![GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue)

[下载 Windows 版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Windows&expanded=true) · [下载 Mac 版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Mac&expanded=true) · [反馈问题](https://github.com/lyq2010/lee-releases/issues)

</div>

---

## 让邮件回到日常工作流

- **连接自己的邮箱** — Windows 版支持 Microsoft Graph、Gmail API 与通用 IMAP/SMTP；Mac 版提供 OAuth 与 IMAP/SMTP 配置。
- **清楚地浏览与回复** — 在邮件列表和阅读区查看内容，按会话处理往来邮件。
- **远程内容由你决定** — 默认阻断邮件远程资源，减少外部图片和跟踪内容的自动加载。
- **无需额外厂商账号** — 不引入广告、订阅、计费或遥测。

Windows 与 Mac 版独立维护，使用各自的数据目录和更新通道；以下 Windows 功能不代表 Mac 版具备相同能力。

## Windows 版的常用能力

| 功能 | 体验 |
| --- | --- |
| 多种邮箱接入 | Microsoft Graph、Gmail API、通用 IMAP/SMTP；支持的账户通过 IDLE 信号触发同步 |
| 搜索邮件 | 中文全文搜索与确定性自然语言搜索 |
| 通讯录 | 本地联系人，以及可双向编辑的 Outlook 云通讯录 |
| 附件预览 | 预览 Office 文档、CSV、邮件、音视频和压缩包目录；压缩包预览不解压 |
| 邮件翻译 | 主动点击后，通过配置的百度翻译或私有 Cloudflare 服务翻译当前可见正文 |
| 发件追踪 | 默认关闭，可逐封开启；依赖用户配置的追踪服务 |
| 本地保护 | 数据库、邮件、附件、头像、搜索索引与账号秘密使用受保护存储 |

Mac 版提供本地邮件同步与三栏邮件工作流。邮箱凭据交由本机同步内核处理，不发送给 Lee's Mail 或原上游服务；默认关闭依赖外部云服务的插件。

## 选择你的版本

| 平台 | 系统要求 | 安装包 | 更新记录 |
| --- | --- | --- | --- |
| Windows | Windows 11 22H2+、x64 | `LeesMail_*_x64-setup.exe` | [Windows 发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Windows&expanded=true) |
| Mac | macOS 15+、Apple Silicon | `LeesMail-*-arm64.dmg` | [Mac 发行版](https://github.com/lyq2010/lee-releases/releases?q=Lee%27s%20Mail%20for%20Mac&expanded=true) |

### Windows

1. 下载并运行 `LeesMail_*_x64-setup.exe`。
2. 按安装器提示确认管理员权限；安装器将内置的 `CN=Lee` 证书导入本机「受信任人」，再安装 MSIX，无需手动导入证书。
3. 从开始菜单打开应用，添加邮箱账户；自定义邮箱按服务商要求填写 IMAP/SMTP 参数。

发行版同时提供原始 MSIX、公钥证书、版本清单和对应源码归档。后续版本通过应用内更新提示获取。

### Mac

1. 下载并打开 `LeesMail-*-arm64.dmg`，将应用拖入「应用程序」。
2. 首次打开若被系统阻止，前往「系统设置 → 隐私与安全性」确认允许。
3. 打开应用，添加邮箱账户，完成登录或 IMAP/SMTP 配置。

Mac 版采用 ad-hoc 签名，不使用 Developer ID 或 Apple 公证。后台更新检查只提示；主动检查发现新版后，会下载、校验大小、SHA-256 与 Minisign 签名，替换应用并重新打开。

## 连接邮箱，保持知情

收发与同步需要连接你的邮件服务商。启用翻译、发件追踪、第三方头像等可选功能时，会按对应配置访问外部服务。

Windows 翻译仅发送当前邮件的可见正文，不发送附件或原始 HTML；发件追踪默认关闭。反馈问题时，请勿上传密码、OAuth 令牌、原始邮件或未脱敏的附件。

## 反馈与许可

通过 [Issues](https://github.com/lyq2010/lee-releases/issues) 提交平台、应用版本、邮箱服务商和复现步骤。

两个平台均遵循 **GPL-3.0**，各自保留上游版权与第三方声明。对应版本的源码归档与安装包在同一发行版提供，具体许可和归属以归档及应用内说明为准。

---

[返回 Lee Releases](../../README.md)
