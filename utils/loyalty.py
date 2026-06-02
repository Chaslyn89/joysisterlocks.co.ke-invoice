# utils/loyalty.py
"""Loyalty program utilities: stars, rewards, messages"""

def calculate_loyalty_stars(visits, stars_max=5):
    """Calculate stars for loyalty display (1 star per 2 visits, max 5)"""
    if not visits:
        visits = 0
    stars_count = min(stars_max, visits // 2)
    return "⭐" * stars_count

def calculate_visits_until_reward(visits, visits_for_reward=5):
    """Calculate visits until next reward"""
    if not visits:
        visits = 0
    remainder = visits % visits_for_reward
    if remainder == 0:
        return 0
    return visits_for_reward - remainder

def get_reward_message(visits, visits_for_reward=5, reward_description="FREE Wash & Style"):
    """Get loyalty reward message based on visit count"""
    visits = visits or 0
    remaining = visits_for_reward - (visits % visits_for_reward)
    
    if remaining == 0:
        return f"🎉 You've earned a {reward_description} on your next visit! 🎉"
    elif remaining == 1:
        return f"⭐ 1 more visit until a {reward_description}!"
    else:
        return f"⭐ {remaining} more visits until a {reward_description}!"

def get_loyalty_progress(visits, visits_for_reward=5):
    """Get loyalty progress as percentage"""
    if not visits:
        visits = 0
    progress = (visits % visits_for_reward) / visits_for_reward * 100
    return min(100, progress)