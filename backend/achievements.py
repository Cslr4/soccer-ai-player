"""成就系统 —— 定义 + 检测 + 存储"""

from __future__ import annotations

ACHIEVEMENTS = [
    # ============ 里程碑 ============
    {"id": "debut",       "name": "职业首秀",     "desc": "完成第一个赛季",       "icon": "👶", "cat": "里程碑"},
    {"id": "goal_1",      "name": "处子之球",     "desc": "打进生涯首球",         "icon": "⚽", "cat": "里程碑"},
    {"id": "goal_50",     "name": "半百射手",     "desc": "生涯打进 50 球",      "icon": "🎯", "cat": "里程碑"},
    {"id": "goal_100",    "name": "百球射手",     "desc": "生涯打进 100 球",     "icon": "💯", "cat": "里程碑"},
    {"id": "assist_50",   "name": "助攻大师",     "desc": "生涯助攻 50 次",      "icon": "🎁", "cat": "里程碑"},
    {"id": "assist_100",  "name": "百助之王",     "desc": "生涯助攻 100 次",     "icon": "👑", "cat": "里程碑"},
    {"id": "season_5",    "name": "五年之约",     "desc": "完成 5 个赛季",       "icon": "📅", "cat": "里程碑"},
    {"id": "season_10",   "name": "十年一梦",     "desc": "完成 10 个赛季",      "icon": "⏳", "cat": "里程碑"},
    {"id": "hat_trick",   "name": "帽子戏法",     "desc": "单赛季进球 30+",      "icon": "🎩", "cat": "里程碑"},
    {"id": "hat_trick_3", "name": "帽子戏法收藏家","desc": "累计 3 次赛季进球 30+","icon": "🏅", "cat": "里程碑"},
    {"id": "four_goal",   "name": "四喜临门",     "desc": "单赛季进球 40+",      "icon": "🔥", "cat": "里程碑"},
    {"id": "streak_30",   "name": "连续30球",     "desc": "连续 2 赛季进球 30+", "icon": "⚡", "cat": "里程碑"},
    {"id": "triple_double","name":"两双赛季",     "desc": "单赛季进球助攻均 15+","icon": "🔢", "cat": "里程碑"},

    # ============ 荣誉 ============
    {"id": "league_win",  "name": "联赛冠军",     "desc": "赢得联赛冠军",         "icon": "🏆", "cat": "荣誉"},
    {"id": "ucl_win",     "name": "欧洲之王",     "desc": "赢得欧冠冠军",         "icon": "🌟", "cat": "荣誉"},
    {"id": "cup_win",     "name": "杯赛之王",     "desc": "赢得国内杯赛冠军",     "icon": "🥤", "cat": "荣誉"},
    {"id": "euro_win",    "name": "欧战称雄",     "desc": "赢得欧联/欧协冠军",    "icon": "🏅", "cat": "荣誉"},
    {"id": "double",      "name": "双冠王",       "desc": "单赛季联赛+杯赛双冠",  "icon": "🎊", "cat": "荣誉"},
    {"id": "grand_slam",  "name": "全满贯",       "desc": "集齐联赛+欧冠+金靴",   "icon": "👑", "cat": "荣誉"},
    {"id": "golden_boot", "name": "金靴奖",       "desc": "获得联赛金靴",         "icon": "👟", "cat": "荣誉"},
    {"id": "euro_boot",   "name": "欧洲金靴",     "desc": "获得欧洲金靴奖",       "icon": "💎", "cat": "荣誉"},
    {"id": "assist_king", "name": "助攻王",       "desc": "获得联赛助攻王",       "icon": "🅰", "cat": "荣誉"},
    {"id": "poty",        "name": "赛季最佳球员", "desc": "获得赛季最佳球员",     "icon": "💫", "cat": "荣誉"},
    {"id": "young_poty",  "name": "金童奖提名",   "desc": "获得最佳年轻球员提名", "icon": "🌟", "cat": "荣誉"},

    # ============ 事件 ============
    {"id": "first_transfer","name":"新篇章",      "desc": "完成第一次转会",       "icon": "✈️", "cat": "事件"},
    {"id": "big_transfer",  "name":"豪门之路",    "desc": "转会加盟豪门球队",     "icon": "💰", "cat": "事件"},
    {"id": "pos_change",    "name":"位置改造",    "desc": "改变场上位置",         "icon": "🔄", "cat": "事件"},
    {"id": "comeback",      "name":"浴火重生",    "desc": "重伤后复出并完成赛季", "icon": "🔥", "cat": "事件"},
    {"id": "atmos_turn",    "name":"力挽狂澜",    "desc": "队内氛围从内讧变融洽以上","icon":"🌈", "cat": "事件"},
    {"id": "media_darling", "name":"媒体宠儿",    "desc": "公众口碑达到 90",     "icon": "📸", "cat": "事件"},
    {"id": "injury_free",   "name":"钢铁之躯",    "desc": "连续 3 赛季无重伤",   "icon": "🛡", "cat": "事件"},

    # ============ 巅峰 ============
    {"id": "attr_90",     "name": "单项精英",     "desc": "任意属性达到 90",     "icon": "📈", "cat": "巅峰"},
    {"id": "attr_95",     "name": "世界级",       "desc": "任意属性达到 95",     "icon": "🔝", "cat": "巅峰"},
    {"id": "hard_850",    "name": "全能战士",     "desc": "硬实力总和达到 850",  "icon": "💪", "cat": "巅峰"},
    {"id": "all_hard_70", "name": "万金油",       "desc": "所有硬实力达到 70",   "icon": "🎨", "cat": "巅峰"},
    {"id": "iron_will",   "name": "钢铁意志",     "desc": "意志+抗压+勇敢≥270","icon": "🧠", "cat": "巅峰"},
    {"id": "speed_demon", "name": "速度狂魔",     "desc": "速度+体力达到 190",   "icon": "⚡", "cat": "巅峰"},
    {"id": "playmaker",   "name": "中场大脑",     "desc": "传球+技术+才华≥270","icon": "🎭", "cat": "巅峰"},

    # ============ 更衣室 ============
    {"id": "core_leader",  "name": "核心领袖",     "desc": "达到核心领袖地位",     "icon": "⭐", "cat": "更衣室"},
    {"id": "legend_status","name": "传奇",         "desc": "达到传奇地位",         "icon": "👑", "cat": "更衣室"},
    {"id": "rise_up",      "name": "草根逆袭",     "desc": "从边缘人物升至核心以上","icon":"🚀", "cat": "更衣室"},
    {"id": "captain",      "name": "队长",         "desc": "连续 3 赛季保持核心以上","icon":"🫡", "cat": "更衣室"},
    {"id": "outcast",      "name": "被遗忘的人",   "desc": "沦为边缘人物",         "icon": "👤", "cat": "更衣室"},
    {"id": "self_destruct","name": "自毁前程",     "desc": "球队氛围跌至内讧",     "icon": "💥", "cat": "更衣室"},

    # ============ 合同 ============
    {"id": "top_wage",     "name": "顶薪球员",     "desc": "拿到顶薪合同",         "icon": "💰", "cat": "合同"},
    {"id": "top_earner",   "name": "打工皇帝",     "desc": "周薪超过 60 万",      "icon": "💸", "cat": "合同"},
    {"id": "big_release",  "name": "天价解约金",   "desc": "解约金超过 5000 万",   "icon": "💎", "cat": "合同"},
    {"id": "big_boss",     "name": "亿元先生",     "desc": "解约金超过 1 亿",      "icon": "💎", "cat": "合同"},
    {"id": "contract_year","name": "合同年",       "desc": "进入合同最后一年",     "icon": "⏰", "cat": "合同"},
    {"id": "free_agent",   "name": "自由之身",     "desc": "合同到期成为自由球员", "icon": "🆓", "cat": "合同"},
    {"id": "long_deal",    "name": "长约锁定",     "desc": "签下 5 年长约",        "icon": "🔒", "cat": "合同"},
    {"id": "child_labor",  "name": "童工合同",     "desc": "以童工工资开始职业生涯","icon":"🍼", "cat": "合同"},
    {"id": "old_deal",     "name": "养老合同",     "desc": "33 岁后签下新合同",    "icon": "👴", "cat": "合同"},
    {"id": "underpaid",    "name": "低薪高能",     "desc": "底薪以下却赛季进球 20+","icon":"📉", "cat": "合同"},
    {"id": "negotiator",   "name": "谈判高手",     "desc": "通过谈判将周薪提升 30%","icon":"🤝", "cat": "合同"},
    {"id": "one_shot_deal","name": "一击即中",     "desc": "第一轮谈判就被接受",   "icon": "🎯", "cat": "合同"},
    {"id": "deal_breaker", "name": "谈崩了",       "desc": "谈判失败报价被撤回",   "icon": "🚫", "cat": "合同"},
    {"id": "actuary",      "name": "精算师",       "desc": "生涯累计谈判成功 5 次", "icon":"🏦", "cat": "合同"},

    # ============ 转会 ============
    {"id": "one_club",    "name": "忠贞不渝",     "desc": "连续 10 赛季不转会",   "icon": "🏠", "cat": "转会"},
    {"id": "loyal",        "name": "忠臣",         "desc": "连续 5 赛季不转会",    "icon": "🏠", "cat": "转会"},
    {"id": "big_move",     "name": "豪门跳板",     "desc": "从弱旅/下游转会至豪门","icon":"✈️", "cat": "转会"},
    {"id": "mercenary",    "name": "浪子",         "desc": "生涯转会 3 次以上",    "icon": "💼", "cat": "转会"},
    {"id": "homecoming",   "name": "落叶归根",     "desc": "回到之前效力过的球队", "icon": "🍂", "cat": "转会"},

    # ============ 特点 ============
    {"id": "double_trait",  "name":"双面手",      "desc": "创建角色时选 2 个特点","icon":"🃏", "cat": "特点"},
    {"id": "four_trait",    "name":"四面手",      "desc": "创建角色时选 4 个特点","icon":"🃏", "cat": "特点"},
    {"id": "negative_trait","name":"天生缺陷",    "desc": "创建时选择负面特点",   "icon": "💀", "cat": "特点"},
    {"id": "pos_2_neg_2",   "name":"双面人生",    "desc": "选 2 正面 + 2 负面",    "icon":"🎭", "cat": "特点"},
    {"id": "rebirth",       "name":"涅槃重生",    "desc": "有玻璃人，连续 3 赛季无重伤","icon":"🔥", "cat": "特点"},
    {"id": "redemption",    "name":"浪子回头",    "desc": "有刺头/独狼，团队精神达 70","icon":"🤝", "cat": "特点"},
    {"id": "silent_gold",   "name":"沉默是金",    "desc": "有争议人物，公众口碑达 80","icon":"🤫", "cat": "特点"},
    {"id": "gamble_goal",   "name":"一发赌中",    "desc": "有神经刀，单赛季进球 25+","icon":"🎲", "cat": "特点"},
    {"id": "iron_body",     "name":"钢筋铁骨",    "desc": "有玻璃人，伤病抗性达 60","icon":"🛡", "cat": "特点"},
    {"id": "calm_down",     "name":"冷静下来",    "desc": "有神经刀，情绪控制达 70","icon":"🧊", "cat": "特点"},
]

# 内存存储: player_id -> {ach_id: {unlocked_at_season, unlocked_at_round}}
_unlocked: dict[str, dict] = {}


def get_unlocked(pid):
    return _unlocked.setdefault(pid, {})


def check_and_award(pid, player=None, season=None):
    """检测并授予新成就，返回新解锁列表 [{id, name, icon, desc, cat}]"""
    from game_state import players, seasons, get_career, get_season_events
    from config import HARD_ATTRS, SOFT_ATTRS
    import random as _random

    p = player or players.get(pid)
    s = season or seasons.get(pid)
    if not p or not s:
        return []

    career = list(get_career(pid))
    unlocked = get_unlocked(pid)
    new_awards = []

    def award(aid):
        if aid not in unlocked:
            unlocked[aid] = {"season": s.season, "round": s.round_name}
            new_awards.append(aid)

    attrs = p.attrs.model_dump()
    total_goals = sum(r.get("goals", 0) for r in career)
    total_apps = sum(r.get("appearances", 0) for r in career)
    total_assists = sum(r.get("assists", 0) for r in career)
    num_seasons = len(career) + 1  # current season not yet in career
    all_honors = []
    for r in career:
        all_honors.extend(r.get("honors", []))
    season_honors = career[-1].get("honors", []) if career else []
    clubs = set(r.get("club", "") for r in career)
    clubs.add(p.team_name)
    hard_sum = sum(attrs.get(a, 0) for a in HARD_ATTRS)
    will = attrs.get("意志力", 0) + attrs.get("抗压能力", 0) + attrs.get("勇敢", 0)
    speed_stamina = attrs.get("速度", 0) + attrs.get("体力", 0)
    creativity = attrs.get("传球", 0) + attrs.get("技术", 0) + attrs.get("才华", 0)

    # ---- 里程碑 ----
    if num_seasons >= 2: award("debut")
    if total_goals >= 1: award("goal_1")
    if total_goals >= 50: award("goal_50")
    if total_goals >= 100: award("goal_100")
    if total_assists >= 50: award("assist_50")
    if total_assists >= 100: award("assist_100")
    if num_seasons >= 5: award("season_5")
    if num_seasons >= 10: award("season_10")
    if len(clubs) == 1 and num_seasons >= 10: award("one_club")
    if career and career[-1].get("goals", 0) >= 30: award("hat_trick")

    # ---- 荣誉 ----
    if any("联赛冠军" in h for h in all_honors): award("league_win")
    if any("欧冠冠军" in h for h in all_honors): award("ucl_win")
    if any("杯赛冠军" in h for h in all_honors): award("cup_win")
    if any("欧战冠军" in h for h in all_honors): award("euro_win")
    if any("金靴" in h for h in all_honors): award("golden_boot")
    if any("欧洲金靴" in h for h in all_honors): award("euro_boot")
    if any("助攻王" in h for h in all_honors): award("assist_king")
    if any("赛季最佳球员" in h for h in all_honors): award("poty")
    if any("最佳年轻球员" in h for h in all_honors): award("young_poty")
    if any("联赛冠军" in h for h in all_honors) and any("欧冠冠军" in h for h in all_honors) and (any("金靴" in h for h in all_honors) or any("欧洲金靴" in h for h in all_honors)): award("grand_slam")
    if any("联赛冠军" in h for h in season_honors) and any("杯赛冠军" in h for h in season_honors): award("double")

    # ---- 事件 ----
    if len(clubs) >= 2: award("first_transfer")
    if p.team_tier == "豪门" and len([c for c in clubs]) >= 2: award("big_transfer")
    # Position change: detect by checking if any season highlight mentions position
    season_events = get_season_events(pid)
    pos_keywords = ["位置", "改造", "新位置", "改打"]
    if any(any(kw in evt for kw in pos_keywords) for evt in season_events):
        award("pos_change")
    # Comeback: heavy injury → recovery
    has_heavy = any("重伤缺阵" in evt for evt in season_events)
    has_recovery = any(("复出" in evt or "康复" in evt) for evt in season_events)
    if has_heavy and has_recovery: award("comeback")
    if s.atmosphere in ("融洽", "鼎盛"):
        # Check if past atmosphere was bad
        # Simplified: check career log for low points
        pass  # atmos_turn needs more tracking, skip for now
    if attrs.get("公众口碑", 0) >= 90: award("media_darling")
    # Injury free: check last 3 seasons
    if num_seasons >= 3:
        recent = career[-3:]
        heavy_injuries = sum(1 for r in recent if any("重伤" in h for h in r.get("highlights", [])))
        if heavy_injuries == 0: award("injury_free")

    # ---- 巅峰 ----
    if any(v >= 90 for v in attrs.values()): award("attr_90")
    if any(v >= 95 for v in attrs.values()): award("attr_95")
    if hard_sum >= 850: award("hard_850")
    if all(attrs.get(a, 0) >= 70 for a in HARD_ATTRS): award("all_hard_70")
    if will >= 270: award("iron_will")
    if speed_stamina >= 190: award("speed_demon")
    if creativity >= 270: award("playmaker")

    # ---- 特点 ----
    if p.trait_count >= 2: award("double_trait")

    # ---- 更衣室 ----
    if p.locker_status in ("核心领袖", "传奇"): award("core_leader")
    if p.locker_status == "传奇": award("legend_status")
    # 边缘逆袭：检查过去是否曾是边缘人物
    if p.locker_status in ("核心领袖", "传奇"):
        for r in career:
            if any("边缘" in h for h in r.get("highlights", [])):
                award("rise_up")
                break

    # ---- 合同 ----
    wl = __import__("game_state")._get_wage_level(p)
    if wl == "顶薪": award("top_wage")
    if p.release_clause >= 5000: award("big_release")
    if p.seasons_left == 1: award("contract_year")
    if p.seasons_left == 0: award("free_agent")
    if p.seasons_left >= 5: award("long_deal")
    if wl == "童工": award("child_labor")
    if p.age >= 33 and p.seasons_left >= 2: award("old_deal")
    if wl in ("童工", "底薪") and career and career[-1].get("goals", 0) >= 20: award("underpaid")

    # ---- 转会 ----
    if p.team_tier == "豪门":
        old_tiers = [r.get("club_tier", "") for r in career if r.get("club") != p.team_name]
        if any(t in ("弱旅", "下游") for t in old_tiers):
            award("big_move")
    if len(set(r.get("club", "") for r in career)) >= 3: award("mercenary")
    # 忠臣：连续5赛季不转会
    if len(career) >= 5:
        last_clubs = [r.get("club", "") for r in career[-5:]]
        if len(set(last_clubs)) == 1 and p.team_name == last_clubs[0]:
            award("loyal")
    # 落叶归根：回到之前效力过的球队（非当前球队出现过2次以上）
    all_clubs = [r.get("club", "") for r in career]
    # 落叶归根：必须离队后回归（中间有别的队）
    all_clubs_seq = [r.get("club", "") for r in career]
    unique_stints = []
    for c in all_clubs_seq:
        if not unique_stints or unique_stints[-1] != c:
            unique_stints.append(c)
    if len(unique_stints) >= 3 and unique_stints[0] == unique_stints[-1] and unique_stints.count(p.team_name) >= 2:
        award("homecoming")

    # ---- 更多更衣室 ----
    # 队长：检查生涯中连续3赛季核心以上
    core_count = 0
    for r in career:
        # approximate: check if any highlight mentions improved status
        pass  # captain check is complex, skip for now
    if p.locker_status == "边缘人物": award("outcast")

    # ---- 更多里程碑 ----
    if len(career) >= 2 and career[-1].get("goals", 0) >= 30 and career[-2].get("goals", 0) >= 30:
        award("streak_30")
    if career and career[-1].get("goals", 0) >= 15 and career[-1].get("assists", 0) >= 15:
        award("triple_double")

    # ---- 检测队内氛围改善 ----
    if s.atmosphere in ("融洽", "鼎盛"):
        # 查看生涯中是否经历过内讧/涣散
        for r in career:
            for h in r.get("highlights", []):
                if "内讧" in h or "涣散" in h:
                    award("atmos_turn")
                    break

    # 构建返回
    result = []
    aid_map = {a["id"]: a for a in ACHIEVEMENTS}
    for aid in new_awards:
        a = aid_map.get(aid, {})
        result.append({
            "id": aid, "name": a.get("name", aid),
            "icon": a.get("icon", ""), "desc": a.get("desc", ""),
            "cat": a.get("cat", ""),
        })
    return result


def get_all_with_status(pid):
    """返回全部成就 + 已解锁状态"""
    unlocked = get_unlocked(pid)
    result = []
    for a in ACHIEVEMENTS:
        u = unlocked.get(a["id"])
        result.append({
            **a,
            "unlocked": u is not None,
            "season": u["season"] if u else None,
            "round": u["round"] if u else None,
        })
    return result
