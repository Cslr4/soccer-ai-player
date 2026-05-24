"""游戏状态管理 —— 内存存储"""

from __future__ import annotations
import random
from config import TEAM_TIERS, POSITIONS, HARD_ATTRS, SOFT_ATTRS, ALL_ATTRS, INVERSE_ATTRS, ROUNDS, TRAITS

# 球队信息缓存：team_name → {tier, league_level}（AI判断后缓存，同队永远一致）
_team_cache: dict[str, dict] = {}

def resolve_team_info(team_name: str) -> dict | None:
    """查缓存，未命中返回None"""
    if team_name in _team_cache:
        return dict(_team_cache[team_name])
    return None

def cache_team_info(team_name: str, tier: str, league_level: str):
    """缓存AI判断的球队信息"""
    _team_cache[team_name] = {"tier": tier, "league_level": league_level}
from models import Player, Attributes, SeasonState, DialogueEntry, SeasonRecord

# 内存存储
players: dict[str, Player] = {}
seasons: dict[str, SeasonState] = {}
dialogues: dict[str, list] = {}           # player_id -> [DialogueEntry]
event_queue: dict[str, list[dict]] = {}   # player_id -> 本轮剩余事件
completed_events: dict[str, list[str]] = {}  # player_id -> 已完成事件摘要
pending_effects: dict[str, dict[str, int]] = {}  # 累积属性变化
pending_talk_effects: dict[str, dict[str, int]] = {}  # 对话累积效果（结算时清算）
used_categories: dict[str, list[str]] = {}  # 本轮已用事件类别
career_log: dict[str, list[dict]] = {}    # player_id -> [SeasonRecord as dict]
season_event_log: dict[str, list[str]] = {}  # player_id -> 本赛季所有事件摘要（跨回合累积）
current_news: dict[str, list[str]] = {}  # player_id -> 当前回合新闻（持久化）
season_growth_changes: dict[str, dict] = {}  # pid -> {attr: diff} 赛季末成长变化
talk_history: dict[str, list[dict]] = {}  # player_id -> [{target, topic, round, season}]
pending_transfers: dict[str, list[dict]] = {}  # player_id -> 本轮所有转会报价列表

# 自由对话定向效果：gain 必然 ±1，risk 概率触发 -1
TALK_EFFECTS = {
    "主教练": {"gain": {"职业态度": 1, "跑位": 1, "意志力": 1}, "risk": {"伤病抗性": -1}, "risk_chance": 0.4},
    "队友":   {"gain": {"团队精神": 1, "人际处理": 1}, "risk": {}, "risk_chance": 0.0},
    "经纪人": {"gain": {"声望": 1, "多面性": 1}, "risk": {"团队精神": -1}, "risk_chance": 0.3},
    "家人":   {"gain": {"意志力": 1, "稳定性": 1, "情绪控制": 1}, "risk": {}, "risk_chance": 0.0},
    "记者":   {"gain": {"公众口碑": 1, "声望": 1}, "risk": {"公众口碑": -1}, "risk_chance": 0.5},
    "俱乐部高层": {"gain": {"声望": 1, "职业态度": 1}, "risk": {"人际处理": -1}, "risk_chance": 0.3},
    "球迷":   {"gain": {"公众口碑": 1, "声望": 1}, "risk": {}, "risk_chance": 0.0},
}

def resolve_talk_effects(target) -> dict:
    """返回本次对话的净效果"""
    info = TALK_EFFECTS.get(target, TALK_EFFECTS["队友"])
    eff = {}
    # gain：随机 ±1
    for k, v in info["gain"].items():
        eff[k] = random.choice([-v, v])
    # risk：概率触发
    if info.get("risk") and random.random() < info["risk_chance"]:
        eff.update(info["risk"])
    return eff


def get_player(pid): return players.get(pid)
def get_season(pid): return seasons.get(pid)
def get_dialogues(pid): return dialogues.setdefault(pid, [])
def get_event_queue(pid): return event_queue.setdefault(pid, [])
def enqueue_event(pid, evt): event_queue.setdefault(pid, []).append(evt)
def pop_next_event(pid):
    q = event_queue.setdefault(pid, [])
    return q.pop(0) if q else None
def clear_event_queue(pid): event_queue[pid] = []

def get_pending_transfers(pid): return pending_transfers.setdefault(pid, [])
def clear_pending_transfers(pid): pending_transfers[pid] = []

def get_completed(pid): return completed_events.setdefault(pid, [])
def add_completed(pid, s): completed_events.setdefault(pid, []).append(s)
def clear_completed(pid): completed_events[pid] = []

def get_effects(pid): return pending_effects.setdefault(pid, {})
def add_effects(pid, eff: dict):
    acc = pending_effects.setdefault(pid, {})
    for k, v in eff.items():
        acc[k] = acc.get(k, 0) + v
def clear_effects(pid): pending_effects[pid] = {}

def get_talk_effects_pending(pid): return pending_talk_effects.setdefault(pid, {})
def add_talk_effect(pid, eff: dict):
    acc = pending_talk_effects.setdefault(pid, {})
    for k, v in eff.items():
        acc[k] = acc.get(k, 0) + v
def clear_talk_effects(pid): pending_talk_effects[pid] = {}

def get_used_cats(pid): return used_categories.setdefault(pid, [])
def add_used_cat(pid, cat): used_categories.setdefault(pid, []).append(cat)
def clear_used_cats(pid): used_categories[pid] = []

# ---- 生涯记录 ----
def get_career(pid): return career_log.get(pid, [])

def get_season_events(pid): return season_event_log.setdefault(pid, [])
def add_season_event(pid, s): season_event_log.setdefault(pid, []).append(s)
def clear_season_events(pid): season_event_log[pid] = []

def get_current_news(pid): return current_news.get(pid, [])
def set_current_news(pid, news_list): current_news[pid] = list(news_list)

def get_talk_history(pid): return talk_history.setdefault(pid, [])
def add_talk_history(pid, target, topic, season, round_name):
    talk_history.setdefault(pid, []).append({
        "target": target, "topic": topic[:60],
        "season": season, "round": round_name,
    })
    # 只保留最近 5 条
    if len(talk_history[pid]) > 5:
        talk_history[pid] = talk_history[pid][-5:]

def get_talk_effects(target) -> dict:
    """返回定向效果 dict，每个属性 ±1"""
    return dict(TALK_EFFECTS.get(target, {}))


def _simulate_stats(player, season, season_events=None) -> tuple[int, int, int]:
    """根据位置+属性+球队等级+地位模拟赛季出场/进球/助攻"""
    pos = player.position
    a = player.attrs

    # 最大比赛数 = 38 联赛 + 杯赛（按球队等级）
    cup_games = {"豪门": (8, 14), "劲旅": (5, 10), "中游": (3, 7), "下游": (1, 5), "弱旅": (0, 3)}
    cup_range = cup_games.get(player.team_tier, (1, 5))
    max_games = 38 + random.randint(*cup_range)

    # 伤病扣减
    injury_count = 0
    if season_events:
        injury_count = sum(1 for e in season_events if "伤" in e or "伤病" in e)
    for _ in range(injury_count):
        max_games -= random.randint(3, 8)
    if a.伤病抗性 < 40: max_games -= random.randint(5, 10)
    elif a.伤病抗性 < 55: max_games -= random.randint(2, 5)

    # 更衣室地位大幅影响出场（保级队边缘人坐板凳，豪门核心场场首发）
    mult = LOCKER_APPEARANCE.get(player.locker_status, 1.0)
    apps = max(1, round(max_games * mult))
    apps = min(apps, max(1, max_games))

    # 每场进球期望
    gpg_map = {"中锋": 0.35, "边锋": 0.20, "前腰": 0.16, "中场": 0.08, "后腰": 0.04, "边后卫": 0.03, "中后卫": 0.03}
    base_gpg = gpg_map.get(pos, 0.06)
    shoot_mod = (a.射门 - 50) / 200 + (a.跑位 - 50) / 400
    goals = round(apps * base_gpg * (1 + shoot_mod) * random.uniform(0.6, 1.4))
    goals = max(0, goals)

    # 助攻（同样降低）
    apg_map = {"前腰": 0.22, "边锋": 0.18, "中场": 0.12, "中锋": 0.07, "后腰": 0.07, "边后卫": 0.10, "中后卫": 0.02}
    base_apg = apg_map.get(pos, 0.05)
    pass_mod = (a.传球 - 50) / 250 + (a.才华 - 50) / 400
    assists = round(apps * base_apg * (1 + pass_mod) * random.uniform(0.6, 1.4))
    assists = max(0, assists)

    return apps, goals, assists


def _generate_honors(player, season, goals, assists) -> list[str]:
    """基于球队成绩+个人数据生成荣誉"""
    h = []
    tier = player.team_tier
    rank = season.team_rank
    a = player.attrs

    # 团队荣誉
    if rank == 1: h.append("联赛冠军")
    elif rank <= 3: h.append("联赛前三")
    if tier in ("豪门", "劲旅") and random.random() < 0.3: h.append("国内杯赛冠军")
    if tier == "豪门" and rank <= 2 and random.random() < 0.25: h.append("欧冠冠军")
    if tier in ("豪门", "劲旅") and rank <= 4 and random.random() < 0.2: h.append("欧战冠军")

    # 个人荣誉
    if goals >= 28: h.append("联赛金靴")
    elif goals >= 20: h.append(f"联赛射手榜前五({goals}球)")
    if assists >= 16: h.append("联赛助攻王")
    elif assists >= 11: h.append(f"联赛助攻榜前五({assists}次)")

    overall = (sum(a.model_dump().values()) / 28)
    if overall > 82 and random.random() < 0.2: h.append("赛季最佳球员")
    if player.age <= 23 and overall > 74: h.append("最佳年轻球员提名")
    if overall > 78 and random.random() < 0.3: h.append("入选赛季最佳阵容")

    # 特殊情况
    if goals >= 35: h.append("欧洲金靴")
    if goals + assists >= 45: h.append("赛季进球+助攻 45+")

    return h


def _generate_season_awards(player, season, goals, assists, honors) -> list[str]:
    """赛季末评选个人奖项（高门槛）"""
    a = player.attrs
    awards = []
    hard_avg = sum(a.model_dump().get(k, 0) for k in HARD_ATTRS) / len(HARD_ATTRS)
    soft_avg = sum(a.model_dump().get(k, 0) for k in SOFT_ATTRS) / len(SOFT_ATTRS)
    rank = season.team_rank

    # 金球奖：极难
    if hard_avg >= 85 and a.声望 >= 85 and rank <= 2 and any("欧冠" in h for h in honors):
        if goals >= 30 or assists >= 20:
            awards.append("金球奖")
    elif hard_avg >= 82 and a.声望 >= 80 and rank <= 4:
        if goals >= 25 and random.random() < 0.3:
            awards.append("金球奖提名")

    # 联赛最佳阵容
    if hard_avg >= 78 and rank <= 6 and (goals + assists) >= 20:
        awards.append("联赛最佳阵容")

    # 联赛MVP
    if hard_avg >= 80 and a.声望 >= 75 and rank <= 4 and (goals >= 22 or assists >= 18):
        awards.append("联赛MVP")

    # 金童奖
    if player.age <= 23 and hard_avg >= 74 and (goals + assists) >= 18:
        awards.append("金童奖")

    # 最佳新人
    if player.age <= 21 and hard_avg >= 68 and (goals + assists) >= 12:
        awards.append("最佳新人")

    # 最佳防守球员（后场）
    if player.position in ("中后卫", "边后卫", "后腰") and hard_avg >= 75 and rank <= 8:
        if a.盯人 >= 80 and a.抢断 >= 80:
            awards.append("联赛最佳防守球员")

    # 年度最佳进球提名
    if goals >= 15 and a.才华 >= 80 and a.技术 >= 80 and random.random() < 0.15:
        awards.append("年度最佳进球提名")

    # 公平竞赛奖
    if soft_avg >= 78 and a.公众口碑 >= 80 and a.情绪控制 >= 75:
        awards.append("公平竞赛奖")

    return awards
_POS_W = {
    "中后卫": {"射门":1,"跑位":2,"定位球":1,"传球":2,"盘带":1,"技术":1,"才华":1,"盯人":6,"抢断":6,"站位":6,"强壮":5,"速度":3,"跳跃":5,"体力":3,"头球":5},
    "边后卫": {"射门":1,"跑位":3,"定位球":2,"传球":3,"盘带":3,"技术":3,"才华":2,"盯人":5,"抢断":5,"站位":5,"强壮":3,"速度":5,"跳跃":3,"体力":4,"头球":2},
    "后腰":   {"射门":2,"跑位":3,"定位球":2,"传球":4,"盘带":2,"技术":3,"才华":2,"盯人":5,"抢断":5,"站位":5,"强壮":4,"速度":3,"跳跃":3,"体力":5,"头球":2},
    "中场":   {"射门":2,"跑位":4,"定位球":3,"传球":5,"盘带":4,"技术":5,"才华":4,"盯人":3,"抢断":3,"站位":3,"强壮":2,"速度":3,"跳跃":2,"体力":4,"头球":2},
    "前腰":   {"射门":4,"跑位":5,"定位球":5,"传球":5,"盘带":5,"技术":5,"才华":6,"盯人":1,"抢断":1,"站位":2,"强壮":1,"速度":3,"跳跃":2,"体力":3,"头球":1},
    "边锋":   {"射门":4,"跑位":5,"定位球":3,"传球":3,"盘带":5,"技术":5,"才华":5,"盯人":1,"抢断":1,"站位":1,"强壮":2,"速度":5,"跳跃":2,"体力":4,"头球":2},
    "中锋":   {"射门":6,"跑位":5,"定位球":2,"传球":2,"盘带":3,"技术":2,"才华":2,"盯人":1,"抢断":1,"站位":2,"强壮":4,"速度":4,"跳跃":4,"体力":3,"头球":5},
}


def generate_attrs_fallback(team_tier: str, position: str) -> Attributes:
    tier = TEAM_TIERS[team_tier]
    w = _POS_W.get(position, _POS_W["中场"])

    def _gen(hard):
        rng = tier["hard_range"] if hard else tier["soft_range"]
        target = random.randint(*rng)
        attrs_list = HARD_ATTRS if hard else SOFT_ATTRS
        vals = {}
        for a in attrs_list:
            if a in INVERSE_ATTRS:
                vals[a] = random.randint(5, 35)
            elif a == "公众口碑":
                vals[a] = random.randint(45, 75)
            elif a == "伤病抗性":
                vals[a] = random.randint(55, 85)
            elif hard:
                base = 40 + (w.get(a, 2) - 1) * 6 + random.randint(-8, 8)
                vals[a] = max(0, min(100, base))
            else:
                vals[a] = random.randint(35, 75)
        total = sum(vals.values())
        if total > 0:
            s = target / total
            for a in attrs_list:
                vals[a] = max(0, min(100, round(vals[a] * s)))
        return vals

    return Attributes(**{**_gen(True), **_gen(False)})


LOCKER_LEVELS = ["边缘人物", "普通成员", "重要角色", "核心领袖", "传奇"]
LOCKER_APPEARANCE = {"边缘人物": 0.65, "普通成员": 0.85, "重要角色": 1.0, "核心领袖": 1.15, "传奇": 1.3}

# 回合 Buff（结算时随机，下回合生效）
player_buffs: dict[str, str] = {}  # pid -> buff_name

def calc_soft_power(pid) -> tuple[int, str]:
    """返回 (软实力均分, 描述标签)"""
    p = players.get(pid)
    if not p: return 50, ""
    a = p.attrs
    soft = [a.意志力, a.勇敢, a.抗压能力, a.稳定性, a.情绪控制,
            a.职业态度, a.团队精神, a.人际处理, a.公众口碑, a.声望]
    avg = sum(soft) / len(soft)
    if avg >= 75: tag = "心理素质出色，近期运势上佳"
    elif avg >= 60: tag = "心理状态平稳"
    elif avg >= 45: tag = "偶尔心态起伏"
    else: tag = "心理层面存在短板，易出状况"
    return int(avg), tag

def roll_settlement_buff(pid) -> str | None:
    """根据本回合事件内容生成Buff，返回描述"""
    p = players.get(pid)
    events = list(get_completed(pid))
    if not p or not events:
        return None

    # 分析事件类型
    has_good = any(kw in e for e in events for kw in ["进球","助攻","获胜","表扬","成功","提升","加薪","续约"])
    has_bad = any(kw in e for e in events for kw in ["受伤","冲突","批评","失败","内讧","罚款","停赛","降级"])
    has_conflict = any("人际" in e or "冲突" in e or "内讧" in e for e in events)
    has_injury = any("伤" in e for e in events)
    has_transfer = any("转会" in e for e in events)

    good_buffs = [
        "状态火热：下回合信心十足",
        "教练信任：训练中备受重用",
        "媒体赞誉：公众形象正面",
    ]
    bad_buffs = [
        "状态低迷：需要找回节奏",
        "身体疲惫：训练强度需调整",
        "舆论压力：媒体密切关注",
    ]

    if has_injury:
        buff = "伤愈恢复：康复训练中，需控制出场"
    elif has_conflict:
        buff = "关系紧张：与部分队友需要时间修复"
    elif has_transfer:
        buff = "转会传闻：未来去向引发猜测"
    elif has_good and not has_bad:
        buff = random.choice(good_buffs)
    elif has_bad and not has_good:
        buff = random.choice(bad_buffs)
    elif has_good and has_bad:
        buff = random.choice(good_buffs + bad_buffs)
    else:
        buff = random.choice(good_buffs)

    player_buffs[pid] = buff
    return buff


def _get_wage_level(player) -> str:
    """根据周薪和球队等级返回工资等级"""
    tier = player.team_tier
    w = player.weekly_wage
    if tier == "豪门":
        if w >= 50: return "顶薪"
        if w >= 30: return "高薪"
        if w >= 15: return "中产"
        if w >= 5: return "底薪"
        return "童工"
    elif tier == "劲旅":
        if w >= 30: return "顶薪"
        if w >= 18: return "高薪"
        if w >= 8: return "中产"
        if w >= 3: return "底薪"
        return "童工"
    elif tier == "中游":
        if w >= 15: return "高薪"
        if w >= 7: return "中产"
        if w >= 2.5: return "底薪"
        return "童工"
    else:  # 下游/弱旅
        if w >= 8: return "高薪"
        if w >= 4: return "中产"
        if w >= 1.5: return "底薪"
        return "童工"


def calc_transfer_interest(pid) -> int:
    """转会兴趣值。0=无人问津，20+=豪门哄抢。基于表现/声望/能力/合同。"""
    p = players.get(pid)
    s = seasons.get(pid)
    if not p or not s:
        return 0

    # 前两赛季基本无人报价
    if s.season <= 1:
        return 0

    interest = 0
    a = p.attrs

    # 上两季表现（需持续发挥）
    career = list(get_career(pid))
    last_goals = 0; last_assists = 0; prev_goals = 0
    if len(career) >= 1:
        last = career[-1]
        last_goals = last.get("goals", 0)
        last_assists = last.get("assists", 0)
    if len(career) >= 2:
        prev_goals = career[-2].get("goals", 0)

    # 最近一季进球
    if last_goals >= 25: interest += 8
    elif last_goals >= 15: interest += 5
    elif last_goals >= 8: interest += 3
    elif last_goals >= 3: interest += 1
    if prev_goals >= 15 and last_goals >= 15: interest += 3

    # 最近一季助攻
    if last_assists >= 12: interest += 6
    elif last_assists >= 7: interest += 3
    elif last_assists >= 3: interest += 1
    if last_goals == 0 and last_assists == 0:
        interest -= 5

    # 声望
    if a.声望 >= 85: interest += 5
    elif a.声望 >= 70: interest += 3
    elif a.声望 >= 55: interest += 1
    elif a.声望 < 35: interest -= 3

    # 球队等级
    tier_weight = {"豪门": -3, "劲旅": 1, "中游": 4, "下游": 7, "弱旅": 9}
    interest += tier_weight.get(p.team_tier, 3)

    # 合同长短
    if p.seasons_left <= 1: interest += 5
    elif p.seasons_left == 2: interest += 2
    elif p.seasons_left >= 4: interest -= 3

    # 冷却期
    if p.last_transfer_season > 0 and s.season - p.last_transfer_season < 2:
        return 0

    # 更衣室地位
    if p.locker_status == "传奇": interest -= 8
    elif p.locker_status == "核心领袖": interest -= 5

    # 年龄
    if p.age >= 35: interest -= 12
    elif p.age >= 33: interest -= 6
    elif p.age >= 31: interest -= 2
    if p.age <= 20: interest -= 2

    # 硬实力门坎
    hard_sum = sum(a.model_dump().get(k, 0) for k in HARD_ATTRS)
    if hard_sum < 520: interest = min(interest, 3)
    elif hard_sum < 580: interest = min(interest, 8)
    elif hard_sum < 650: interest = min(interest, 14)

    return max(0, interest)


def _calculate_locker_status(pid):
    """冬窗/夏窗结算时重新计算更衣室地位"""
    p = players.get(pid)
    s = seasons.get(pid)
    if not p or not s:
        return None, 0

    a = p.attrs

    # 1. 属性匹配度
    tier_expect = TEAM_TIERS[p.team_tier]["hard_range"]
    avg_tier = (tier_expect[0] + tier_expect[1]) / 2
    player_hard = sum(a.model_dump().get(k, 0) for k in HARD_ATTRS)
    match_score = max(-25, min(25, round((player_hard - avg_tier) / 10)))

    # 2. 社交属性
    social = a.人际处理 * 0.18 + a.团队精神 * 0.10 + a.职业态度 * 0.08 + a.声望 * 0.08 + a.意志力 * 0.05 + a.公众口碑 * 0.05
    social = min(25, social)

    # 3. 工资匹配度（档次比较）
    wl = _get_wage_level(p)
    wage_map = {"顶薪": 12, "高薪": 8, "中产": 4, "底薪": 0, "童工": -4}
    wage_score = wage_map.get(wl, 0)

    # 4. 资历
    career = list(get_career(pid))
    consecutive = 0
    for r in reversed(career):
        if r.get("club") == p.team_name:
            consecutive += 1
        else:
            break
    if s.round_idx >= 3:
        consecutive += 1
    seniority = min(25, consecutive * 2)

    # 5. 表现
    performance = 0
    if career:
        last = career[-1]
        performance = min(15, (last.get("goals", 0) + last.get("assists", 0)) // 2)

    # 6. 年龄
    if p.age <= 20: age_bonus = -3
    elif p.age <= 23: age_bonus = 0
    elif p.age <= 26: age_bonus = 2
    elif p.age <= 29: age_bonus = 5
    elif p.age <= 33: age_bonus = 8
    else: age_bonus = 5

    total = match_score + social + wage_score + seniority + performance + age_bonus

    if total >= 105: status = "传奇"
    elif total >= 78: status = "核心领袖"
    elif total >= 50: status = "重要角色"
    elif total >= 20: status = "普通成员"
    else: status = "边缘人物"

    return status, total


def renew_contract(pid, seasons, weekly_wage, release_clause=0.0):
    """续约/签新合同"""
    p = players.get(pid)
    if not p:
        return
    p.seasons_left = max(1, min(5, seasons))
    p.weekly_wage = max(0.5, float(weekly_wage))
    p.release_clause = max(0.0, float(release_clause))
    players[pid] = p
    return _get_wage_level(p)


def decrement_contract(pid):
    """赛季结束合同年 -1，返回是否到期"""
    p = players.get(pid)
    if not p:
        return False
    p.seasons_left = max(0, p.seasons_left - 1)
    players[pid] = p
    return p.seasons_left == 0


def _apply_trait(attrs: dict, trait: str) -> dict:
    """特点重新分配：硬↔硬，软↔软，混合按比例分流，总数不变"""
    if not trait or trait not in TRAITS:
        return attrs
    info = TRAITS[trait]
    boost = info["boost"]
    is_negative = info.get("type") == "negative"

    # 按硬/软拆分量
    hard_boost = {k: v for k, v in boost.items() if k in HARD_ATTRS}
    soft_boost = {k: v for k, v in boost.items() if k in SOFT_ATTRS}
    hard_total = sum(hard_boost.values())
    soft_total = sum(soft_boost.values())

    for boost_dict, total, pool in [
        (hard_boost, hard_total, HARD_ATTRS),
        (soft_boost, soft_total, SOFT_ATTRS),
    ]:
        if total == 0:
            continue
        if is_negative:
            # 负面：从 boost 扣，加到同类别其他
            for k, v in boost_dict.items():
                if k in attrs:
                    attrs[k] = max(5, attrs[k] - v)
            others = [k for k in pool if k not in boost_dict and attrs.get(k, 0) < 95]
            if not others:
                continue
            random.shuffle(others)
            for i in range(total):
                k = others[i % len(others)]
                attrs[k] = min(99, attrs.get(k, 0) + 1)
        else:
            # 正面：加到 boost，从同类别其他扣
            for k, v in boost_dict.items():
                if k in attrs:
                    attrs[k] = min(99, attrs[k] + v)
            others = [k for k in pool if k not in boost_dict and attrs.get(k, 0) > 15]
            if not others:
                continue
            random.shuffle(others)
            for i in range(total):
                k = others[i % len(others)]
                if attrs.get(k, 0) > 10:
                    attrs[k] -= 1
    return attrs

def _apply_body_modifiers(attrs: dict, height: int, weight: int, position: str) -> dict:
    """对AI生成的属性用身高体重微调"""
    # 身高修正
    if height >= 192:
        attrs["盘带"] = max(0, attrs.get("盘带", 50) - random.randint(3, 8))
        attrs["头球"] = min(100, attrs.get("头球", 50) + random.randint(3, 8))
        attrs["跳跃"] = min(100, attrs.get("跳跃", 50) + random.randint(2, 5))
    elif height >= 188:
        attrs["头球"] = min(100, attrs.get("头球", 50) + random.randint(2, 5))
        attrs["盘带"] = max(0, attrs.get("盘带", 50) - random.randint(1, 4))
    elif height <= 168:
        attrs["盘带"] = min(100, attrs.get("盘带", 50) + random.randint(3, 8))
        attrs["头球"] = max(0, attrs.get("头球", 50) - random.randint(3, 8))
    elif height <= 174:
        attrs["盘带"] = min(100, attrs.get("盘带", 50) + random.randint(1, 4))

    # 体重修正
    if weight >= 90:
        attrs["速度"] = max(0, attrs.get("速度", 50) - random.randint(3, 8))
        attrs["强壮"] = min(100, attrs.get("强壮", 50) + random.randint(3, 8))
    elif weight >= 83:
        attrs["速度"] = max(0, attrs.get("速度", 50) - random.randint(1, 4))
        attrs["强壮"] = min(100, attrs.get("强壮", 50) + random.randint(1, 4))
    elif weight <= 62:
        attrs["速度"] = min(100, attrs.get("速度", 50) + random.randint(2, 6))
        attrs["强壮"] = max(0, attrs.get("强壮", 50) - random.randint(2, 6))
    elif weight <= 68:
        attrs["速度"] = min(100, attrs.get("速度", 50) + random.randint(1, 3))
        attrs["强壮"] = max(0, attrs.get("强壮", 50) - random.randint(1, 3))

    return attrs


def _apply_body_to_attrs(attrs: Attributes, height: int, weight: int, position: str) -> Attributes:
    """对fallback属性用身高体重修正"""
    d = attrs.model_dump()
    d = _apply_body_modifiers(d, height, weight, position)
    total = sum(d.values())
    if total > 0:
        scale = sum(attrs.model_dump().values()) / total
        for k in d:
            d[k] = max(0, min(100, round(d[k] * scale)))
    return Attributes(**d)


def _real_team_stats(league_level: str, round_idx: int) -> tuple[int, int, int]:
    """返回真实的 (已赛场次, 积分, 排名)，基于38轮联赛模型。league_level为球队在自身联赛中的地位"""
    # 夏窗=0, 上半前期=1, 上半后期=2, 冬窗=3, 下半前期=4, 下半后期=5
    games_per_round = [0, 9, 9, 7, 9, 7]  # 对应各回合累计场次
    cum = sum(games_per_round[:round_idx])
    cur = games_per_round[round_idx] if round_idx < len(games_per_round) else 0
    games = cum + (random.randint(cur - 1, cur + 1) if cur > 0 else 0)
    games = max(0, min(38, games))

    # 联赛地位决定场均积分和排名
    level_map = {
        "争冠": (2.0, 2.6, 1, 3),
        "上游": (1.6, 2.2, 3, 7),
        "中游": (1.2, 1.7, 7, 12),
        "下游": (0.8, 1.3, 12, 17),
        "保级": (0.4, 0.9, 15, 20),
    }
    lo, hi, r_lo, r_hi = level_map.get(league_level, (1.2, 1.7, 7, 12))
    ppg = lo + random.random() * (hi - lo)
    pts = max(0, round(games * ppg))
    rank = random.randint(r_lo, r_hi)
    return games, pts, rank


def create_player(name, team_tier, league_level, team_name, nationality, position, age, height, weight, attrs_dict=None, traits=None) -> Player:
    traits = traits or []
    if attrs_dict:
        attrs_dict = _apply_body_modifiers(attrs_dict, height, weight, position)
        for t in traits:
            attrs_dict = _apply_trait(attrs_dict, t)
        attrs = Attributes(**{k: attrs_dict.get(k, 50) for k in ALL_ATTRS})
    else:
        attrs = generate_attrs_fallback(team_tier, position)
        attrs = _apply_body_to_attrs(attrs, height, weight, position)
        if traits:
            d = attrs.model_dump()
            for t in traits:
                d = _apply_trait(d, t)
            attrs = Attributes(**d)

    # 年龄折扣
    if age <= 20:
        d = attrs.model_dump()
        for k in d: d[k] = max(5, round(d[k] * 0.92))
        attrs = Attributes(**d)
    elif age <= 23:
        d = attrs.model_dump()
        for k in d: d[k] = max(5, round(d[k] * 0.96))
        attrs = Attributes(**d)

    # 强制钳位到等级范围（高于上限等比缩，低于下限等比拉）
    tier_info = TEAM_TIERS.get(team_tier, TEAM_TIERS["中游"])
    hard_min, hard_max = tier_info["hard_range"]
    soft_min, soft_max = tier_info["soft_range"]
    d = attrs.model_dump()
    h_sum = sum(d.get(k, 0) for k in HARD_ATTRS)
    s_sum = sum(d.get(k, 0) for k in SOFT_ATTRS)
    if h_sum > hard_max:
        scale = hard_max / h_sum
        for k in HARD_ATTRS: d[k] = max(5, round(d[k] * scale))
    elif h_sum < hard_min and h_sum > 0:
        scale = hard_min / h_sum
        for k in HARD_ATTRS: d[k] = min(99, round(d[k] * scale))
    if s_sum > soft_max:
        scale = soft_max / s_sum
        for k in SOFT_ATTRS: d[k] = max(5, round(d[k] * scale))
    elif s_sum < soft_min and s_sum > 0:
        scale = soft_min / s_sum
        for k in SOFT_ATTRS: d[k] = min(99, round(d[k] * scale))
    attrs = Attributes(**d)

    # 初始合同：按球队等级
    init_wage = {"豪门": 8.0, "劲旅": 5.0, "中游": 3.0}.get(team_tier, 2.0)
    from config import TRAITS as _TRAITS
    neg_count = sum(1 for t in traits if _TRAITS.get(t, {}).get("type") == "negative")
    p = Player(name=name, age=age, height=height, weight=weight, nationality=nationality,
               team_tier=team_tier, league_level=league_level, team_name=team_name, position=position, attrs=attrs,
               weekly_wage=init_wage, seasons_left=3, trait_count=len(traits),
               neg_trait_count=neg_count, traits=list(traits))
    players[p.id] = p

    # 新角色从第一赛季夏窗开始（round_idx=0），夏窗场次为0
    games, pts, rank = _real_team_stats(league_level, 0)
    seasons[p.id] = SeasonState(season=1, round_idx=0, round_name=ROUNDS[0],
                                team_rank=rank, team_points=pts, team_games=games)
    dialogues[p.id] = []
    event_queue[p.id] = []
    completed_events[p.id] = []
    pending_effects[p.id] = {}
    used_categories[p.id] = []
    return p


def adjust_attributes(pid, adjustments: dict) -> Player:
    p = players[pid]
    total = sum(abs(v) for v in adjustments.values())
    if total > 30:
        raise ValueError(f"±30点限制，当前{total}")
    attrs = p.attrs.model_dump()
    for a, d in adjustments.items():
        if a in ALL_ATTRS:
            attrs[a] = max(0, min(100, attrs[a] + d))
    p.attrs = Attributes(**attrs)
    players[pid] = p
    return p


def apply_effects(pid, effects: dict, temp_status="无"):
    p = players[pid]
    attrs = p.attrs.model_dump()
    overflow_effects = {}
    # 清理内部键
    for k in list(effects.keys()):
        if k.startswith("_offer") or k.startswith("_neg"):
            del effects[k]
    # 体力保护：事件效果不扣体力
    for a, d in list(effects.items()):
        if a == "体力" and d < 0:
            continue  # 跳过负值
        if a in ALL_ATTRS:
            old = attrs[a]
            attrs[a] = max(0, min(99, old + d))
            # 正向溢出：本该加d但被99截断，多余点数转移
            overflow = (old + d) - attrs[a]
            if overflow > 0:
                # 随机分给其他未满属性
                pool = [k for k in ALL_ATTRS if k != a and attrs.get(k, 0) < 99]
                if pool:
                    dest = random.choice(pool)
                    attrs[dest] = min(99, attrs[dest] + overflow)
                    overflow_effects[f"{a}+{overflow}→{dest}"] = overflow
    p.attrs = Attributes(**attrs)
    add_effects(pid, effects)
    # 溢出也记入效果
    if overflow_effects:
        add_effects(pid, overflow_effects)

    if temp_status and temp_status != "无":
        p.temp_status = temp_status
        if temp_status == "轻伤休养":
            p.injury_rounds = 1
        elif temp_status == "重伤缺阵":
            p.injury_rounds = random.randint(1, 2)
        elif temp_status == "停赛":
            p.suspended_rounds = random.randint(1, 2)

    players[pid] = p


def advance_round(pid):
    p = players[pid]
    s = seasons[pid]
    new_idx = s.round_idx + 1

    if new_idx >= len(ROUNDS):
        return _new_season(pid)

    # 状态倒计时
    if p.injury_rounds > 0:
        p.injury_rounds -= 1
        if p.injury_rounds == 0 and "伤" in p.temp_status:
            p.temp_status = "无"
            add_season_event(pid, "伤愈复出，已恢复正常训练和比赛")
    if p.suspended_rounds > 0:
        p.suspended_rounds -= 1
        if p.suspended_rounds == 0 and p.temp_status == "停赛":
            p.temp_status = "无"
            add_season_event(pid, "停赛期满，可正常出战")

    s.round_idx = new_idx
    s.round_name = ROUNDS[new_idx]
    games, pts, rank = _real_team_stats(p.league_level, new_idx)
    s.team_games = games
    s.team_points = pts
    s.team_rank = rank

    # 冬窗(3)或夏窗(0)结算更衣室地位
    if s.round_name in ("夏窗", "冬窗"):
        old_status = p.locker_status
        new_status, score = _calculate_locker_status(pid)
        if new_status and new_status != old_status:
            p.locker_status = new_status
            print(f"[更衣室] {p.name} 地位变更: {old_status} → {new_status} (得分:{score})")

    # 把本轮事件累积到赛季日志（跨回合保留）
    for evt in get_completed(pid):
        add_season_event(pid, evt)

    clear_event_queue(pid)
    clear_completed(pid)
    clear_effects(pid)
    clear_talk_effects(pid)
    clear_used_cats(pid)

    players[pid] = p
    seasons[pid] = s
    return p, s


def _new_season(pid):
    p = players[pid]
    old = seasons[pid]

    # ---- 保存本赛季生涯记录 ----
    for evt in get_completed(pid):
        add_season_event(pid, evt)
    highlights = list(get_season_events(pid))
    apps, goals, assists = _simulate_stats(p, old, highlights)
    honors = _generate_honors(p, old, goals, assists)
    awards = _generate_season_awards(p, old, goals, assists, honors)
    hard_sum = sum(p.attrs.model_dump().get(a, 0) for a in HARD_ATTRS)
    soft_sum = sum(p.attrs.model_dump().get(a, 0) for a in SOFT_ATTRS)

    record = SeasonRecord(
        season=old.season, age=p.age, club=p.team_name,
        league_position=old.team_rank,
        appearances=apps, goals=goals, assists=assists,
        honors=honors, highlights=highlights[-8:],
        awards=awards,
        hard_sum=hard_sum, soft_sum=soft_sum,
    )
    career_log.setdefault(pid, []).append(record.model_dump())
    clear_season_events(pid)

    # 合同年 -1
    contract_expired = decrement_contract(pid)
    if contract_expired:
        print(f"[合同] {p.name} 合同到期！夏窗须决定去向")

    # ---- 年龄 + 赛季事件成长 ----
    p.age += 1
    attrs = p.attrs.model_dump()

    # 事件→属性映射
    event_attr_map = {
        "比赛表现": HARD_ATTRS[:7],           # 射门→才华
        "训练日常": ["职业态度","体力","意志力"],
        "人际交往": ["人际处理","团队精神","情绪控制"],
        "媒体舆论": ["公众口碑","声望","情绪控制"],
        "转会传闻": ["声望","多面性","稳定性"],
        "伤病医疗": ["意志力","伤病抗性"],
        "场外生活": ["情绪控制","稳定性","公众口碑"],
        "生涯抉择": ["多面性","意志力","声望"],
    }

    # 统计本季事件类型和处理结果
    events = list(get_season_events(pid))
    handled_well = sum(1 for e in events if any(kw in e for kw in ["成功","提升","表扬","夺冠","获奖"]))
    handled_bad = sum(1 for e in events if any(kw in e for kw in ["失败","受伤","冲突","批评","下滑","罚款"]))

    # 年龄幅值
    if p.age <= 20: pts = random.randint(5, 8); decline = False
    elif p.age <= 25: pts = random.randint(3, 6); decline = False
    elif p.age <= 29: pts = random.randint(1, 4); decline = (handled_bad > handled_well)
    elif p.age <= 33: pts = random.randint(1, 3); decline = True
    else: pts = random.randint(2, 5); decline = True

    # 从赛季涉及的事件类别中选相关属性
    related = set()
    for evt in events:
        for cat, attrs_list in event_attr_map.items():
            if cat in evt:
                related.update(attrs_list)
    if not related:
        related = set(random.sample(ALL_ATTRS, min(6, len(ALL_ATTRS))))

    candidates = list(related)
    random.shuffle(candidates)

    before_growth = dict(attrs)
    overflow_map = []
    if decline:
        for _ in range(pts):
            avail = [a for a in candidates if attrs.get(a, 0) > 5 and not (a in SOFT_ATTRS and random.random() < 0.5)]
            if not avail:
                avail = [k for k in ALL_ATTRS if attrs.get(k, 0) > 5]
            if not avail:
                break
            a = random.choice(avail)
            attrs[a] = max(5, attrs[a] - 1)
    else:
        # 均匀分配，满99的点溢出到其他候选
        counts = {a: 0 for a in candidates}
        gave = set()
        overflow_map = []
        for _ in range(pts):
            avail = [a for a in candidates if counts[a] < 2 and attrs.get(a, 0) < 99]
            if not avail:
                avail = [k for k in ALL_ATTRS if attrs.get(k, 0) < 99]
            if not avail: break
            a = random.choice(avail)
            counts[a] = counts.get(a, 0) + 1
            gave.add(a)
            attrs[a] = min(99, attrs[a] + 1)
        # 记录溢出：候选中被跳过（≥98满或达2次上限）→实际加最多的属性
        got_points = {a: n for a, n in counts.items() if n > 0}
        skipped = [c for c in candidates if counts.get(c, 0) == 0 and attrs.get(c, 0) >= 96]
        for s in skipped:
            if got_points:
                dest = max(got_points, key=got_points.get)
                overflow_map.append((s, dest))
        # 年轻球员净涨（只抽回一半），年长持平
        if p.age <= 23:
            deduct = pts // 3
        elif p.age <= 28:
            deduct = pts // 2
        else:
            deduct = pts
        others = [k for k in ALL_ATTRS if k not in gave and attrs.get(k, 0) > 15]
        if others:
            random.shuffle(others)
            for i in range(deduct):
                k = others[i % len(others)]
                if attrs.get(k, 0) > 10:
                    attrs[k] -= 1

    p.attrs = Attributes(**attrs)
    p.temp_status = "无"

    # 记录成长变化
    growth_diff = {}
    for k in ALL_ATTRS:
        diff = attrs.get(k, 0) - before_growth.get(k, 0)
        if diff != 0:
            growth_diff[k] = diff
    # 溢出标记：射门+2→速度
    for from_attr, to_attr in overflow_map:
        growth_diff[f"{from_attr}+1→{to_attr}"] = 1
    season_growth_changes[pid] = growth_diff

    games, pts, rank = _real_team_stats(p.league_level, 0)
    # 新赛季氛围自然调整（表现好可改善）
    atm = old.atmosphere
    if old.team_rank <= 3:
        # 成绩好：氛围向上或保持
        if atm == "平淡": atm = random.choice(["融洽", "平淡"])
        elif atm == "涣散": atm = "平淡"
        elif atm == "内讧": atm = random.choice(["涣散", "平淡"])
    elif old.team_rank >= 15:
        # 成绩差：可能下滑
        if atm == "融洽": atm = random.choice(["平淡", "融洽"])
        elif atm == "鼎盛": atm = "融洽"
        elif atm == "平淡": atm = random.choice(["涣散", "平淡"])
    else:
        # 中游：轻度回归
        if atm == "鼎盛": atm = "融洽"
        elif atm == "内讧": atm = "涣散"
    ns = SeasonState(season=old.season+1, round_idx=0, round_name=ROUNDS[0],
                     team_rank=rank, team_points=pts, team_games=games, atmosphere=atm)

    clear_event_queue(pid)
    clear_completed(pid)
    clear_effects(pid)
    clear_used_cats(pid)

    players[pid] = p
    seasons[pid] = ns
    return p, ns


def settlement_prep(pid):
    eff = dict(get_effects(pid))
    # 合并对话累积效果
    talk = get_talk_effects_pending(pid)
    for k, v in talk.items():
        eff[k] = eff.get(k, 0) + v
    clear_talk_effects(pid)
    return players[pid], seasons[pid], eff, list(get_completed(pid))


# ============================================================
# 存档系统 (JSON 文件)
# ============================================================
import json as _json
import os as _os
from config import SAVES_DIR

_SAVE_VERSION = 2


def save_game(pid):
    """自动保存到 saves/{pid}.json"""
    _write_save(pid, pid, "自动存档")


def create_named_save(pid, name):
    """手动命名存档 → saves/{pid}_m_{uuid}.json，返回 save_id"""
    import uuid as _uuid
    save_id = f"{pid}_m_{_uuid.uuid4().hex[:6]}"
    _write_save(pid, save_id, name.strip() or "未命名")
    return save_id


def _write_save(pid, save_id, slot_name):
    """保存角色状态到 saves/{save_id}.json"""
    if pid not in players:
        return
    _os.makedirs(SAVES_DIR, exist_ok=True)

    p = players[pid]
    s = seasons[pid]
    data = {
        "version": _SAVE_VERSION,
        "save_id": save_id,
        "slot_name": slot_name,
        "updated_at": __import__("datetime").datetime.now().isoformat(),
        "player": p.model_dump(),
        "season": s.model_dump(),
        "dialogues": [d.model_dump() for d in get_dialogues(pid)],
        "career_log": list(get_career(pid)),
        "season_event_log": list(get_season_events(pid)),
        "event_queue": list(get_event_queue(pid)),
        "completed_events": list(get_completed(pid)),
        "pending_effects": dict(get_effects(pid)),
        "used_categories": list(get_used_cats(pid)),
        "current_news": list(get_current_news(pid)),
        "talk_history": list(get_talk_history(pid)),
        "pending_talk_effects": dict(get_talk_effects_pending(pid)),
        "pending_transfers": list(pending_transfers.get(pid, [])),
    }

    tmp = _os.path.join(SAVES_DIR, f"{save_id}.tmp")
    dst = _os.path.join(SAVES_DIR, f"{save_id}.json")
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
    _os.replace(tmp, dst)
    _update_save_index(save_id, data)


def load_game(save_id):
    """从 saves/{save_id}.json 恢复全部状态（兼容自动/手动存档）"""
    dst = _os.path.join(SAVES_DIR, f"{save_id}.json")
    if not _os.path.isfile(dst):
        raise FileNotFoundError(f"存档 {save_id} 不存在")

    with open(dst, "r", encoding="utf-8") as f:
        data = _json.load(f)

    if data.get("version", 0) > _SAVE_VERSION:
        raise RuntimeError(f"存档版本 {data['version']} 高于当前版本 {_SAVE_VERSION}")

    # v1 → v2 迁移：旧回合顺序 [上半前期/上半后期/冬窗/下半前期/下半后期/夏窗] → 新 [夏窗/上半前期/.../下半后期]
    if data.get("version", 0) < 2:
        old_idx = data["season"].get("round_idx", 0)
        old_to_new = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 0}
        data["season"]["round_idx"] = old_to_new.get(old_idx, old_idx)
        data["season"]["round_name"] = ROUNDS[data["season"]["round_idx"]]
        data["version"] = 2

    pdata = data["player"]
    sdata = data["season"]
    pid = pdata["id"]

    attrs = Attributes(**{k: pdata["attrs"].get(k, 50) for k in ALL_ATTRS})
    players[pid] = Player(
        id=pid, name=pdata["name"], age=pdata["age"], height=pdata["height"],
        weight=pdata["weight"], nationality=pdata["nationality"],
        team_tier=pdata["team_tier"], league_level=pdata.get("league_level", "中游"),
        team_name=pdata["team_name"], position=pdata["position"], attrs=attrs,
        temp_status=pdata.get("temp_status", "无"),
        injury_rounds=pdata.get("injury_rounds", 0),
        suspended_rounds=pdata.get("suspended_rounds", 0),
        locker_status=pdata.get("locker_status", "普通成员"),
        seasons_left=pdata.get("seasons_left", 3),
        weekly_wage=float(pdata.get("weekly_wage", 5)),
        release_clause=float(pdata.get("release_clause", 0)),
        trait_count=pdata.get("trait_count", 0),
        neg_trait_count=pdata.get("neg_trait_count", 0),
        traits=pdata.get("traits", []),
        neg_success=pdata.get("neg_success", 0),
        last_transfer_season=pdata.get("last_transfer_season", 0),
    )

    seasons[pid] = SeasonState(
        season=sdata["season"], round_idx=sdata["round_idx"],
        round_name=sdata["round_name"], team_rank=sdata["team_rank"],
        team_points=sdata["team_points"], team_games=sdata["team_games"],
        atmosphere=sdata.get("atmosphere", "平淡"),
    )

    dialogues[pid] = [DialogueEntry(**d) for d in data.get("dialogues", [])]
    career_log[pid] = data.get("career_log", [])
    season_event_log[pid] = data.get("season_event_log", [])
    event_queue[pid] = data.get("event_queue", [])
    completed_events[pid] = data.get("completed_events", [])
    pending_effects[pid] = data.get("pending_effects", {})
    used_categories[pid] = data.get("used_categories", [])
    current_news[pid] = data.get("current_news", [])
    talk_history[pid] = data.get("talk_history", [])
    pending_talk_effects[pid] = data.get("pending_talk_effects", {})
    pts = data.get("pending_transfers", [])
    if pts:
        pending_transfers[pid] = list(pts)
    return pid


def list_saves() -> list[dict]:
    """返回所有存档摘要列表"""
    idx = _os.path.join(SAVES_DIR, "index.json")
    if not _os.path.isfile(idx):
        return []
    try:
        with open(idx, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (_json.JSONDecodeError, IOError):
        return []


def delete_save(save_id):
    """删除存档文件和内存数据"""
    dst = _os.path.join(SAVES_DIR, f"{save_id}.json")
    if _os.path.isfile(dst):
        _os.remove(dst)
    # 如果有对应的 .tmp 也删掉
    tmp = _os.path.join(SAVES_DIR, f"{save_id}.tmp")
    if _os.path.isfile(tmp):
        _os.remove(tmp)
    # 删索引
    idx_path = _os.path.join(SAVES_DIR, "index.json")
    entries = []
    if _os.path.isfile(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                entries = _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    entries = [e for e in entries if e.get("save_id") != save_id]
    with open(idx_path, "w", encoding="utf-8") as f:
        _json.dump(entries, f, ensure_ascii=False, indent=2)


def _update_save_index(save_id, data):
    """更新存档索引 index.json"""
    idx_path = _os.path.join(SAVES_DIR, "index.json")
    entries = []
    if _os.path.isfile(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                entries = _json.load(f)
        except (_json.JSONDecodeError, IOError):
            entries = []

    p = data["player"]
    s = data["season"]
    entry = {
        "save_id": save_id,
        "player_id": p["id"],
        "slot_name": data.get("slot_name", "自动存档"),
        "name": p["name"],
        "position": p["position"],
        "team_name": p["team_name"],
        "season": s["season"],
        "round_name": s["round_name"],
        "updated_at": data["updated_at"],
    }

    found = False
    for i, e in enumerate(entries):
        if e.get("save_id") == save_id:
            entries[i] = entry
            found = True
            break
    if not found:
        entries.append(entry)

    with open(idx_path, "w", encoding="utf-8") as f:
        _json.dump(entries, f, ensure_ascii=False, indent=2)
