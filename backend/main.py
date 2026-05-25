"""
命运绿茵 - 球员生涯模拟
运行: python main.py  然后打开 http://127.0.0.1:8000
"""

import os
import json
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import POSITIONS, ALL_ATTRS, ROUNDS
from models import CreatePlayerReq, AdjustAttrReq, FreeTalkReq, EventChoiceReq, DialogueEntry
from pydantic import BaseModel
from game_state import (
    players, seasons, dialogues,
    get_dialogues,
    get_event_queue, enqueue_event, pop_next_event, clear_event_queue,
    get_completed, add_completed, clear_completed,
    get_effects, clear_effects,
    get_used_cats, add_used_cat, clear_used_cats,
    create_player, adjust_attributes, apply_effects, advance_round, settlement_prep,
    generate_attrs_fallback,
    get_career,
    save_game, create_named_save, load_game, list_saves, delete_save,
    pending_transfers, get_pending_transfers, add_season_event,
    roll_settlement_buff, player_buffs, season_growth_changes,
    get_current_news, set_current_news,
    get_talk_history, add_talk_history, resolve_talk_effects,
    add_talk_effect, clear_talk_effects,
    renew_contract, _get_wage_level,
)
from ai_engine import (
    create_player_ai, round_start, generate_single_event,
    free_talk as ai_free_talk, resolve_event as ai_resolve_event,
    settle as ai_settle,
    free_talk_stream, resolve_event_stream,
    expand_news,
    negotiate_contract_dialogue,
    close_client,
)
from achievements import check_and_award, get_all_with_status

import sys

if getattr(sys, 'frozen', False):
    FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
else:
    FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.getcwd(), "frontend")

app = FastAPI(title="命运绿茵")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


def _need(pid):
    if pid not in players:
        raise HTTPException(404, "角色不存在")


def _state(pid):
    p = players[pid]
    s = seasons[pid]
    q = get_event_queue(pid)
    done = len(get_completed(pid))
    cur = q[0] if q else None
    return {
        "player": p.model_dump(),
        "season": s.model_dump(),
        "events_in_queue": len(q),
        "events_completed": done,
        "current_event": cur,
        "can_settle": done > 0,
        "can_get_event": done < 4 and len(q) == 0,
        "news": get_current_news(pid),
        "buff": player_buffs.get(pid, ""),
    }


# ============================================================
# 创建角色（AI 根据球队名判断等级）
# ============================================================
@app.post("/api/player/create")
async def api_create(req: CreatePlayerReq):
    if req.position not in POSITIONS:
        raise HTTPException(400, f"位置: {'/'.join(POSITIONS)}")
    if not (17 <= req.age <= 35):
        raise HTTPException(400, "年龄 17-35")
    if not (160 <= req.height <= 210):
        raise HTTPException(400, "身高 160-210cm")
    if not (50 <= req.weight <= 120):
        raise HTTPException(400, "体重 50-120kg")

    # 特点验证：最多4个，最多2个正面，不可重复
    from config import TRAITS
    if len(req.traits) > 4:
        raise HTTPException(400, "最多选择4个特点")
    if len(set(req.traits)) != len(req.traits):
        raise HTTPException(400, "特点不可重复")
    pos_count = sum(1 for t in req.traits if t in TRAITS and TRAITS[t].get("type") == "positive")
    neg_count = sum(1 for t in req.traits if t in TRAITS and TRAITS[t].get("type") == "negative")
    if pos_count > 2:
        raise HTTPException(400, "正面特点最多2个")
    for t in req.traits:
        if t not in TRAITS:
            raise HTTPException(400, f"未知特点: {t}")

    result = await create_player_ai(req.name, req.team_name, req.nationality, req.position, req.age, req.height, req.weight, req.traits)
    p = create_player(req.name, result["team_tier"], result.get("league_level","中游"), result["team_name"],
                      req.nationality, req.position, req.age, req.height, req.weight, result["attrs"], req.traits)
    save_game(p.id)
    if len(req.traits) >= 2: check_and_award(p.id)
    return {"player": p.model_dump(), "message": "角色创建成功"}


@app.post("/api/player/create_fallback")
async def api_create_fallback(req: CreatePlayerReq):
    if req.position not in POSITIONS:
        raise HTTPException(400, f"位置: {'/'.join(POSITIONS)}")
    if not (17 <= req.age <= 35):
        raise HTTPException(400, "年龄 17-35")
    if not (160 <= req.height <= 210):
        raise HTTPException(400, "身高 160-210cm")
    if not (50 <= req.weight <= 120):
        raise HTTPException(400, "体重 50-120kg")
    # 特点验证
    from config import TRAITS
    if len(req.traits) > 4:
        raise HTTPException(400, "最多选择4个特点")
    pos_count = sum(1 for t in req.traits if t in TRAITS and TRAITS[t].get("type") == "positive")
    if pos_count > 2:
        raise HTTPException(400, "正面特点最多2个")

    # 离线模式：简单关键字匹配
    elite_kw = ["曼城","皇马","巴萨","拜仁","巴黎","利物浦","阿森纳","切尔西","曼联","尤文","国米"]
    strong_kw = ["多特","马竞","那不勒斯","热刺","纽卡","维拉","AC米兰","勒沃库森","罗马","拉齐奥"]
    mid_kw = ["塞维利亚","布莱顿","西汉姆","马赛","里昂","摩纳哥","水晶宫","富勒姆","狼队","埃弗顿"]
    lower_kw = ["南安普顿","诺丁汉","伯恩利","谢菲联","卢顿","加的斯","热那亚","恩波利","奥格斯堡"]
    t = req.team_name
    if any(k in t for k in elite_kw): tier = "豪门"; league_level = "争冠"
    elif any(k in t for k in strong_kw): tier = "劲旅"; league_level = "上游"
    elif any(k in t for k in mid_kw): tier = "中游"; league_level = "中游"
    elif any(k in t for k in lower_kw): tier = "下游"; league_level = "下游"
    else: tier = "弱旅"; league_level = "保级"
    attrs = generate_attrs_fallback(tier, req.position)
    p = create_player(req.name, tier, league_level, req.team_name, req.nationality, req.position,
                      req.age, req.height, req.weight, attrs.model_dump(), req.traits)
    save_game(p.id)
    if len(req.traits) >= 2: check_and_award(p.id)
    return {"player": p.model_dump(), "message": "角色创建成功（离线模式）"}


# ============================================================
# 调整属性
# ============================================================
@app.post("/api/player/{pid}/adjust")
async def api_adjust(pid: str, req: AdjustAttrReq):
    _need(pid)
    p = adjust_attributes(pid, req.adjustments)
    save_game(pid)
    return {"player": p.model_dump()}


# ============================================================
# 状态
# ============================================================
@app.get("/api/game/{pid}/state")
async def api_state(pid: str):
    _need(pid)
    return _state(pid)


@app.get("/api/game/{pid}/career")
async def api_career(pid: str):
    _need(pid)
    p = players[pid]
    records = get_career(pid)
    return {
        "player_name": p.name,
        "position": p.position,
        "career": records,
    }


@app.get("/api/game/{pid}/achievements")
async def api_achievements(pid: str):
    _need(pid)
    return {"achievements": get_all_with_status(pid)}


@app.post("/api/game/{pid}/news/expand")
async def api_expand_news(pid: str, req: FreeTalkReq):
    _need(pid)
    p = players[pid]; s = seasons[pid]
    detail = await expand_news(p, s, req.content)
    return {"detail": detail}


# ============================================================
# 回合开始（只生成新闻）
# ============================================================
@app.post("/api/game/{pid}/round_start")
async def api_round_start(pid: str):
    _need(pid)
    p = players[pid]
    s = seasons[pid]
    result = await round_start(p, s)
    clear_event_queue(pid)
    clear_completed(pid)
    clear_effects(pid)
    clear_used_cats(pid)
    set_current_news(pid, result.get("news", []))
    save_game(pid)
    return {
        "round_name": s.round_name,
        "season": s.season,
        "news": result["news"],
        "round_intro": result["round_intro"],
    }


# ============================================================
# 获取下一个事件（每次一个）
# ============================================================
@app.post("/api/game/{pid}/next_event")
async def api_next_event(pid: str):
    _need(pid)
    p = players[pid]
    s = seasons[pid]
    used = get_used_cats(pid)

    if len(get_completed(pid)) >= 4:
        raise HTTPException(400, "本回合事件已达上限（4个），请结算")

    evt = await generate_single_event(p, s, used)
    enqueue_event(pid, evt)
    save_game(pid)
    return {"event": evt, "events_done": len(get_completed(pid)), "events_total": 4}


# ============================================================
# 自由对话
# ============================================================
@app.post("/api/game/{pid}/free_talk")
async def api_free_talk(pid: str, req: FreeTalkReq):
    _need(pid)
    p = players[pid]
    s = seasons[pid]
    dl = get_dialogues(pid)
    history = [{"role": d.role, "content": d.content} for d in dl]
    result = await ai_free_talk(p, s, req.content, history, req.target)

    # 定向效果：暂存，回合结算时清算
    talk_effs = resolve_talk_effects(req.target)
    add_talk_effect(pid, talk_effs)
    if result.get("effects"):
        apply_effects(pid, result["effects"])

    # 存储对话历史
    add_talk_history(pid, req.target, req.content, s.season, s.round_name)

    dl.append(DialogueEntry(role="user", content=f"【{req.target}】{req.content}", stage="free_talk"))
    dl.append(DialogueEntry(role="assistant", content=result["narrative"], stage="free_talk"))
    save_game(pid)
    return {"narrative": result["narrative"]}


@app.post("/api/game/{pid}/free_talk/stream")
async def api_free_talk_stream(pid: str, req: FreeTalkReq):
    """流式自由对话 —— SSE 推送，叙事逐字出现"""
    _need(pid)
    p = players[pid]
    s = seasons[pid]
    dl = get_dialogues(pid)
    history = [{"role": d.role, "content": d.content} for d in dl]

    from fastapi.responses import StreamingResponse

    async def generate():
        narrative_acc = ""
        async for typ, data in free_talk_stream(p, s, req.content, history, req.target):
            if typ == "chunk":
                narrative_acc += data
                yield f"data: {json.dumps({'type': 'chunk', 'content': data})}\n\n"
            elif typ == "done":
                # 定向效果：暂存，回合结算时清算
                talk_effs = resolve_talk_effects(req.target)
                add_talk_effect(pid, talk_effs)
                if data.get("effects"):
                    apply_effects(pid, data["effects"])
                # 存储历史
                add_talk_history(pid, req.target, req.content, s.season, s.round_name)
                dl.append(DialogueEntry(role="user", content=f"【{req.target}】{req.content}", stage="free_talk"))
                dl.append(DialogueEntry(role="assistant", content=data["narrative"], stage="free_talk"))
                save_game(pid)
                yield f"data: {json.dumps({'type': 'done', 'narrative': data['narrative'], 'effects': data.get('effects', {})})}\n\n"
            elif typ == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============================================================
# 事件选择
# ============================================================
@app.post("/api/game/{pid}/event_choice")
async def api_event_choice(pid: str, req: EventChoiceReq):
    _need(pid)
    p = players[pid]
    s = seasons[pid]

    # 从队列头取事件
    evt = pop_next_event(pid)
    if evt is None:
        raise HTTPException(400, "没有待处理的事件，请先获取下一个事件")

    result = await ai_resolve_event(p, s, evt, req.option_id, req.custom_text)

    # 处理位置变更和氛围变更
    effects = dict(result.get("effects", {}))
    new_pos = effects.pop("_new_position", None)
    new_atm = effects.pop("_atmosphere", None)
    new_team = effects.pop("_new_team", None)
    new_tier = effects.pop("_new_team_tier", None)
    new_league = effects.pop("_new_league_level", None)
    if new_pos and new_pos in POSITIONS:
        p.position = new_pos
    if new_atm in ("内讧","涣散","平淡","融洽","鼎盛"):
        s.atmosphere = new_atm
    if new_team:
        from config import WAGE_TABLE
        import uuid as _uuid
        # 优先缓存，未命中则用AI判断并缓存
        if info:
            new_tier = info["tier"]; new_league = info["league_level"]
        else:
            # AI首次判断此队，缓存起来
            new_tier = new_tier or "中游"; new_league = new_league or "中游"
        wage_lo, wage_hi = WAGE_TABLE.get(new_tier, (1, 10))
        base = p.weekly_wage * random.uniform(1.15, 1.50)
        tier_order = {"弱旅":0,"下游":1,"中游":2,"劲旅":3,"豪门":4}
        tier_diff = tier_order.get(new_tier,2) - tier_order.get(p.team_tier,2)
        if tier_diff >= 3: base *= random.uniform(1.3, 1.6)
        elif tier_diff >= 2: base *= random.uniform(1.1, 1.3)
        offer_wage = round(max(wage_lo, min(wage_hi, base)), 1)
        offer_years = random.randint(2, 5)
        offer_clause = round(offer_wage * 52 * (random.choice([3, 5, 8]) if random.random() < 0.3 else 0))
        target_rank = random.randint(1, 18)
        target_atm = random.choice(["融洽","平淡","涣散"])
        existing = get_pending_transfers(pid)
        existing.clear()
        offer = {
            "id": _uuid.uuid4().hex[:6],
            "team": new_team, "tier": new_tier, "league": new_league,
            "years": offer_years, "wage": offer_wage, "clause": offer_clause,
            "target_rank": target_rank, "target_atm": target_atm,
            "neg_history": [], "neg_round": 1, "status": "pending",
        }
        existing.append(offer)
        print(f"[转会报价] {p.name} ← {new_team} ({new_tier}, {offer_years}年 周薪{offer_wage}万)")
    elif evt.get("category") == "转会传闻":
        print(f"[转会] 事件为转会传闻但 _new_team 缺失，玩家选: {req.option_id}，effects: {effects}")
    players[pid] = p
    seasons[pid] = s

    apply_effects(pid, effects, result.get("temp_status", "无"))

    cat = evt.get("category", "未知")
    add_used_cat(pid, cat)
    opt = req.option_id if req.option_id != "custom" else f"自定义: {req.custom_text[:30]}"
    add_completed(pid, f"[{cat}] {evt.get('title','')} → {opt}")

    save_game(pid)
    new_achs = check_and_award(pid)
    offers = get_pending_transfers(pid)
    return {
        "narrative": result["narrative"],
        "category": cat,
        "new_position": new_pos,
        "transfer_offers": offers,
        "events_done": len(get_completed(pid)),
        "events_total": 4,
        "new_achievements": new_achs, "growth_changes": season_growth_changes.pop(pid, {}),
    }


# ---- 转会确认/拒绝 ----
@app.post("/api/game/{pid}/transfer/accept")
async def api_accept_transfer(pid: str, req: FreeTalkReq = None):
    _need(pid)
    offers = get_pending_transfers(pid)
    if not offers:
        raise HTTPException(400, "没有待确认的报价")
    idx = int(req.content) if req and req.content else 0
    if idx >= len(offers):
        idx = 0
    offer = offers[idx]
    pending_transfers[pid] = []  # 签约后清空所有报价
    p = players[pid]
    is_renew = offer.get("is_renewal", False)
    # 签约声望效果：大合同=高声望
    new_w = offer.get("wage", p.weekly_wage)
    old_w = p.weekly_wage
    ratio = new_w / max(1, old_w)
    if new_w >= 50:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(4, 7))
    elif new_w >= 30:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(3, 5))
    elif new_w >= 15:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(2, 4))
    elif ratio >= 2.0:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(2, 4))
    elif ratio >= 1.5:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(1, 3))
    elif ratio >= 1.2:
        p.attrs.声望 = min(99, p.attrs.声望 + random.randint(1, 2))
    p.team_name = offer["team"]
    p.team_tier = offer["tier"]
    p.league_level = offer["league"]
    p.seasons_left = offer["years"]
    p.weekly_wage = offer["wage"]
    p.release_clause = offer["clause"]
    p.last_transfer_season = seasons[pid].season
    players[pid] = p
    msg = f"与{offer['team']}续约" if is_renew else f"转会至{offer['team']}({offer['tier']})"
    add_season_event(pid, f"{msg}，签{offer['years']}年合同")
    save_game(pid)
    print(f"[{'续约' if is_renew else '转会'}确认] {p.name} {'←' if is_renew else '→'} {offer['team']}")
    return {"message": f"{'续约' if is_renew else '转会'}成功！合同{offer['years']}年 周薪{offer['wage']}万"}

@app.post("/api/game/{pid}/transfer/reject")
async def api_reject_transfer(pid: str, req: FreeTalkReq = None):
    _need(pid)
    offers = get_pending_transfers(pid)
    idx = int(req.content) if req and req.content else 0
    if offers and idx < len(offers):
        offers.pop(idx)
    return {"message": "已拒绝报价"}


@app.post("/api/game/{pid}/transfer/negotiate")
async def api_negotiate_transfer(pid: str, req: FreeTalkReq):
    """合同谈判：req.content=玩家发言"""
    _need(pid)
    offers = get_pending_transfers(pid)
    if not offers:
        raise HTTPException(400, "没有待谈判的报价")
    offer = offers[0]
    if offer.get("neg_round", 0) >= 4:
        raise HTTPException(400, "谈判已达最大轮次")
    p = players[pid]; s = seasons[pid]
    result = await negotiate_contract_dialogue(p, s, offer, req.content, offer.get("neg_round", 1))
    # 更新报价
    offer["neg_round"] = offer.get("neg_round", 1) + 1
    if result.get("counter"):
        c = result["counter"]
        if c.get("wage") and float(c["wage"]) >= offer["wage"]:
            offer["wage"] = float(c["wage"])
        if c.get("years"): offer["years"] = int(c["years"])
        if c.get("clause") is not None: offer["clause"] = float(c["clause"])
    # 谈判成果影响声望/口碑
    if result.get("decision") == "accept":
        old_w = offer.get("_orig_wage", offer["wage"])
        new_w = offer.get("wage", old_w)
        ratio = new_w / max(1, old_w)
        p2 = players[pid]
        if ratio >= 2.0:
            p2.attrs.声望 = min(99, p2.attrs.声望 + random.randint(3, 5))
        elif ratio >= 1.5:
            p2.attrs.声望 = min(99, p2.attrs.声望 + random.randint(2, 3))
        elif ratio >= 1.2:
            p2.attrs.声望 = min(99, p2.attrs.声望 + 1)
        elif ratio <= 0.7:
            p2.attrs.公众口碑 = min(99, p2.attrs.公众口碑 + random.randint(2, 4))
            p2.attrs.声望 = max(0, p2.attrs.声望 - 1)
        # 顶薪额外声望
        if new_w >= 50:
            p2.attrs.声望 = min(99, p2.attrs.声望 + random.randint(1, 3))
        players[pid] = p2
    elif result.get("decision") == "reject":
        pending_transfers[pid] = []
        p2 = players[pid]
        p2.attrs.公众口碑 = max(0, p2.attrs.公众口碑 - random.randint(1, 2))
        players[pid] = p2
    # 存原始工资用于比较涨幅
    if "_orig_wage" not in offer:
        offer["_orig_wage"] = offer["wage"]
    save_game(pid)
    return {**result, "offer": offer, "round": offer["neg_round"]}


@app.post("/api/game/{pid}/event_choice/stream")
async def api_event_choice_stream(pid: str, req: EventChoiceReq):
    """流式事件结算 —— SSE 推送，叙事逐字出现"""
    _need(pid)
    p = players[pid]
    s = seasons[pid]

    evt = pop_next_event(pid)
    if evt is None:
        raise HTTPException(400, "没有待处理的事件，请先获取下一个事件")

    from fastapi.responses import StreamingResponse

    async def generate():
        async for typ, data in resolve_event_stream(p, s, evt, req.option_id, req.custom_text):
            if typ == "chunk":
                yield f"data: {json.dumps({'type': 'chunk', 'content': data})}\n\n"
            elif typ == "done":
                effects = dict(data.get("effects", {}))
                new_pos = effects.pop("_new_position", None)
                new_atm = effects.pop("_atmosphere", None)
                new_team = effects.pop("_new_team", None)
                new_tier = effects.pop("_new_team_tier", None)
                new_league = effects.pop("_new_league_level", None)
                if new_pos and new_pos in POSITIONS:
                    p.position = new_pos
                if new_atm in ("内讧", "涣散", "平淡", "融洽", "鼎盛"):
                    s.atmosphere = new_atm
                if new_team and len(new_team.strip()) >= 2 and new_team.strip() not in ("无", "无报价", "未知") and new_team != p.team_name:
                    from config import WAGE_TABLE
                    import uuid as _uuid2
                    new_tier = new_tier or "中游"; new_league = new_league or "中游"
                    # 优先用 AI 在 effects 里的报价，没有则公式生成
                    ai_wage = effects.pop("_offer_wage", None)
                    ai_years = effects.pop("_offer_years", None)
                    if ai_wage and ai_years:
                        offer_wage = float(ai_wage)
                        offer_years = int(ai_years)
                    else:
                        wage_lo, wage_hi = WAGE_TABLE.get(new_tier, (1, 10))
                        base = p.weekly_wage * random.uniform(1.15, 1.50)
                        tier_order = {"弱旅":0,"下游":1,"中游":2,"劲旅":3,"豪门":4}
                        tier_diff = tier_order.get(new_tier,2) - tier_order.get(p.team_tier,2)
                        if tier_diff >= 3: base *= random.uniform(1.3, 1.6)
                        elif tier_diff >= 2: base *= random.uniform(1.1, 1.3)
                        offer_wage = round(max(wage_lo, min(wage_hi, base)), 1)
                    offer_years = random.randint(2, 5)
                    offer_clause = round(offer_wage * 52 * (random.choice([3, 5, 8]) if random.random() < 0.3 else 0))
                    target_rank = random.randint(1, 18)
                    target_atm = random.choice(["融洽","平淡","涣散"])
                    existing = get_pending_transfers(pid)
                    if not any(o["team"] == new_team for o in existing):
                        offer = {
                        "id": _uuid2.uuid4().hex[:6],
                        "team": new_team, "tier": new_tier, "league": new_league,
                        "years": offer_years, "wage": offer_wage, "clause": offer_clause,
                        "target_rank": target_rank, "target_atm": target_atm,
                        "neg_history": [], "neg_round": 1, "status": "pending",
                    }
                    existing.append(offer)
                    print(f"[转会报价] {p.name} ← {new_team} ({new_tier}, {offer_years}年)")
                elif evt.get("category") == "转会传闻":
                    print(f"[转会-流式] 事件为转会传闻但 _new_team 缺失，effects: {effects}")
                players[pid] = p
                seasons[pid] = s

                apply_effects(pid, effects, data.get("temp_status", "无"))

                cat = evt.get("category", "未知")
                add_used_cat(pid, cat)
                opt = req.option_id if req.option_id != "custom" else f"自定义: {req.custom_text[:30]}"
                add_completed(pid, f"[{cat}] {evt.get('title', '')} → {opt}")

                save_game(pid)
                new_achs = check_and_award(pid)
                offers = get_pending_transfers(pid)
                yield f"data: {json.dumps({'type': 'done', 'narrative': data['narrative'], 'category': cat, 'new_position': new_pos, 'transfer_offers': offers, 'events_done': len(get_completed(pid)), 'events_total': 4, 'effects': effects, 'temp_status': data.get('temp_status', '无'), 'new_achievements': new_achs})}\n\n"
            elif typ == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============================================================
# 合同
# ============================================================
@app.post("/api/game/{pid}/contract/renew")
async def api_renew_contract(pid: str, req: FreeTalkReq):
    """续约：content 格式为 "seasons,wage,clause" 例 "3,15.5,0" """
    _need(pid)
    parts = req.content.split(",")
    seasons = int(parts[0]) if len(parts) > 0 else 3
    wage = float(parts[1]) if len(parts) > 1 else 10.0
    clause = float(parts[2]) if len(parts) > 2 else 0.0
    wage_level = renew_contract(pid, max(1, min(5, seasons)), max(0.5, wage), max(0.0, clause))
    save_game(pid)
    return {"message": f"续约成功，{seasons}年 周薪{wage}万 ({wage_level})"}


# ============================================================
# 回合结算
# ============================================================
@app.post("/api/game/{pid}/settle")
async def api_settle(pid: str):
    _need(pid)
    p, s, effects, logs = settlement_prep(pid)

    if len(logs) == 0:
        raise HTTPException(400, "本回合还没处理任何事件，无法结算")

    summary = "\n".join(f"- {l}" for l in logs)
    result = await ai_settle(p, s, summary, effects)
    p, s = advance_round(pid)
    set_current_news(pid, result.get("news", []))
    buff = roll_settlement_buff(pid)
    save_game(pid)
    new_achs = check_and_award(pid)

    return {
        "narrative": result["narrative"],
        "world_news": result["news"],
        "buff": buff,
        "attr_changes": effects,
        "team_rank": s.team_rank,
        "team_points": s.team_points,
        "temp_status": p.temp_status,
        "atmosphere": s.atmosphere,
        "next_round": s.round_name,
        "season": s.season,
        "new_achievements": new_achs, "growth_changes": season_growth_changes.pop(pid, {}),
    }


# ============================================================
# 配置 & 存档 & 删除
# ============================================================
@app.get("/api/config")
async def api_config():
    import config
    key = config.DEEPSEEK_API_KEY
    return {
        "positions": POSITIONS,
        "hard_attrs": ["射门","跑位","定位球","传球","盘带","技术","才华","盯人","抢断","站位","强壮","速度","跳跃","体力","头球"],
        "soft_attrs": ["意志力","勇敢","抗压能力","稳定性","情绪控制","职业态度","团队精神","人际处理","公众口碑","声望","伤病抗性","多面性","双足均衡"],
        "rounds": ROUNDS,
        "ai_ready": bool(key and "请设置" not in key),
    }


class SetupReq(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""

@app.post("/api/setup")
async def api_setup(req: SetupReq):
    import config, ai_engine
    if req.api_key:
        config.DEEPSEEK_API_KEY = req.api_key
        ai_engine.DEEPSEEK_API_KEY = req.api_key
    if req.base_url:
        config.DEEPSEEK_BASE_URL = req.base_url
        ai_engine.DEEPSEEK_BASE_URL = req.base_url
    if req.model:
        config.DEEPSEEK_MODEL = req.model
        ai_engine.DEEPSEEK_MODEL = req.model
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    DEEPSEEK_API_KEY = config.DEEPSEEK_API_KEY
    DEEPSEEK_BASE_URL = config.DEEPSEEK_BASE_URL
    DEEPSEEK_MODEL = config.DEEPSEEK_MODEL
    return {"message": "配置已保存", "ready": True}


@app.get("/api/saves")
async def api_list_saves():
    return {"saves": list_saves()}


@app.post("/api/game/{pid}/save")
async def api_manual_save(pid: str, req: FreeTalkReq):
    """手动命名存档。FreeTalkReq 复用 content 字段作存档名"""
    _need(pid)
    save_id = create_named_save(pid, req.content)
    return {"save_id": save_id, "message": "存档成功"}


@app.post("/api/saves/{save_id}/load")
async def api_load_save(save_id: str):
    try:
        pid = load_game(save_id)
    except FileNotFoundError:
        raise HTTPException(404, "存档不存在")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"player": players[pid].model_dump(), "message": "存档加载成功"}


@app.delete("/api/saves/{save_id}")
async def api_delete_save(save_id: str):
    delete_save(save_id)
    return {"message": "存档已删除"}


@app.delete("/api/player/{pid}")
async def api_delete(pid: str):
    delete_save(pid)
    return {"message": "已删除"}


# ============================================================
# 静态文件
# ============================================================
if os.path.isdir(FRONTEND_DIR):
    @app.get("/style.css")
    async def serve_css():
        return FileResponse(os.path.join(FRONTEND_DIR, "style.css"))
    @app.get("/app.js")
    async def serve_js():
        return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))
    @app.get("/")
    async def serve():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
    print(f"  前端: {FRONTEND_DIR}")
    print(f"  浏览器打开 http://127.0.0.1:8000")
else:
    print(f"  [警告] 未找到前端: {FRONTEND_DIR}")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    import uvicorn
    import webbrowser
    import threading

    print("=" * 50)
    print("  命运绿茵 - 球员生涯模拟")
    print("=" * 50)
    print(f"  存档目录: {os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'saves'))}")

    # 延迟 1.5s 后自动打开浏览器
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")


@app.on_event("shutdown")
async def shutdown():
    await close_client()
