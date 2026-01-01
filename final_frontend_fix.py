
import os

path = 'dashboard/src/id_finder_analytics.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update normalizePayload to be absolutely sure about mapping
old_mapping = 'likes: Number(r.likes_given ?? r.reactions ?? r.likes ?? 0),'
new_mapping = 'likes: Number(r.likes_given ?? r.likes_received ?? r.likes ?? 0),'
content = content.replace(old_mapping, new_mapping)

# 2. Update renderLeaderboard to use the correct 'likes' property
# The previous version might have been manually changed to r.likes_given which is undefined after normalization
content = content.replace(
    '<td class="text-end">${fmtNumber(r.likes_given || 0)}</td>',
    '<td class="text-end">${fmtNumber(r.likes || 0)}</td>'
)

# 3. Increase column width for "Reaktionen" and fix table layout
# Find the CSS block
css_to_replace = """        .ga-leaderboard-table { table-layout: fixed; min-width: 750px !important; }
        .ga-col-rank { width: 60px; }
        .ga-col-user { width: auto; }
        .ga-col-msg { width: 100px; }
        .ga-col-media { width: 100px; }
        .ga-col-react { width: 150px; }"""

new_css = """        .ga-leaderboard-table { table-layout: fixed; width: 100%; border-collapse: collapse; }
        .ga-col-rank { width: 50px; }
        .ga-col-user { width: 40%; }
        .ga-col-msg { width: 80px; }
        .ga-col-media { width: 80px; }
        .ga-col-react { width: 110px; }
        .ga-leaderboard-table td, .ga-leaderboard-table th { 
            white-space: nowrap; 
            overflow: hidden; 
            text-overflow: ellipsis; 
        }"""

if css_to_replace in content:
    content = content.replace(css_to_replace, new_css)
else:
    # Fallback: find any style tag and inject
    content = content.replace('</style>', new_css + '\n    </style>')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
