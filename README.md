# 建筑板部工具箱

建筑板 / 冷库板项目概览表桌面工具，可将装箱明细、成品物流、切锯表、下单详情、转账款明细和开票明细整理为项目概览表，并生成汇总、发货和合同收款数据。业务文件只在本机处理。

## 下载与安装

| 系统 | 下载入口 | 安装文件 |
|---|---|---|
| Windows x64 | [最新稳定版](https://github.com/lyq2010/building-panel-dept-toolkit-releases/releases/latest) | `packing-list-toolkit_*_x64-setup.exe` |
| Windows 11 x64 原生版 | [Windows Native v1.0.4](https://github.com/lyq2010/building-panel-dept-toolkit-releases/releases/tag/windows-native-v1.0.4) | `packing-list-toolkit_*_windows-native-x64-setup.exe` |
| macOS Apple Silicon | [最新稳定版](https://github.com/lyq2010/building-panel-dept-toolkit-releases/releases/latest) | `packing-list-toolkit_*_arm64.dmg` |
| macOS Apple Silicon 原生版 | [原生版下载](https://github.com/lyq2010/building-panel-dept-toolkit-releases/releases/tag/native-v3.0.4) | `packing-list-toolkit_*_macos-native-arm64.dmg` |

Windows 运行安装程序完成安装。macOS 打开 DMG 后将应用拖入「应用程序」；如系统阻止首次打开，请在「系统设置 → 隐私与安全性」中允许。

## 版本怎么选

- Windows 通用版使用 Tauri，沿用稳定版版本号与 `latest.json` 更新通道。
- Windows Native 使用 WinUI 3，仅支持 Windows 11 22H2 及以上；开始菜单名称为「建筑板部原生工具箱 for Win」。
- macOS 通用版使用 Tauri；macOS 原生版使用 SwiftUI，仅支持 Apple Silicon。
- 通用版与原生版可以并行安装；它们的安装目录、数据、证书、卸载项和更新清单互不共用。

## 快速开始

1. 选择「建筑板 · 概览表」或「冷库板 · 概览表」。
2. 将业务表格拖入对应文件槽，也可以点击文件槽选择文件。
3. 新建概览表时填写项目名和保存目录；更新时放入原概览表。
4. 按需勾选「汇总」「每日发货」「合同收款」和「先备份」。
5. 点击「执行」或「开始处理」，也可以按 `Ctrl/⌘ + Enter`。
6. 完成后点击「打开文件」或「打开目录」查看结果。

底部回执区显示成功结果或失败原因，事件区可查看详细过程。

## 文件怎么选

| 业务入口 | 新建时必填 | 更新时可选 |
|---|---|---|
| 建筑板 | 装箱明细、项目名、保存目录 | 原概览表、装箱明细、成品物流、切锯表、下单详情、转账款明细、开票明细 |
| 冷库板 | 下单详情、项目名、保存目录 | 原概览表、下单详情、成品物流、切锯表 |

放入哪类可选表，就刷新对应的数据；未提供的可选数据不会被强制要求。更新重要文件前建议开启「先备份」。

## 从系统拉数

点击「从系统拉数」，可根据下单详情或概览表中的项目与库号获取装箱明细、切锯表和成品物流。该功能需要连接公司生产管理系统，一次只能处理一个项目；车间、切锯范围和物流时间可在高级设置中调整。

## 使用提示

- 支持 `.xlsx` / `.xlsm`，下单详情也支持 UTF-8 或 GBK 编码的 `.csv`。
- 检测到 Microsoft Excel 时会执行原生重算；没有 Excel 也能生成文件，公式将在下次用 Excel 打开时重算。
- 输出文件被 Excel 占用时，请关闭文件后重试。
- 应用只保存最近任务所需的本地元信息，不上传或缓存业务文件正文。

公司内部使用，保留所有权利。
