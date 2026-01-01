
import os
import re

app_path = 'dashboard/app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

new_func = """
def build_group_activity(days: int = 30, chat_id=None) -> dict:
    log.info("build_group_activity called with days=%s, chat_id=%s", days, chat_id)
    days = int(days) if str(days).isdigit() else 30
    if days < 1: days = 1
    if days > 365: days = 365

    chat_id_raw = (str(chat_id).strip() if chat_id is not None else "")
    chat_id_filter = None
    if chat_id_raw != "":
        chat_id_filter = chat_id_raw

    now = _now()
    cutoff = now - timedelta(days=days)
    cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo is not None else cutoff

    start_date = (now - timedelta(days=days - 1)).date()
    labels = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    per_hour = [0] * 24
    per_weekday = [0] * 7
    timeline_map = defaultdict(int)

    per_user = defaultdict(lambda: {
        "user_id": "",
        "username": "",
        "full_name": "",
        "messages": 0,
        "media": 0,
        "likes_received": 0,
        "likes_given": 0,
        "last_seen": None,
        "daily": defaultdict(int),
    })

    per_chat = defaultdict(int)
    total = 0
    media_shared = 0
    total_reactions_received = 0
    total_reactions_given = 0

    # --- 1. Parse reactions_log.jsonl for given reactions ---
    REACTIONS_LOG_FILE = os.path.join(DATA_DIR, "reactions_log.jsonl")
    if os.path.exists(REACTIONS_LOG_FILE):
        r_lines = _tail_text_file(REACTIONS_LOG_FILE, max_lines=50000)
        for rl in r_lines:
            rl = (rl or "").strip()
            if not rl: continue
            try:
                rj = json.loads(rl)
                rdt = _parse_dt(rj.get("ts"))
                if not rdt: continue
                rdt_naive = rdt.replace(tzinfo=None) if rdt.tzinfo is not None else rdt
                if rdt_naive < cutoff_naive: continue
                
                if chat_id_filter:
                    rcid = rj.get("chat_id")
                    if rcid is None or str(rcid).strip() != str(chat_id_filter).strip():
                        continue

                rid = str(rj.get("reactor_user_id", "")).strip()
                if rid:
                    new_r = rj.get("new_reaction")
                    if isinstance(new_r, list) and len(new_r) > 0:
                        nr_str = str(new_r[0])
                        if nr_str != "()" and ("emoji=" in nr_str or "ReactionType" in nr_str):
                            per_user[rid]["user_id"] = rid
                            per_user[rid]["likes_given"] += 1
                            total_reactions_given += 1
                            
                            if not per_user[rid].get("username"):
                                per_user[rid]["username"] = rj.get("reactor_username", "")
                            if not per_user[rid].get("full_name"):
                                per_user[rid]["full_name"] = rj.get("reactor_full_name", "")
            except: continue
    log.info("Group Activity Analytics: counted %d given reactions from log", total_reactions_given)

    # --- 2. Parse user messages ---
    reg_list = load_user_registry_list()
    reg_map = {str(u.get("id")): u for u in reg_list if u.get("id")}

    MAX_LINES_PER_FILE = 12000
    for fp in _iter_message_files():
        lines = _tail_text_file(fp, max_lines=MAX_LINES_PER_FILE)
        for line in lines:
            line = (line or "").strip()
            if not line: continue
            try:
                m = json.loads(line)
            except Exception: continue

            dt = _parse_dt(m.get("ts"))
            if not dt: continue
            try:
                dt_naive = dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            except Exception: dt_naive = dt

            if dt_naive < cutoff_naive: continue

            cid = m.get("chat_id")
            if chat_id_filter is not None:
                if cid is None or str(cid) != chat_id_filter: continue

            author_uid = _extract_user_id_from_msg(m)
            if not author_uid: continue

            total += 1
            try: per_hour[int(dt_naive.hour)] += 1
            except: pass
            try: per_weekday[int(dt_naive.weekday())] += 1
            except: pass

            dkey = dt_naive.date().isoformat()
            if dkey in labels:
                timeline_map[dkey] += 1
            if cid is not None:
                per_chat[str(cid)] += 1

            has_media = bool(m.get("has_media"))
            if has_media:
                media_shared += 1

            likes_received = _extract_reactions_total(m)
            total_reactions_received += likes_received

            u = per_user[author_uid]
            u["user_id"] = author_uid
            u["messages"] += 1
            u["media"] += 1 if has_media else 0
            u["likes_received"] += likes_received

            username = m.get("username") or ""
            full_name = m.get("full_name") or m.get("name") or ""
            if author_uid in reg_map:
                if not username: username = reg_map[author_uid].get("username", "") or ""
                if not full_name: full_name = reg_map[author_uid].get("full_name", "") or ""
            u["username"] = username
            u["full_name"] = full_name

            prev = u["last_seen"]
            if prev is None or dt_naive > prev:
                u["last_seen"] = dt_naive
            if dkey in labels:
                u["daily"][dkey] += 1

    # --- 3. Build Result ---
    total_arr = [int(timeline_map.get(d, 0)) for d in labels]
    busiest_day = None
    if timeline_map:
        busiest_day = max(timeline_map.items(), key=lambda x: x[1])[0]

    leaderboard_list = sorted(per_user.values(), key=lambda x: x.get("messages", 0), reverse=True)
    leaderboard = []
    user_series = {}

    for idx, u in enumerate(leaderboard_list[:20], start=1):
        uid = u["user_id"]
        avatar_url = reg_map.get(uid, {}).get("avatar_url") or f"/tg/avatar/{uid}"
        leaderboard.append({
            "rank": idx,
            "user_id": uid,
            "username": u.get("username", ""),
            "name": u.get("full_name", ""),
            "messages": int(u.get("messages", 0)),
            "media": int(u.get("media", 0)),
            "likes_received": int(u.get("likes_received", 0)),
            "likes_given": int(u.get("likes_given", 0)),
            "avatar_url": avatar_url,
        })
        user_series[uid] = [int(u["daily"].get(d, 0)) for d in labels]

    top_contributor = None
    most_liked_user = None
    if leaderboard:
        top_contributor = leaderboard[0].get("name") or (f"@{leaderboard[0].get('username')}" if leaderboard[0].get("username") else leaderboard[0].get("user_id"))
        most = max(leaderboard, key=lambda x: x.get("likes_received", 0))
        most_liked_user = most.get("name") or (f"@{most.get('username')}" if most.get("username") else most.get("user_id"))

    top_chat = None
    if per_chat:
        cid, cnt = max(per_chat.items(), key=lambda x: x[1])
        top_chat = {"chat_id": str(cid), "messages": int(cnt)}

    peak_hour = max(range(24), key=lambda h: per_hour[h]) if total > 0 else None
    peak_weekday = max(range(7), key=lambda d: per_weekday[d]) if total > 0 else None

    recently_active = []
    recent_sorted = sorted(per_user.values(), key=lambda x: x["last_seen"] or datetime.min, reverse=True)[:10]
    for u in recent_sorted:
        dt_last = u["last_seen"]
        uid = u["user_id"]
        recently_active.append({
            "user_id": uid,
            "username": u.get("username", ""),
            "name": u.get("full_name", ""),
            "last_seen": dt_last.isoformat() if isinstance(dt_last, datetime) else None,
            "avatar_url": reg_map.get(uid, {}).get("avatar_url") or f"/tg/avatar/{uid}",
        })

    meta_compat = {
        "days": days,
        "chat_id": chat_id_filter,
        "totalMessages": int(total),
        "activeUsers": int(len(per_user)),
        "mediaShared": int(media_shared),
        "totalReactions": int(total_reactions_received),
        "totalReactionsGiven": int(total_reactions_given),
        "busiestDay": busiest_day,
        "topContributor": top_contributor,
        "mostLikedUser": most_liked_user,
        "topChat": top_chat,
    }

    timeline_list = [{"date": d, "count": int(timeline_map.get(d, 0))} for d in labels]
    kpis = {
        "total_messages": int(total),
        "active_users": int(len(per_user)),
        "busiest_day": busiest_day,
        "media_shared": int(media_shared),
        "total_reactions_received": int(total_reactions_received),
        "total_reactions_given": int(total_reactions_given),
        "top_contributor": top_contributor or "—",
        "most_liked_user": most_liked_user or "—",
        "top_chat": top_chat or "—",
    }

    return {
        "ok": True,
        "meta": meta_compat,
        "per_hour": per_hour,
        "per_weekday": per_weekday,
        "timeline": timeline_list,
        "leaderboard": leaderboard,
        "kpis": kpis,
        "timeline2": {"labels": labels, "total": total_arr},
        "timeline_series": {"labels": labels, "total": total_arr},
        "busiest_hours": per_hour,
        "busiest_days": per_weekday,
        "user_series": user_series,
        "recently_active": recently_active,
    }
"""

# Replace the whole build_group_activity function
pattern = r'def build_group_activity\(days: int = 30, chat_id=None\) -> dict:.*?return \{.*?\}'
app_content = re.sub(pattern, new_func.strip(), app_content, flags=re.DOTALL)

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

# Now fix the HTML JS mapping
html_path = 'dashboard/src/id_finder_analytics.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

html_content = html_content.replace(
    'total_reactions: payload.kpis?.total_reactions_given ?? meta.total_reactions ?? 0,',
    'total_reactions: payload.kpis?.total_reactions_given ?? meta.totalReactionsGiven ?? meta.total_reactions ?? 0,'
)
html_content = html_content.replace(
    'likes: Number(r.reactions ?? r.likes ?? 0),',
    'likes: Number(r.likes_given ?? r.reactions ?? r.likes ?? 0),'
)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)
