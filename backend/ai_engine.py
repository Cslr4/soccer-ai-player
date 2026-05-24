"""
DeepSeek AI 游戏引擎
"""

from __future__ import annotations
import json
import re
import random
import httpx
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, ALL_ATTRS

# 共享 HTTP 客户端 —— 复用 TCP 连接，避免每次 API 调用重新握手
_client: httpx.AsyncClient | None = None

def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client

async def close_client():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

ROUND_PERIOD = {
    "夏窗": "6月-8月初（转会期）",
    "上半前期": "8月-10月初", "上半后期": "10月中-12月",
    "冬窗": "1月-2月初（冬窗转会）",
    "下半前期": "2月中-4月初", "下半后期": "4月中-5月底（赛季末）",
}

SYSTEM_PROMPT = """你是《命运绿茵》——一个足球球员生涯模拟游戏的主持AI。

## 游戏规则
- 球员有28项属性(0-100)：
  硬实力[射门、跑位、定位球、传球、盘带、技术、才华、盯人、抢断、站位、强壮、速度、跳跃、体力、头球]
  软实力[意志力、勇敢、抗压能力、稳定性、情绪控制、职业态度、团队精神、人际处理、公众口碑、声望、伤病抗性、多面性、双足均衡]
- 多面性高→胜任更多位置；勇敢高→比赛拼但易受伤；双足均衡高→左右脚均衡
- 球队氛围分五级：内讧→涣散→平淡→融洽→鼎盛。氛围影响事件走向和球员成长，事件也可改变氛围
- 伤病抗性越高越不容易受伤；公众口碑越高越不受负面媒体影响
- 一赛季6回合，每回合约2-3个月，事件须符合该时段真实足球逻辑
- 等级范围：豪门(硬780-850/软750-800)、劲旅(硬710-780/软725-790)、中游(硬640-710/软700-775)、下游(硬570-640/软675-760)、弱旅(硬500-570/软650-745)

## 绝对规则
- 叙事永远不显示数值
- 每个选项同时隐含正面和负面效果。体力只增不减——训练/比赛/恢复都可能提升体力，任何事件都不得让体力降低。用其他属性（如强壮/速度/抗压等）表达代价
- 使用真实球队名和球员名
- 球员位置在生涯中可能改变
- 队内氛围即使不佳，也不应过半事件都是更衣室冲突；比赛、训练、转会、场外生活等需保持合理比例
- 转会事件结算时，必须在effects中包含_new_team（新球队中文全名）、_new_team_tier（豪门/劲旅/中游/下游/弱旅）、_new_league_level（争冠/上游/中游/下游/保级），叙事中提及的新球队须与effects一致
- 更衣室地位分五级（边缘人物→普通成员→重要角色→核心领袖→传奇），影响出场时间和事件走向。地位由实力匹配度、社交属性、资历、表现、年龄综合决定，冬窗和夏窗结算。
- 结构化数据用```json代码块，纯叙事直接输出"""


async def _call(prompt: str, temp: float = 0.9, max_tok: int = 1200) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    c = _get_client()
    r = await c.post(
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": temp, "max_tokens": max_tok},
    )
    if r.status_code == 402:
        return f"[AI错误]DeepSeek 账户余额不足，请充值后重试。"
    if r.status_code != 200: return f"[AI错误{r.status_code}]{r.text[:200]}"
    return r.json()["choices"][0]["message"]["content"]


# ============================================================
# 流式 API 调用（SSE）
# ============================================================
async def _call_stream(prompt: str, temp: float = 0.9, max_tok: int = 1200):
    """流式调用 DeepSeek，逐 token yield (type, content)。
    type: "chunk" 文本片段 | "done" 完整文本 | "error" 错误信息
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    c = _get_client()

    async with c.stream(
        "POST",
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": temp,
              "max_tokens": max_tok, "stream": True},
    ) as r:
        if r.status_code != 200:
            body = await r.aread()
            yield ("error", f"[AI错误{r.status_code}]{body[:200]}")
            return

        full = ""
        async for line in r.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    full += content
                    yield ("chunk", content)
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

        yield ("done", full)


def _parse_stream(text: str):
    """从\"叙事在前、JSON在后\"的 AI 回复中提取 narrative 和结构化数据。
    返回 (narrative, raw_dict)。"""
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if m:
        narrative = text[:m.start()].strip()
        try:
            return narrative, json.loads(m.group(1))
        except json.JSONDecodeError:
            return narrative, {}
    # 尝试裸 JSON
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        narrative = text[:m.start()].strip()
        try:
            return narrative, json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return text.strip(), {}


def _clean_effects(raw: dict) -> dict:
    """过滤并钳位 effects 中的属性值（-3..3），保留特殊键（_开头）"""
    out = {}
    for k, v in raw.items():
        if k.startswith("_"):
            out[k] = v
        elif k in ALL_ATTRS:
            try:
                out[k] = max(-2, min(2, int(v)))
            except (ValueError, TypeError):
                pass
    return out


def _json(text: str) -> dict | None:
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if m:
        try: return json.loads(m.group(1))
        except json.JSONDecodeError: pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try: return json.loads(m.group(0))
        except json.JSONDecodeError: pass
    return None


def _p(p) -> str: return f"球员：{p.name} {p.age}岁 {p.height}cm {p.weight}kg 国籍：{p.nationality} | {p.position} | 效力：{p.team_name}({p.team_tier}) | 状态：{p.temp_status} | 更衣室地位：{p.locker_status} | 合同：剩{p.seasons_left}年 周薪{p.weekly_wage}万"
def _s(s) -> str: return f"第{s.season}赛季 {s.round_name} | 排名#{s.team_rank} 积分{s.team_points} 已赛{s.team_games}场 | 队内氛围：{s.atmosphere}"
def _a(attrs) -> str:
    d = attrs if isinstance(attrs, dict) else attrs.model_dump()
    return " | ".join(f"{k}:{d[k]}" for k in ALL_ATTRS)
def _period(rn: str) -> str:
    p = ROUND_PERIOD.get(rn, ""); return f"当前时期：{p}（{rn}）" if p else rn


# ============================================================
# 0. 创建角色
# ============================================================
async def create_player_ai(name, team_name, nationality, position, age, height, weight, traits=None, team_tier=None) -> dict:
    traits = traits or []
    hint_parts = []
    for trait in traits:
        if trait in __import__("config").TRAITS:
            t = __import__("config").TRAITS[trait]
            items = "、".join(t["boost"].keys())
            hint_parts.append(f"特点「{trait}」({t['desc']})，侧重：{items}")
    trait_hint = ("\n" + "\n".join(hint_parts) + "\n在符合等级范围的前提下，这些属性偏向上限。") if hint_parts else ""
    prompt = f"""【创建角色】{name}，{age}岁，{height}cm，{weight}kg，国籍：{nationality}，{position}，加入{team_name}。{trait_hint}

根据该队在世界足坛的真实实力判断世界等级（豪门/劲旅/中游/下游/弱旅），再判断该队在自身联赛中的地位（争冠/上游/中游/下游/保级）。
世界等级决定初始属性范围：
豪门硬780-850软750-800；劲旅硬710-780软725-790；中游硬640-710软700-775；下游硬570-640软675-760；弱旅硬500-570软650-745。
注意：软实力下限必须严格遵守，弱旅球员软实力也不能低于650总。伤病抗性>60，公众口碑>50。

位置侧重：中后卫(盯人抢断站位头球强壮)、边后卫(速度抢断盯人传球)、后腰(盯人抢断传球体力)、中场(传球技术才华跑位)、前腰(才华技术盘带定位球射门)、边锋(速度盘带技术跑位)、中锋(射门头球跑位强壮)。

返回JSON（team_name用中文全名）：```json
{{"team_tier":"弱旅","league_level":"争冠","team_name":"中文队名","attrs":{{"射门":0,...}}}}
```"""
    text = await _call(prompt, temp=0.7, max_tok=900)
    data = _json(text)
    if data:
        return {
            "team_tier": data.get("team_tier","弱旅"),
            "league_level": data.get("league_level","中游"),
            "team_name": data.get("team_name",team_name),
            "attrs": {a: max(0, min(100, int(data.get("attrs",{}).get(a,50)))) for a in ALL_ATTRS},
        }
    return {"team_tier":"弱旅","league_level":"中游","team_name":team_name,"attrs":{a:50 for a in ALL_ATTRS}}


# ============================================================
# 合同谈判
# ============================================================
async def negotiate_contract(player, season, offer, player_msg):
    """AI 合同谈判：玩家发言，AI 回应并可能调整报价"""
    prompt = f"""【合同谈判】{player.name}与{offer['team']}({offer.get('tier','')})谈判。
当前报价：{offer['years']}年 周薪{offer['wage']}万 解约金{offer.get('clause',0)}万
球员：{player.name} {player.age}岁 {player.position} 效力{player.team_name}
球员发言：{player_msg}

你是俱乐部谈判代表。简短回应（30-60字），然后判断是否接受球员要求。
- 如果接受：在回应末尾附```json
{{"decision":"accept","counter":{{"years":{offer['years']},"wage":{offer['wage']},"clause":{offer.get('clause',0)}}}}}
```
- 如果拒绝且谈判破裂：{{"decision":"reject"}}
- 如果讨价还价：{{"decision":"counter","counter":{{"years":N,"wage":N.N,"clause":N}}}}
（counter中给出调整后的报价）

直接输出回应文本+JSON块。"""
    text = await _call(prompt, temp=0.7, max_tok=400)
    data = _json(text)
    if data:
        narrative = text[:text.find("```json")].strip() if "```json" in text else text
        return {"narrative": narrative or text, "decision": data.get("decision","counter"),
                "counter": data.get("counter", {}), "negotiated": True}
    return {"narrative": text, "decision": "counter", "counter": {}, "negotiated": True}


# 转会兜底：AI 没给 _new_team 时从叙事文本通用提取球队名
def _extract_team_from_text(text, current_team):
    """从 AI 叙事中提取转会目标球队名（通用匹配，不靠硬编码表）"""
    patterns = [
        r'(?:加盟|转会|签约|前往|投奔|加入|抵达|来到)\s*([一-鿿]{2,8}(?:联|队|城|亚|斯|姆|卡|纳|萨|黎|马|森|堡|利|勒|塔|尼|波|格|齐|恩|瓦|尔|特|蒙|里|良|丁|卡|巴|维|兰|郡|普|托|文|菲|顿|加|罗|黑|切|曼|赛|汀|堡|纳|斯|亚|希|辛|富|勒|克|拉|福|兰|西|斯|佛|伦|萨|都|灵|图|特|法|克|福|门|兴|沃|尔|夫|斯|堡|雷|恩|尼|斯|伦|西|亚|贝|蒂|斯|罗|纳))',
        r'(?:有意|报价|求购|关注)\s*([一-鿿]{2,8}(?:联|队|城|亚|斯|姆|卡|纳|萨|黎|马|森|堡|利|勒|塔|尼|波|格|齐|恩|瓦|尔|特|蒙|里|良|丁|卡|巴|维|兰|郡|普|托|文|菲|顿|加|罗|黑|切|曼|赛|汀|堡|纳|斯|亚|希|辛|富|勒|克|拉|福|兰|西|斯|佛|伦|萨|都|灵|图|特|法|克|福|门|兴|沃|尔|夫|斯|堡|雷|恩|尼|斯|伦|西|亚|贝|蒂|斯|罗|纳))',
        r'([一-鿿]{2,6}(?:联|队|城))\s*(?:的|向|给)',
    ]
    import re as _re2
    for pat in patterns:
        m = _re2.search(pat, text)
        if m and m.group(1) != current_team:
            return m.group(1)
    return None


# ============================================================
# 新闻扩写
# ============================================================
async def expand_news(player, season, headline):
    text = await _call(f"""将以下足坛简讯扩展为3-4句详细报道（60-100字），保持足球新闻口吻，提及相关球队和球员。直接输出纯文本，不要JSON。
简讯：{headline}""", temp=0.7, max_tok=250)
    return text.strip()


# ============================================================
# 1. 回合开始
# ============================================================
async def round_start(player, season) -> dict:
    text = await _call(f"""【回合开始】{_period(season.round_name)}
{_p(player)} | {_s(season)}
播报6条足坛大事：2条本联赛 + 2条国际新闻 + 2条关于{player.name}的个人动态。每条20-40字。再加一句开场白。
返回JSON：```json
{{"news":["联赛1","联赛2","国际1","国际2","个人1","个人2"],"round_intro":"开场白..."}}```""", temp=1.0, max_tok=600)
    data = _json(text)
    return {"news": data.get("news",[]) if data else [], "round_intro": data.get("round_intro","") if data else ""}


# ============================================================
# 2. 单个事件
# ============================================================
async def generate_single_event(player, season, used_cats=None) -> dict:
    # 类别统计：同类别最多2次，出现1次后降低再出概率
    used_cats = used_cats or []
    from collections import Counter
    cat_counts = Counter(used_cats)
    avoid_parts = []
    once_cats = [c for c, n in cat_counts.items() if n == 1]
    twice_cats = [c for c, n in cat_counts.items() if n >= 2]
    if once_cats:
        avoid_parts.append(f"降低概率再用：{'、'.join(once_cats)}")
    if twice_cats:
        avoid_parts.append(f"本轮禁止再用：{'、'.join(twice_cats)}")
    # 伤病抗性高→大幅降低伤病事件概率
    if player.attrs.伤病抗性 >= 80:
        avoid_parts.append("伤病抗性极高，几乎不会受伤")
    elif player.attrs.伤病抗性 >= 65:
        avoid_parts.append("伤病抗性较高，伤病事件应极少出现")
    elif player.attrs.伤病抗性 < 30:
        avoid_parts.append("伤病抗性极低，容易受伤")
    # 软实力仅影响事件好坏倾向，不影响种类
    from game_state import calc_soft_power as _csp
    _sp, _tag = _csp(player.id)
    if _tag:
        avoid_parts.append(_tag + "（仅影响事件正负，不改变类别）")
    # 非转会窗每回合必有一个比赛表现事件
    is_window = season.round_name in ("夏窗", "冬窗")
    if not is_window and "比赛表现" not in used_cats and len(used_cats) >= 2:
        avoid_parts.append("本轮未出现比赛表现事件，本事件必须为比赛表现类别")
    avoid = "；".join(avoid_parts) if avoid_parts else ""
    # 转会兴趣评估
    from game_state import calc_transfer_interest
    tr_interest = calc_transfer_interest(player.id)
    if tr_interest < 3:
        avoid = (avoid + "；本赛季无实质性球队报价" if avoid else "本赛季无实质性球队报价")
    elif tr_interest < 7:
        avoid = (avoid + "；仅低级别球队偶有试探" if avoid else "仅低级别球队偶有试探")
    elif tr_interest < 12:
        avoid = (avoid + "；有同级或略高球队关注" if avoid else "有同级或略高球队关注")
    elif tr_interest < 18:
        avoid = (avoid + "；劲旅级别球队有意" if avoid else "劲旅级别球队有意")
    else:
        avoid = (avoid + "；少数豪门球探跟踪观察" if avoid else "少数豪门球探跟踪观察")
    # 注入近期对话历史（仅作轻参考，1-3个相关即可）
    from game_state import get_talk_history as _th
    talks = _th(player.id)
    talk_hint = ""
    if talks:
        recent = talks[-3:]
        lines = "\n".join(f"- [{t['target']}] {t['topic']}" for t in recent)
        talk_hint = f"\n【玩家近期对话-仅参考】\n{lines}\n注意：本回合4个事件中1-3个可与此相关，至少保留1-2个其他类别以保持多样性。"
    # 合同年提示
    if player.seasons_left <= 1:
        talk_hint += "\n【合同即将到期】续约/自由转会事件应提高出现概率。"
    elif player.seasons_left == 2:
        talk_hint += "\n【合同进入最后2年】续约话题逐渐升温。"
    # 转会类别限制：刚转会/无兴趣/非窗口/已有报价去重 → 移除
    cats = "比赛表现/训练日常/人际交往/媒体舆论/转会传闻/伤病医疗/场外生活/生涯抉择"
    is_window = season.round_name in ("夏窗", "冬窗")
    just_moved = player.last_transfer_season == season.season
    # 已有报价的球队列表
    from game_state import get_pending_transfers
    existing_teams = [o["team"] for o in get_pending_transfers(player.id)]
    if just_moved:
        cats = "比赛表现/训练日常/人际交往/媒体舆论/伤病医疗/场外生活/生涯抉择"
        avoid = (avoid + "；刚完成转会，本赛季不再出现转会事件" if avoid else "刚完成转会，本赛季不再出现转会事件")
    elif tr_interest < 5:
        cats = "比赛表现/训练日常/人际交往/媒体舆论/伤病医疗/场外生活/生涯抉择"
    elif not is_window:
        cats = "比赛表现/训练日常/人际交往/媒体舆论/伤病医疗/场外生活/生涯抉择"
        avoid = (avoid + "；非转会窗，不出现转会事件" if avoid else "非转会窗，不出现转会事件")
    if existing_teams:
        avoid = (avoid + f"；已有以下球队报价不可重复：{'、'.join(existing_teams)}" if avoid else f"已有以下球队报价不可重复：{'、'.join(existing_teams)}")
    text = await _call(f"""【生成一个事件】{_period(season.round_name)}
{_p(player)} | {_s(season)} | 属性：{_a(player.attrs)} | {avoid}{talk_hint}

从[{cats}]中随机挑选一个类别，生成一个事件。
重要：杜绝模板化！每个事件必须独特——不同的人物、不同的场景细节、不同的对话、不同的冲突角度。即使同类事件也必须换全新具体内容，避免"教练表扬/批评""队友配合好/坏"等套路。
符合当前时段足球逻辑，可结合国籍。100-200字，2-3选项各含正反隐效。
如果是"转会传闻"类别，必须在事件描述中明确写出有意向签约的具体球队中文全名。转会球队不能是上面已列出的球队。

返回JSON：```json
{{"category":"比赛表现","title":"标题","description":"描述","options":[{{"id":"A","text":"A"}},{{"id":"B","text":"B"}},{{"id":"C","text":"C"}}]}}
```""", temp=1.2, max_tok=900)
    data = _json(text)
    if data: return {"category":data.get("category",""),"title":data.get("title",""),"description":data.get("description",""),"options":data.get("options",[])}
    return {"category":"训练日常","title":"日常","description":"训练照常。","options":[{"id":"A","text":"全力以赴"},{"id":"B","text":"按部就班"}]}


# ============================================================
# 3. 自由对话
# ============================================================
async def free_talk(player, season, content, history=None, target="") -> dict:
    target_info = f"对话对象：{target}\n" if target else ""
    hist = "\n".join(f"{'玩家' if h['role']=='user' else '对方'}: {h['content'][:100]}" for h in (history or [])[-6:]) if history else ""
    text = await _call(f"""【自由对话】{_period(season.round_name)}
{target_info}{_p(player)} | 属性：{_a(player.attrs)} | 最近：{hist or '无'}
玩家：{content}
叙事回应（100-200字）+轻效（0-1项±1）。返回JSON：```json
{{"narrative":"...","effects":{{}}}}```""", temp=0.8, max_tok=450)
    data = _json(text)
    if data:
        eff = {k: max(-1, min(1, int(v))) for k, v in data.get("effects",{}).items() if k in ALL_ATTRS}
        return {"narrative": data.get("narrative",text), "effects": eff}
    return {"narrative": text, "effects": {}}


# ============================================================
# 4. 事件结算
# ============================================================
async def resolve_event(player, season, event, option_id, custom_text="") -> dict:
    opts = "\n".join(f"{o['id']}: {o['text']}" for o in event.get("options",[]))
    choice = custom_text if option_id=="custom" else next((o['text'] for o in event.get('options',[]) if o['id']==option_id), option_id)
    text = await _call(f"""【事件结算】{_period(season.round_name)}
{_p(player)} | 属性：{_a(player.attrs)}
事件：[{event.get('category')}] {event.get('title')}
描述：{event.get('description')} | 选项：{opts} | 玩家选择：{choice}
叙事（150-250字，正反两面）+属性变化（1-2项±1~2）+临时状态。可改变队内氛围加"_atmosphere"键。位置变更加"_new_position"。转会事件必须将_new_team（中文全名）、_new_team_tier（豪门/劲旅/中游/下游/弱旅）、_new_league_level（争冠/上游/中游/下游/保级）放入effects内。
返回JSON：```json
{{"narrative":"...","effects":{{"射门":1,"_new_team":"新队名","_new_team_tier":"豪门"}},"temp_status":"无"}}```""", temp=0.8, max_tok=700)
    data = _json(text)
    if data:
        eff = {}
        for k, v in data.get("effects",{}).items():
            if k.startswith("_"):
                eff[k] = v
            elif k in ALL_ATTRS:
                eff[k] = max(-2, min(2, int(v)))
        # 兜底：AI 可能把特殊键放在 JSON 顶层而非 effects 内
        for k in ("_new_position", "_atmosphere", "_new_team", "_new_team_tier", "_new_league_level"):
            if k in data and k not in eff:
                eff[k] = data[k]
        # 转会兜底：AI 没给 _new_team → 从叙事提取球队名
        if event.get("category") == "转会传闻" and "_new_team" not in eff:
            team = _extract_team_from_text(text, player.team_name)
            if team:
                tiers = ["弱旅","下游","中游","劲旅","豪门"]
                idx = tiers.index(player.team_tier) if player.team_tier in tiers else 2
                new_tier = tiers[min(len(tiers)-1, idx + random.randint(0, 1))]
                leagues = {"豪门":"争冠","劲旅":"上游","中游":"中游","下游":"下游","弱旅":"保级"}
                eff["_new_team"] = team
                eff["_new_team_tier"] = new_tier
                eff["_new_league_level"] = leagues.get(new_tier, "中游")
        return {"narrative": data.get("narrative",text), "effects": eff, "temp_status": data.get("temp_status","无")}
    return {"narrative": text, "effects": {}, "temp_status": "无"}


# ============================================================
# 5. 回合结算
# ============================================================
async def settle(player, season, summary, changes) -> dict:
    chg = ", ".join(f"{k}{'+' if v>0 else ''}{v}" for k,v in changes.items() if v!=0) or "无变化"
    text = await _call(f"""【回合结算】{_period(season.round_name)}
{_p(player)} | {_s(season)} | 属性：{_a(player.attrs)}
本回合：{summary} | 变化：{chg}
输出narrative（300-400字）+news（6条：2条本联赛+2条国际+2条关于{player.name}的个人动态，每条20-40字）。返回JSON：
```json
{{"narrative":"...","news":["新闻1","新闻2","新闻3","新闻4","新闻5","新闻6"],"team_rank":{season.team_rank},"team_points":{season.team_points}}}```""", temp=0.9, max_tok=1600)
    data = _json(text)
    if data: return {"narrative": data.get("narrative",""), "news": data.get("news",[]), "team_rank": data.get("team_rank",season.team_rank), "team_points": data.get("team_points",season.team_points)}
    return {"narrative": text, "news": [], "team_rank": season.team_rank, "team_points": season.team_points}


# ============================================================
# 6. AI 对话式合同谈判
# ============================================================
async def negotiate_contract_dialogue(player, season, offer, player_msg: str, round_num: int) -> dict:
    """AI 对话式谈判。玩家自由发言，AI 根据球员实际表现判断合理性。4轮。"""
    text = await _call(f"""【合同谈判对话】第{round_num}轮（共4轮）

{_p(player)}
报价球队：{offer['team']}（{offer['tier']}，联赛排名#{offer.get('target_rank','?')}，更衣室{offer.get('target_atm','?')}）
原报价：{offer['years']}年 周薪{offer['wage']}万欧 解约金{offer.get('clause',0)}万欧

球员说："{player_msg}"

你是对方俱乐部的谈判代表，用自然口语化中文回应，像真人谈判一样说话。
关键判断依据——看球员的实际表现和声望：
- 上赛季进球/助攻多、声望高、是核心球员 → 还价合理范围大（可接受涨50%-100%），甚至可以直接同意
- 表现平平、声望一般 → 还价空间小（涨20%-30%），态度稍硬
- 表现差、年龄大 → 几乎没空间，坚持原报价
回应策略：
- 合理 → decision: "accept"，直接同意。counter里填入最终确定的wage/years/clause，注意：如果是同意球员的还价，必须用球员说的数字，不能自己改口！例：球员说"4万"，你同意就必须写"wage":4，不能写3.9
- 还价 → decision: "counter"，给出折中数字
- 离谱 → decision: "reject"
每轮逐渐宽松。可以提及球队排名/氛围作为谈判筹码。

返回JSON（wage>0、years>0）：```json
{{"decision":"accept/counter/reject","narrative":"回应","counter":{{"wage":12.5,"years":4,"clause":3000}}}}
```""", temp=0.8, max_tok=500)
    data = _json(text)
    if data:
        return {
            "decision": data.get("decision", "accept"),
            "narrative": data.get("narrative", text),
            "counter": data.get("counter"),
        }
    return {"decision": "accept", "narrative": text, "counter": None}


# ============================================================
# 流式版本 —— 叙事先出，JSON 后出，逐 token 推送
# ============================================================

async def free_talk_stream(player, season, content, history=None, target=""):
    """流式自由对话 —— 叙事纯文本先行，JSON 块后置"""
    target_info = f"对话对象：{target}\n" if target else ""
    hist = "\n".join(f"{'玩家' if h['role']=='user' else '对方'}: {h['content'][:100]}" for h in (history or [])[-6:]) if history else ""
    prompt = f"""【自由对话】{_period(season.round_name)}
{target_info}{_p(player)} | 属性：{_a(player.attrs)} | 最近：{hist or '无'}
玩家：{content}

先直接写叙事回应（100-200字，纯文本），不要用任何标记包裹叙事。
然后另起一行用```json代码块给出轻效数据（0-1项±1）：
```json
{{"effects":{{}}}}
```"""
    narrative = ""
    async for typ, data in _call_stream(prompt, temp=0.8, max_tok=450):
        if typ == "chunk":
            yield ("chunk", data)
        elif typ == "done":
            narrative, parsed = _parse_stream(data)
            eff = _clean_effects(parsed.get("effects", {}))
            eff = {k: max(-1, min(1, v)) for k, v in eff.items()}
            yield ("done", {"narrative": narrative or data, "effects": eff})
        elif typ == "error":
            yield ("error", data)


async def resolve_event_stream(player, season, event, option_id, custom_text=""):
    """流式事件结算 —— 叙事纯文本先行，JSON 块后置"""
    opts = "\n".join(f"{o['id']}: {o['text']}" for o in event.get("options", []))
    choice = custom_text if option_id == "custom" else next((o['text'] for o in event.get('options', []) if o['id'] == option_id), option_id)
    prompt = f"""【事件结算】{_period(season.round_name)}
{_p(player)} | 属性：{_a(player.attrs)}
事件：[{event.get('category')}] {event.get('title')}
描述：{event.get('description')} | 选项：{opts} | 玩家选择：{choice}

先直接写叙事（150-250字，正反两面，纯文本），不要用任何标记包裹叙事。
然后另起一行用```json代码块给出数据（属性变化1-2项±1~2、临时状态、可选_atmosphere、_new_position，转会必须将_new_team/_new_team_tier/_new_league_level放入effects内，同时写入_offer_wage（周薪万欧）和_offer_years（年限），这些数字必须与叙事中提到的完全一致！）：
```json
{{"effects":{{"射门":1,"_new_team":"新队名","_new_team_tier":"豪门"}},"temp_status":"无"}}
```"""
    narrative = ""
    async for typ, data in _call_stream(prompt, temp=0.8, max_tok=700):
        if typ == "chunk":
            yield ("chunk", data)
        elif typ == "done":
            narrative, parsed = _parse_stream(data)
            eff = _clean_effects(parsed.get("effects", {}))
            # 兜底：AI 可能把特殊键放在顶层
            for k in ("_new_position", "_atmosphere", "_new_team", "_new_team_tier", "_new_league_level"):
                if k in parsed and k not in eff:
                    eff[k] = parsed[k]
            # 转会兜底：从叙事提取球队名
            if event.get("category") == "转会传闻" and "_new_team" not in eff:
                team = _extract_team_from_text(data, player.team_name)
                if team:
                    tiers = ["弱旅","下游","中游","劲旅","豪门"]
                    idx = tiers.index(player.team_tier) if player.team_tier in tiers else 2
                    nt = tiers[min(len(tiers)-1, idx + random.randint(0, 1))]
                    leagues = {"豪门":"争冠","劲旅":"上游","中游":"中游","下游":"下游","弱旅":"保级"}
                    eff["_new_team"] = team
                    eff["_new_team_tier"] = nt
                    eff["_new_league_level"] = leagues.get(nt, "中游")
            yield ("done", {
                "narrative": narrative or data,
                "effects": eff,
                "temp_status": parsed.get("temp_status", "无"),
            })
        elif typ == "error":
            yield ("error", data)
