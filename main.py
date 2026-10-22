"""AstrBot 音游助手的基础插件入口。"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class RhythmGameHelper(Star):
    """提供音游知识查询与聊天联动的扩展入口。"""

    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        logger.info("[rhythm_game_helper] 音游助手初始化完成（基础模板）")

    @filter.command("音游助手")
    async def rhythm_helper_status(self, event: AstrMessageEvent):
        """查看音游助手的安装状态和功能进度。"""
        yield event.plain_result(
            "音游助手已加载（v0.1.0）。当前为基础模板，音游知识查询、目录与收录功能尚未接入。"
        )

    async def terminate(self):
        logger.info("[rhythm_game_helper] 音游助手已停止")
