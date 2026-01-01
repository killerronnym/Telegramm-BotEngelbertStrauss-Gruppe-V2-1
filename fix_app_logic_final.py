
import os
import re

path = 'dashboard/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Correct the reaction counting logic in build_group_activity
# The previous check "()" not in nr was failing because ReactionTypeEmoji(...) contains parentheses.
new_logic = """
                rid = str(rj.get("reactor_user_id", "")).strip()
                if rid:
                    new_r = rj.get("new_reaction")
                    if isinstance(new_r, list) and len(new_r) > 0:
                        nr_str = str(new_r[0])
                        # A valid reaction string looks like "(ReactionTypeEmoji(emoji='👍', ...))"
                        # A removal looks like "()"
                        if nr_str != "()" and ("emoji=" in nr_str or "ReactionType" in nr_str):
                            per_user[rid]["user_id"] = rid
                            per_user[rid]["likes_given"] += 1
                            total_reactions_given += 1
                            
                            if not per_user[rid].get("username"):
                                per_user[rid]["username"] = rj.get("reactor_username", "")
                            if not per_user[rid].get("full_name"):
                                per_user[rid]["full_name"] = rj.get("reactor_full_name", "")
"""

# Find the block and replace it
# Match from 'rid = str(rj.get("reactor_user_id"' to 'reactor_full_name", "")'
pattern = r'rid = str\(rj\.get\("reactor_user_id".*?rj\.get\("reactor_full_name", ""\)'
content = re.sub(pattern, new_logic.strip(), content, flags=re.DOTALL)

# 2. Ensure total_reactions_given is correctly mapped in the return dictionary
# Check if total_reactions_given is used in kpis
if '"total_reactions_given": int(total_reactions_given),' not in content:
    # If I previously replaced it with 999, fix it back to the variable
    content = content.replace('"total_reactions_given": 999,', '"total_reactions_given": int(total_reactions_given),')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
