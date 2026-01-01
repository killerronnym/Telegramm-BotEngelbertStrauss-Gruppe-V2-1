
import os
import re

# 1. CLEAN BACKEND FUNCTION
app_path = 'dashboard/app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

# Define the absolute clean function
clean_func = """
def build_group_activity(days: int = 30, chat_id=None) -> dict:
    log.info("build_group_activity start: days=%s, chat_id=%s", days, chat_id)
    days = int(days) if str(days).isdigit() else 30
    if days < 1: days = 1
    if days > 365: days = 365

    chat_id_filter = str(chat_id).strip() if chat_id else None
    now = _now()
    cutoff_naive = (now - timedelta(days=days)).replace(tzinfo=None)

    labels = [( (now - timedelta(days=days - 1)).date() + timedelta(days=i) ).isoformat() for i in range(days)]

    per_user = defaultdict(lambda: {
        "user_id": "", "username": "", "full_name": "",
        "messages": 0, "media": 0, "likes_received": 0, "likes_given": 0,
        "last_seen": None, "daily": defaultdict(int),
    })
    
    per_hour = [0] * 24
    per_weekday = [0] * 7
    timeline_map = defaultdict(int)
    total_messages = 0
    media_shared = 0
    total_reactions_received = 0
    total_reactions_given = 0
    per_chat = defaultdict(int)

    # --- Step 1: Reactions (Likes Given) ---
    REACTIONS_LOG_FILE = os.path.join(DATA_DIR, "reactions_log.jsonl")
    if os.path.exists(REACTIONS_LOG_FILE):
        for line in _tail_text_file(REACTIONS_LOG_FILE, max_lines=50000):
            try:
                rj = json.loads(line)
                dt = _parse_dt(rj.get("ts"))
                if not dt or dt.replace(tzinfo=None) < cutoff_naive: continue
                if chat_id_filter and str(rj.get("chat_id")) != chat_id_filter: continue
                
                rid = str(rj.get("reactor_user_id", "")).strip()
                if rid:
                    new_r = rj.get("new_reaction")
                    if isinstance(new_r, list) and len(new_r) > 0 and str(new_r[0]) != "()":
                        per_user[rid]["user_id"] = rid
                        per_user[rid]["likes_given"] += 1
                        total_reactions_given += 1
                        if not per_user[rid]["username"]: per_user[rid]["username"] = rj.get("reactor_username", "")
                        if not per_user[rid]["full_name"]: per_user[rid]["full_name"] = rj.get("reactor_full_name", "")
            except: continue

    # --- Step 2: Messages ---
    reg_list = load_user_registry_list()
    reg_map = {str(u.get("id")): u for u in reg_list if u.get("id")}

    for fp in _iter_message_files():
        for line in _tail_text_file(fp, max_lines=10000):
            try:
                m = json.loads(line)
                dt = _parse_dt(m.get("ts"))
                if not dt or dt.replace(tzinfo=None) < cutoff_naive: continue
                if chat_id_filter and str(m.get("chat_id")) != chat_id_filter: continue

                uid = _extract_user_id_from_msg(m)
                if not uid: continue

                total_messages += 1
                per_hour[dt.replace(tzinfo=None).hour] += 1
                per_weekday[dt.replace(tzinfo=None).weekday()] += 1
                dkey = dt.replace(tzinfo=None).date().isoformat()
                if dkey in labels: timeline_map[dkey] += 1
                
                cid = m.get("chat_id")
                if cid: per_chat[str(cid)] += 1

                has_media = bool(m.get("has_media"))
                if has_media: media_shared += 1

                l_rec = _extract_reactions_total(m)
                total_reactions_received += l_rec

                u = per_user[uid]
                u["user_id"] = uid
                u["messages"] += 1
                if has_media: u["media"] += 1
                u["likes_received"] += l_rec
                
                if not u["username"]: u["username"] = m.get("username", "") or reg_map.get(uid, {}).get("username", "")
                if not u["full_name"]: u["full_name"] = m.get("full_name", "") or m.get("name", "") or reg_map.get(uid, {}).get("full_name", "")
                
                if not u["last_seen"] or dt.replace(tzinfo=None) > u["last_seen"]: u["last_seen"] = dt.replace(tzinfo=None)
                if dkey in labels: u["daily"][dkey] += 1
            except: continue

    # --- Step 3: Leaderboard & KPIs ---
    leaderboard_list = sorted(per_user.values(), key=lambda x: x.get("messages", 0), reverse=True)
    leaderboard = []
    user_series = {}
    for idx, u in enumerate(leaderboard_list[:20], start=1):
        uid = u["user_id"]
        leaderboard.append({
            "rank": idx, "user_id": uid, "username": u["username"], "name": u["full_name"],
            "messages": u["messages"], "media": u["media"], 
            "likes_received": u["likes_received"], "likes_given": u["likes_given"],
            "avatar_url": f"/tg/avatar/{uid}"
        })
        user_series[uid] = [u["daily"].get(d, 0) for d in labels]

    top_chat = max(per_chat.items(), key=lambda x: x[1], default=(None,0))
    
    res = {
        "ok": True,
        "meta": {
            "days": days, "totalMessages": total_messages, "activeUsers": len(per_user),
            "mediaShared": media_shared, "totalReactions": total_reactions_received,
            "totalReactionsGiven": total_reactions_given,
            "busiest_day": max(timeline_map.items(), key=lambda x: x[1], default=(None,0))[0]
        },
        "kpis": {
            "total_messages": total_messages, "active_users": len(per_user),
            "media_shared": media_shared, "total_reactions_received": total_reactions_received,
            "total_reactions_given": total_reactions_given,
            "top_contributor": leaderboard[0]["name"] if leaderboard else "—",
            "most_liked_user": max(leaderboard, key=lambda x: x["likes_received"], default={"name":"—"})["name"],
            "top_chat": f"{top_chat[0]} ({top_chat[1]})" if top_chat[0] else "—"
        },
        "leaderboard": leaderboard,
        "timeline": [{"date": d, "count": timeline_map.get(d, 0)} for d in labels],
        "user_series": user_series,
        "busiest_hours": per_hour,
        "busiest_days": per_weekday
    }
    return res
"""

# Replace in app.py
pattern = r'def build_group_activity\(days: int = 30, chat_id=None\) -> dict:.*?return \{.*?\}'
app_content = re.sub(pattern, clean_func.strip(), app_content, flags=re.DOTALL)
with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

# 2. CLEAN FRONTEND JS
html_path = 'dashboard/src/id_finder_analytics.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# Update normalizePayload Mapping
html_content = re.sub(
    r'total_reactions:.*?,',
    'total_reactions: payload.kpis?.total_reactions_given ?? payload.meta?.totalReactionsGiven ?? 0,',
    html_content
)
html_content = re.sub(
    r'likes: Number\(r\.likes_given.*?\),',
    'likes: Number(r.likes_given ?? 0),',
    html_content
)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)
