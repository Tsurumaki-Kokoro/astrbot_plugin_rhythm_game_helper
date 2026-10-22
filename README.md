# AstrBot 音游助手

音游知识查询与聊天联动插件，当前版本为 v0.1.0 基础模板。

## 当前功能

- 插件初始化与卸载日志。
- 状态指令：`/音游助手`（实际前缀以 AstrBot 当前会话配置为准）。
- 尚未接入音游知识库、AI 查询工具和知识收录。

## 开发方向

- 移植 rhythm-kb JSON 资料与关键词检索逻辑。
- 提供音游知识查询、目录与收录工具。
- 兼容 Chat Plus 发起的聊天请求，保持现有人格稳定。

## 环境

- AstrBot >= 4.29.1。
- 当前没有额外的第三方依赖，使用 AstrBot 自带 Python 环境。
- 修改代码后，在 AstrBot 插件管理中重载本插件。

## 项目

https://github.com/Tsurumaki-Kokoro/astrbot_plugin_rhythm_game_helper

许可证见 LICENSE。
