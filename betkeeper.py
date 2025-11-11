import requests
import json
import os
import sys
import argparse
import webbrowser
import http.server
import socketserver

# --- put your own cookie values here, or you will be prompted on the command line---
SWID = "YOUR_SWID_HERE"
ESPN_S2 = "YOUR_ESPN_S2_HERE"
ONESITE_TOKEN = "YOUR_TOKEN_HERE"

MEMBER_FILE = "member_data.json"
WEEKS_FILE = "all_weeks_data.json"


def get_credentials():
    """Prompt user for ESPN credentials."""
    print("\n" + "=" * 70)
    print("ESPN CREDENTIALS REQUIRED")
    print("=" * 70)
    print("\nTo get your credentials:")
    print("1. Go to https://www.espn.com/fantasy/")
    print("2. Make sure you are signed in")
    print("3. Press F12 to open Developer Tools")
    print("4. Click on the 'Application' tab at the top")
    print("5. In the sidebar, expand 'Cookies' and click on 'https://www.espn.com'")
    print("6. Find and copy the values for:")
    print("   - SWID (include the curly brackets)")
    print("   - espn_s2")
    print("   - ESPN-ONESITE.WEB-PROD.token")
    print("\n" + "=" * 70 + "\n")
    
    try:
        swid = input("Enter SWID (with brackets) or 'quit' to exit: ").strip()
        if swid.lower() == 'quit':
            sys.exit(0)
            
        espn_s2 = input("Enter espn_s2 or 'quit' to exit: ").strip()
        if espn_s2.lower() == 'quit':
            sys.exit(0)
            
        onesite_token = input("Enter ESPN-ONESITE.WEB-PROD.token or 'quit' to exit: ").strip()
        if onesite_token.lower() == 'quit':
            sys.exit(0)
        
        return swid, espn_s2, onesite_token
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)

def fetch_member_data(cookies):
    """Fetch member picks data from ESPN API."""
    url = "https://gambit-api.fantasy.espn.com/apis/v1/challenges/265/members/?platform=chui&view=chui_default"
    
    try:
        response = requests.get(url, cookies=cookies)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print("\n" + "=" * 70)
            print("AUTHENTICATION ERROR (401)")
            print("=" * 70)
            print("\nYour credentials are incorrect or expired.")
            print("Please make sure you:")
            print("  • Are signed into ESPN Fantasy")
            print("  • Copied the FULL cookie values")
            print("  • SWID includes the curly brackets { }")
            print("  • Credentials are recent (they may expire)")
            print("=" * 70 + "\n")
            
            # Prompt for new credentials
            global SWID, ESPN_S2, ONESITE_TOKEN
            SWID, ESPN_S2, ONESITE_TOKEN = get_credentials()
            
            # Retry with new credentials
            new_cookies = {
                "SWID": SWID,
                "espn_s2": ESPN_S2,
                "ESPN-ONESITE.WEB-PROD.token": ONESITE_TOKEN
            }
            print("\nRetrying with new credentials...\n")
            response = requests.get(url, cookies=new_cookies)
            response.raise_for_status()
            return response.json()
        else:
            raise

def fetch_weeks_data(completed_weeks, cookies):
    """Fetch game data for all completed weeks."""
    url_template = "https://gambit-api.fantasy.espn.com/apis/v1/challenges/265/?scoringPeriodId={p}&view=chui_challenge_matchups&platform=chui"
    all_weeks_data = {}
    
    for week in completed_weeks:
        url = url_template.format(p=week)
        response = requests.get(url, cookies=cookies)
        response.raise_for_status()
        all_weeks_data[week] = response.json()
    
    return all_weeks_data


def load_cached_data():
    """Load data from cached JSON files if they exist."""
    if not os.path.exists(MEMBER_FILE) or not os.path.exists(WEEKS_FILE):
        return None, None
    
    with open(MEMBER_FILE) as f:
        member = json.load(f)
    
    with open(WEEKS_FILE) as f:
        all_weeks = json.load(f)
    
    return member, all_weeks


def save_data(member, all_weeks):
    """Save data to JSON files."""
    with open(MEMBER_FILE, "w") as f:
        json.dump(member, f, indent=2)
    
    with open(WEEKS_FILE, "w") as f:
        json.dump(all_weeks, f, indent=2)


def get_data(refetch=False):
    """Get data either from cache or by fetching."""
    cookies = {
        "SWID": SWID,
        "espn_s2": ESPN_S2,
        "ESPN-ONESITE.WEB-PROD.token": ONESITE_TOKEN
    }
    
    if not refetch:
        member, all_weeks = load_cached_data()
        if member and all_weeks:
            print("Using cached data...")
            return member, all_weeks
    
    print("Fetching data from ESPN...")
    
    # Fetch member data
    member = fetch_member_data(cookies)
    
    # Get completed weeks
    entries = member.get("entries", [])
    score_by_period = (entries[0].get("score", {}).get("scoreByPeriod", {}) if entries else {})
    completed_weeks = sorted(int(k) for k, v in score_by_period.items() if (v or {}).get("score", 0) > 0)
    
    print(f"Found {len(completed_weeks)} completed weeks")
    
    # Fetch weeks data
    all_weeks = fetch_weeks_data(completed_weeks, cookies)
    
    # Save to cache
    save_data(member, all_weeks)
    print("Data cached successfully")
    
    return member, all_weeks


def calculate_profit(pick, all_weeks_data, bet_amount=100):
    """Calculate profit/loss for a single pick."""
    your_outcome_id = pick['outcomesPicked'][0]['outcomeId']
    your_result = pick['outcomesPicked'][0]['result']
    prop_id = pick['propositionId']
    
    # Find the game
    matching_prop = None
    for week_data in all_weeks_data.values():
        for prop in week_data["propositions"]:
            if prop["id"] == prop_id:
                matching_prop = prop
                break
        if matching_prop:
            break
    
    if not matching_prop:
        return None
    
    # Find the team picked
    your_team = None
    for outcome in matching_prop["possibleOutcomes"]:
        if outcome["id"] == your_outcome_id:
            your_team = outcome
            break
    
    if not your_team:
        return None
    
    # Extract betting line
    betting_line = None
    for mapping in your_team["mappings"]:
        if mapping["type"] == "BETTING_LINE":
            betting_line = mapping["value"]
            break
    
    if not betting_line:
        return None
    
    # Calculate profit
    line = int(betting_line)
    if line < 0:
        profit = bet_amount * (100 / abs(line))
    else:
        profit = bet_amount * (line / 100)
    
    # Return profit or loss
    if your_result == "CORRECT":
        return profit
    else:
        return -bet_amount


def analyze_picks(member, all_weeks_data, bet_amount=100):
    """Analyze all picks and calculate statistics."""
    all_picks = member["entries"][0]["picks"]
    
    wins = 0
    losses = 0
    total_profit = 0
    total_winnings = 0
    total_losses = 0
    
    for pick in all_picks:
        profit = calculate_profit(pick, all_weeks_data, bet_amount)
        
        if profit is None:
            continue
        
        total_profit += profit
        
        if profit > 0:
            wins += 1
            total_winnings += profit
        else:
            losses += 1
            total_losses += abs(profit)
    
    return {
        "total_picks": wins + losses,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / (wins + losses) * 100 if (wins + losses) > 0 else 0,
        "total_winnings": total_winnings,
        "total_losses": total_losses,
        "net_profit": total_profit,
        "roi": (total_profit / (bet_amount * (wins + losses))) * 100 if (wins + losses) > 0 else 0
    }


def print_summary(stats):
    """Print summary statistics."""
    print("\n" + "=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print(f"Total Picks: {stats['total_picks']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Win Rate: {stats['win_rate']:.1f}%")
    print()
    print(f"Total Winnings: ${stats['total_winnings']:.2f}")
    print(f"Total Losses: ${stats['total_losses']:.2f}")
    print(f"NET PROFIT: ${stats['net_profit']:.2f}")
    print()
    print(f"ROI: {stats['roi']:.1f}%")
    print("=" * 70)


def calculate_line_range_stats(member, all_weeks_data, bet_amount=100):
    """Calculate performance by betting line ranges."""
    line_ranges = {
        'heavy_favorites': {'range': '≤ -200', 'min': -9999, 'max': -200, 'wins': 0, 'losses': 0, 'profit': 0},
        'favorites': {'range': '-199 to -110', 'min': -199, 'max': -110, 'wins': 0, 'losses': 0, 'profit': 0},
        'slight_underdogs': {'range': '+110 to +199', 'min': 110, 'max': 199, 'wins': 0, 'losses': 0, 'profit': 0},
        'big_underdogs': {'range': '≥ +200', 'min': 200, 'max': 9999, 'wins': 0, 'losses': 0, 'profit': 0}
    }
    
    all_picks = member["entries"][0]["picks"]
    
    for pick in all_picks:
        profit = calculate_profit(pick, all_weeks_data, bet_amount)
        if profit is None:
            continue
        
        your_outcome_id = pick['outcomesPicked'][0]['outcomeId']
        prop_id = pick['propositionId']
        
        matching_prop = None
        for week_data in all_weeks_data.values():
            for prop in week_data["propositions"]:
                if prop["id"] == prop_id:
                    matching_prop = prop
                    break
            if matching_prop:
                break
        
        if not matching_prop:
            continue
        
        your_team = None
        for outcome in matching_prop["possibleOutcomes"]:
            if outcome["id"] == your_outcome_id:
                your_team = outcome
                break
        
        if not your_team:
            continue
        
        betting_line = None
        for mapping in your_team["mappings"]:
            if mapping["type"] == "BETTING_LINE":
                betting_line = mapping["value"]
                break
        
        if not betting_line:
            continue
        
        line = int(betting_line)
        
        # Categorize by line range
        for category, data in line_ranges.items():
            if line < 0:  # Favorites
                if data['max'] < 0 and data['min'] <= line <= data['max']:
                    data['profit'] += profit
                    if profit > 0:
                        data['wins'] += 1
                    else:
                        data['losses'] += 1
                    break
            else:  # Underdogs
                if data['min'] > 0 and data['min'] <= line <= data['max']:
                    data['profit'] += profit
                    if profit > 0:
                        data['wins'] += 1
                    else:
                        data['losses'] += 1
                    break
    
    return line_ranges


def calculate_streak_stats(member, all_weeks_data, bet_amount=100):
    """Calculate winning/losing streaks."""
    all_picks = member["entries"][0]["picks"]
    
    picks_with_results = []
    for pick in all_picks:
        profit = calculate_profit(pick, all_weeks_data, bet_amount)
        if profit is not None:
            picks_with_results.append({
                'profit': profit,
                'won': profit > 0
            })
    
    current_streak = 0
    current_streak_type = None
    longest_win_streak = 0
    longest_lose_streak = 0
    
    for pick in picks_with_results:
        if pick['won']:
            if current_streak_type == 'win':
                current_streak += 1
            else:
                current_streak = 1
                current_streak_type = 'win'
            longest_win_streak = max(longest_win_streak, current_streak)
        else:
            if current_streak_type == 'loss':
                current_streak += 1
            else:
                current_streak = 1
                current_streak_type = 'loss'
            longest_lose_streak = max(longest_lose_streak, current_streak)
    
    return {
        'current_streak': current_streak if current_streak_type else 0,
        'current_streak_type': current_streak_type if current_streak_type else 'none',
        'longest_win_streak': longest_win_streak,
        'longest_lose_streak': longest_lose_streak
    }


def calculate_weekly_stats(member, all_weeks_data, bet_amount=100):
    """Calculate weekly performance details."""
    all_picks = member["entries"][0]["picks"]
    weekly_data = {}
    
    for pick in all_picks:
        profit = calculate_profit(pick, all_weeks_data, bet_amount)
        if profit is None:
            continue
        
        # Find the proposition to get the week
        prop_id = pick['propositionId']
        week = None
        
        for week_num, week_data in all_weeks_data.items():
            for prop in week_data["propositions"]:
                if prop["id"] == prop_id:
                    week = week_num
                    break
            if week:
                break
        
        if week is None:
            continue
        
        if week not in weekly_data:
            weekly_data[week] = {
                'week': week,
                'wins': 0,
                'losses': 0,
                'profit': 0
            }
        
        weekly_data[week]['profit'] += profit
        if profit > 0:
            weekly_data[week]['wins'] += 1
        else:
            weekly_data[week]['losses'] += 1
    
    weekly_list = sorted(weekly_data.values(), key=lambda x: x['week'])
    
    return weekly_list


def simulate_bankroll_strategies(member, all_weeks_data, starting_bankroll=1000):
    """Simulate different bankroll management strategies."""
    all_picks = member["entries"][0]["picks"]
    
    # Get all picks with their data (only CORRECT/INCORRECT, not UNDECIDED)
    picks_data = []
    for pick in all_picks:
        your_outcome_id = pick['outcomesPicked'][0]['outcomeId']
        your_result = pick['outcomesPicked'][0]['result']
        
        # Skip undecided picks
        if your_result == "UNDECIDED":
            continue
        
        prop_id = pick['propositionId']
        
        # Find the proposition
        matching_prop = None
        for week_data in all_weeks_data.values():
            for prop in week_data["propositions"]:
                if prop["id"] == prop_id:
                    matching_prop = prop
                    break
            if matching_prop:
                break
        
        if not matching_prop:
            continue
        
        # Find the outcome picked
        your_team = None
        for outcome in matching_prop["possibleOutcomes"]:
            if outcome["id"] == your_outcome_id:
                your_team = outcome
                break
        
        if not your_team:
            continue
        
        # Extract betting line
        betting_line = None
        for mapping in your_team["mappings"]:
            if mapping["type"] == "BETTING_LINE":
                betting_line = mapping["value"]
                break
        
        if not betting_line:
            continue
        
        line = int(betting_line)
        won = your_result == "CORRECT"
        
        picks_data.append({
            'line': line,
            'won': won
        })
    
    if len(picks_data) == 0:
        print("Warning: No completed picks data found for bankroll simulation!")
        return []
    
    print(f"Simulating bankroll strategies for {len(picks_data)} completed picks...")
    
    # Calculate historical performance by line category for confidence-based strategy
    line_performance = {
        'heavy_favorites': {'wins': 0, 'total': 0, 'roi': -5.0},  # From your data
        'favorites': {'wins': 0, 'total': 0, 'roi': 12.3},
        'slight_underdogs': {'wins': 0, 'total': 0, 'roi': 18.9},
        'big_underdogs': {'wins': 0, 'total': 0, 'roi': 0}
    }
    
    for pick in picks_data:
        line = pick['line']
        won = pick['won']
        
        if line <= -200:
            category = 'heavy_favorites'
        elif -199 <= line <= -110:
            category = 'favorites'
        elif 110 <= line <= 199:
            category = 'slight_underdogs'
        else:
            category = 'big_underdogs'
        
        line_performance[category]['total'] += 1
        if won:
            line_performance[category]['wins'] += 1
    
    # Initialize strategies
    strategies = {
        'flat_betting': {
            'name': 'Flat Betting ($100)',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        },
        'fixed_percentage': {
            'name': 'Fixed 5% of Bankroll',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        },
        'conservative_percentage': {
            'name': 'Conservative 1% of Bankroll',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        },
        'kelly_criterion': {
            'name': 'Kelly Criterion',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        },
        'martingale': {
            'name': 'Martingale (Double on Loss)',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0,
            'current_bet': 100,
            'base_bet': 100
        },
        'anti_martingale': {
            'name': 'Anti-Martingale (Double on Win)',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0,
            'current_bet': 100,
            'base_bet': 100
        },
        'unit_based': {
            'name': 'Unit-Based on Line',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        },
        'confidence_based': {
            'name': 'Confidence-Based (ROI Weighted)',
            'bankroll': starting_bankroll,
            'history': [starting_bankroll],
            'peak': starting_bankroll,
            'lowest': starting_bankroll,
            'max_drawdown': 0
        }
    }
    
    # Calculate win rate for Kelly
    total_wins = sum(1 for p in picks_data if p['won'])
    win_rate = total_wins / len(picks_data)
    
    # Simulate each strategy
    for pick in picks_data:
        line = pick['line']
        won = pick['won']
        
        # Calculate decimal odds
        if line < 0:
            decimal_odds = 1 + (100 / abs(line))
        else:
            decimal_odds = 1 + (line / 100)
        
        # Determine line category
        if line <= -200:
            line_category = 'heavy_favorites'
        elif -199 <= line <= -110:
            line_category = 'favorites'
        elif 110 <= line <= 199:
            line_category = 'slight_underdogs'
        else:
            line_category = 'big_underdogs'
        
        for strategy_name, strategy in strategies.items():
            bankroll = strategy['bankroll']
            
            # Skip if bankroll is depleted
            if bankroll <= 0:
                strategy['history'].append(0)
                continue
            
            # Determine bet size based on strategy
            if strategy_name == 'flat_betting':
                bet_size = min(100, bankroll)
                
            elif strategy_name == 'fixed_percentage':
                bet_size = bankroll * 0.05  # 5%
                
            elif strategy_name == 'conservative_percentage':
                bet_size = bankroll * 0.01  # 1%
                
            elif strategy_name == 'kelly_criterion':
                # Kelly formula: f = (bp - q) / b
                b = decimal_odds - 1
                p = win_rate
                q = 1 - p
                kelly_fraction = (b * p - q) / b if b > 0 else 0
                
                # Use half-Kelly for safety
                kelly_fraction = kelly_fraction * 0.5
                
                # Clamp between 0 and 0.25 (max 25% of bankroll)
                kelly_fraction = max(0, min(kelly_fraction, 0.25))
                
                bet_size = bankroll * kelly_fraction
                
            elif strategy_name == 'martingale':
                # Double bet after loss, reset after win
                bet_size = min(strategy['current_bet'], bankroll)
                
            elif strategy_name == 'anti_martingale':
                # Double bet after win, reset after loss
                bet_size = min(strategy['current_bet'], bankroll)
                
            elif strategy_name == 'unit_based':
                # Base unit = 1% of starting bankroll ($10)
                base_unit = starting_bankroll * 0.01
                
                # Adjust units based on line category
                if line_category == 'heavy_favorites':
                    units = 0.5  # Bet less on heavy favorites (you lose here)
                elif line_category == 'favorites':
                    units = 1.0  # Standard bet (your best category)
                elif line_category == 'slight_underdogs':
                    units = 1.5  # Bet more on slight underdogs (high ROI)
                else:
                    units = 0.5  # Minimal on big underdogs
                
                bet_size = min(base_unit * units, bankroll)
                
            elif strategy_name == 'confidence_based':
                # Base bet = 2% of bankroll
                base_bet = bankroll * 0.02
                
                # Get ROI for this category
                category_roi = line_performance[line_category]['roi']
                
                # Scale bet size based on ROI
                if category_roi > 15:
                    multiplier = 2.0  # Double on high confidence
                elif category_roi > 5:
                    multiplier = 1.5
                elif category_roi > 0:
                    multiplier = 1.0
                elif category_roi > -5:
                    multiplier = 0.5
                else:
                    multiplier = 0.25  # Minimal bet on losing categories
                
                bet_size = min(base_bet * multiplier, bankroll)
            
            # Ensure bet size is reasonable
            bet_size = min(bet_size, bankroll)
            bet_size = max(bet_size, 0)
            
            # Calculate profit/loss
            if won:
                profit = bet_size * (decimal_odds - 1)
            else:
                profit = -bet_size
            
            # Update bankroll
            strategy['bankroll'] += profit
            strategy['history'].append(strategy['bankroll'])
            
            # Update martingale bet sizes
            if strategy_name == 'martingale':
                if won:
                    strategy['current_bet'] = strategy['base_bet']  # Reset on win
                else:
                    strategy['current_bet'] = min(strategy['current_bet'] * 2, bankroll)  # Double on loss
                    
            elif strategy_name == 'anti_martingale':
                if won:
                    strategy['current_bet'] = min(strategy['current_bet'] * 2, bankroll * 0.25)  # Double on win, max 25%
                else:
                    strategy['current_bet'] = strategy['base_bet']  # Reset on loss
            
            # Update peak, lowest, and max drawdown
            strategy['peak'] = max(strategy['peak'], strategy['bankroll'])
            strategy['lowest'] = min(strategy['lowest'], strategy['bankroll'])
            drawdown = strategy['peak'] - strategy['bankroll']
            strategy['max_drawdown'] = max(strategy['max_drawdown'], drawdown)
    
    # Format output
    strategies_output = []
    for strategy_name, strategy in strategies.items():
        ending_bankroll = strategy['bankroll']
        profit = ending_bankroll - starting_bankroll
        roi = (profit / starting_bankroll) * 100
        
        strategies_output.append({
            'name': strategy['name'],
            'strategy_key': strategy_name,
            'starting_bankroll': starting_bankroll,
            'ending_bankroll': round(ending_bankroll, 2),
            'profit': round(profit, 2),
            'roi': round(roi, 1),
            'peak_bankroll': round(strategy['peak'], 2),
            'lowest_point': round(strategy['lowest'], 2),
            'max_drawdown': round(strategy['max_drawdown'], 2),
            'history': [round(h, 2) for h in strategy['history']]
        })
    
    return strategies_output


def export_stats_to_json(stats, member, all_weeks_data, bet_amount=100):
    """Export comprehensive stats to JSON file."""
    
    line_range_stats = calculate_line_range_stats(member, all_weeks_data, bet_amount)
    streak_stats = calculate_streak_stats(member, all_weeks_data, bet_amount)
    weekly_stats = calculate_weekly_stats(member, all_weeks_data, bet_amount)
    bankroll_strategies = simulate_bankroll_strategies(member, all_weeks_data)
    
    all_picks = member["entries"][0]["picks"]
    all_profits = []
    for pick in all_picks:
        profit = calculate_profit(pick, all_weeks_data, bet_amount)
        if profit is not None:
            all_profits.append(profit)
    
    wins_only = [p for p in all_profits if p > 0]
    losses_only = [p for p in all_profits if p < 0]
    
    # Format line range stats
    line_ranges_export = []
    for category, data in line_range_stats.items():
        total_bets = data['wins'] + data['losses']
        line_ranges_export.append({
            'category': category,
            'range': data['range'],
            'total_bets': total_bets,
            'wins': data['wins'],
            'losses': data['losses'],
            'win_rate': round((data['wins'] / total_bets * 100), 1) if total_bets > 0 else 0,
            'profit': round(data['profit'], 2),
            'roi': round((data['profit'] / (bet_amount * total_bets) * 100), 1) if total_bets > 0 else 0
        })
    
    # Build stats object
    output = {
        'overall': {
            'total_picks': stats['total_picks'],
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(stats['win_rate'], 1),
            'total_winnings': round(stats['total_winnings'], 2),
            'total_losses': round(stats['total_losses'], 2),
            'net_profit': round(stats['net_profit'], 2),
            'roi': round(stats['roi'], 1),
            'avg_win': round(sum(wins_only) / len(wins_only), 2) if wins_only else 0,
            'avg_loss': round(sum(losses_only) / len(losses_only), 2) if losses_only else 0,
            'biggest_win': round(max(all_profits), 2) if all_profits else 0,
            'biggest_loss': round(min(all_profits), 2) if all_profits else 0
        },
        'by_line_range': line_ranges_export,
        'weekly': weekly_stats,
        'streaks': streak_stats,
        'bankroll_strategies': bankroll_strategies
    }
    
    # Write to JSON
    with open('stats_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    return 'stats_output.json'


def main():
    """
    Main entry point for the betting stats script.

    Command-line arguments:
        --refetch : Optional flag that forces data to be re-fetched instead of
                    using cached data. Useful when the source data may have changed
                    or needs to be refreshed.
    """
    parser = argparse.ArgumentParser(description="Analyze and export betting stats.")
    parser.add_argument(
        "--refetch",
        action="store_true",
        help="Force data to be re-fetched instead of using cached data. (needs to be done for new weeks)"
    )
    args = parser.parse_args()
    refetch = args.refetch
    
    member, all_weeks = get_data(refetch=refetch)
    
    print("\nCalculating betting results...")
    stats = analyze_picks(member, all_weeks)
    
    print_summary(stats)
    
    print("\nExporting stats to JSON...")
    json_file = export_stats_to_json(stats, member, all_weeks)
    print(f"✓ Stats exported to: {json_file}")

    print("\nStarting local server...")
    PORT = 8000
    webbrowser.open(f'http://localhost:{PORT}/dashboard.html')

    # Start server (this will block)
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Server running at http://localhost:{PORT}")
        print("Press Ctrl+C to stop the server")
        httpd.serve_forever()


if __name__ == "__main__":
    main()