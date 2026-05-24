"""Pydantic 数据模型"""

from __future__ import annotations
import uuid
from pydantic import BaseModel, Field


class Attributes(BaseModel):
    # 硬实力 (15)
    射门: int = 50; 跑位: int = 50; 定位球: int = 50
    传球: int = 50; 盘带: int = 50; 技术: int = 50; 才华: int = 50
    盯人: int = 50; 抢断: int = 50; 站位: int = 50
    强壮: int = 50; 速度: int = 50; 跳跃: int = 50; 体力: int = 50; 头球: int = 50
    # 软实力 (13)
    意志力: int = 50; 勇敢: int = 50; 抗压能力: int = 50
    稳定性: int = 50; 情绪控制: int = 50
    职业态度: int = 50; 团队精神: int = 50; 人际处理: int = 50
    公众口碑: int = 50; 声望: int = 50
    伤病抗性: int = 50; 多面性: int = 50; 双足均衡: int = 50


class Player(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    age: int = 20
    height: int = 180
    weight: int = 75
    nationality: str = ""
    team_tier: str = ""      # 世界等级 豪门/劲旅/中游/下游/弱旅 → 决定初始属性
    league_level: str = ""   # 联赛地位 争冠/上游/中游/下游/保级 → 决定排名积分
    team_name: str = ""
    position: str = ""
    attrs: Attributes = Field(default_factory=Attributes)
    temp_status: str = "无"
    injury_rounds: int = 0
    suspended_rounds: int = 0
    locker_status: str = "普通成员"  # 更衣室地位
    seasons_left: int = 3       # 合同剩余赛季数
    weekly_wage: float = 5.0    # 周薪（万欧元）
    release_clause: float = 0.0 # 解约金（万欧元，0=无）
    trait_count: int = 0        # 创建时选的特点数（成就用）
    neg_trait_count: int = 0    # 负面特点数
    traits: list[str] = []      # 所有特点名
    neg_success: int = 0        # 谈判成功次数
    last_transfer_season: int = 0  # 上次转会的赛季（冷却用）


class SeasonState(BaseModel):
    season: int = 1
    round_idx: int = 0
    round_name: str = "上半前期"
    team_rank: int = 10
    team_points: int = 30
    team_games: int = 0
    atmosphere: str = "平淡"  # 内讧/涣散/平淡/融洽/鼎盛


class DialogueEntry(BaseModel):
    role: str
    content: str
    stage: str = ""


# ---------- API 请求 ----------
class CreatePlayerReq(BaseModel):
    name: str
    team_name: str
    nationality: str
    position: str
    age: int
    height: int
    weight: int
    traits: list[str] = []  # 球员特点（0-2个，对应 TRAITS 的 key）


class AdjustAttrReq(BaseModel):
    adjustments: dict[str, int]


class FreeTalkReq(BaseModel):
    content: str
    target: str = ""  # 对话对象（主教练/队友/经纪人/家人/记者/俱乐部高层/球迷）


class EventChoiceReq(BaseModel):
    option_id: str
    custom_text: str = ""


class SeasonRecord(BaseModel):
    season: int
    age: int
    club: str
    league_position: int
    appearances: int
    goals: int
    assists: int
    honors: list[str] = []
    awards: list[str] = []       # 个人奖项（金球/最佳阵容等）
    highlights: list[str] = []   # 本赛季大事
    hard_sum: int = 0
    soft_sum: int = 0
