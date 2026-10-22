import requests
import json
import os
import time
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

# Cache files
TRADE_VALUES_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_values_cache.json")
CACHE_TTL_SECONDS = 10800  # 3 hours

def _normalize_name(name: str) -> str:
    """Normalize player names for fuzzy cross-source matching."""
    if not name:
        return ""
    clean = name.lower()
    for char in [".", "'", "-", " jr", " sr", " ii", " iii", " iv"]:
        clean = clean.replace(char, "")
    return clean.strip()

def fetch_market_values(is_dynasty: bool = True, num_qbs: int = 1, ppr: float = 1.0) -> Dict[str, Any]:
    """
    Fetch market trade values from FantasyCalc and KeepTradeCut.
    Returns:
        dict with:
            'by_sleeper_id': {id: player_dict}
            'by_name': {norm_name: player_dict}
            'draft_picks': [pick_dict]
            'meta': {'source': 'FantasyCalc & KTC', 'last_updated': ...}
    """
    now = time.time()
    # Check cache
    cache_key = f"{'dynasty' if is_dynasty else 'redraft'}_{num_qbs}qb"
    if os.path.exists(TRADE_VALUES_CACHE):
        try:
            with open(TRADE_VALUES_CACHE, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                if cache_key in cached_data:
                    entry = cached_data[cache_key]
                    if now - entry.get('timestamp', 0) < CACHE_TTL_SECONDS:
                        return entry.get('payload', {})
        except Exception as e:
            print(f"Error reading trade values cache: {e}")

    by_sleeper_id = {}
    by_name = {}
    draft_picks = []

    # 1. Fetch from FantasyCalc API
    try:
        fc_url = f"https://api.fantasycalc.com/values/current?isDynasty={'true' if is_dynasty else 'false'}&numQbs={num_qbs}&ppr={int(ppr) if ppr in [0, 1] else ppr}"
        fc_res = requests.get(fc_url, timeout=10)
        if fc_res.status_code == 200:
            fc_json = fc_res.json()
            for item in fc_json:
                p = item.get("player", {})
                name = p.get("name", "")
                norm = _normalize_name(name)
                s_id = str(p.get("sleeperId") or "")
                val = item.get("value", 0)
                
                # Check if this item is a rookie draft pick
                if "1st" in name or "2nd" in name or "3rd" in name or "4th" in name:
                    draft_picks.append({
                        "name": name,
                        "value": val,
                        "trend30Day": item.get("trend30Day", 0)
                    })
                    continue

                info = {
                    "name": name,
                    "norm_name": norm,
                    "position": p.get("position", ""),
                    "team": p.get("maybeTeam", ""),
                    "age": p.get("maybeAge"),
                    "sleeper_id": s_id,
                    "espn_id": str(p.get("espnId") or ""),
                    "value": val,
                    "redraft_value": item.get("redraftValue", val),
                    "overall_rank": item.get("overallRank"),
                    "pos_rank": item.get("positionRank"),
                    "trend30Day": item.get("trend30Day", 0),
                    "source": "FantasyCalc"
                }

                if s_id and s_id != "None":
                    by_sleeper_id[s_id] = info
                if norm:
                    by_name[norm] = info
    except Exception as e:
        print(f"FantasyCalc fetch error: {e}")

    # 2. Complementary KTC feed (DynastyProcess) for dynasty consensus cross-referencing
    if is_dynasty:
        try:
            ktc_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv"
            ktc_res = requests.get(ktc_url, timeout=8)
            if ktc_res.status_code == 200:
                lines = ktc_res.text.strip().split("\n")
                if len(lines) > 1:
                    headers = [h.strip('"') for h in lines[0].split(",")]
                    # Map headers
                    p_idx = headers.index("player") if "player" in headers else 0
                    v_idx = headers.index("value_2qb" if num_qbs > 1 else "value_1qb") if ("value_1qb" in headers) else -1
                    age_idx = headers.index("age") if "age" in headers else -1

                    for line in lines[1:]:
                        parts = [p.strip('"') for p in line.split(",")]
                        if len(parts) > p_idx:
                            k_name = parts[p_idx]
                            k_norm = _normalize_name(k_name)
                            k_val = int(parts[v_idx]) if v_idx != -1 and parts[v_idx].isdigit() else 0
                            
                            # If pick
                            if ("1st" in k_name or "2nd" in k_name or "3rd" in k_name) and not any(p["name"] == k_name for p in draft_picks):
                                draft_picks.append({
                                    "name": k_name,
                                    "value": k_val,
                                    "trend30Day": 0
                                })
                            elif k_norm in by_name:
                                # Blend with FantasyCalc for consensus
                                existing = by_name[k_norm]
                                existing["ktc_value"] = k_val
                                existing["consensus_value"] = round((existing["value"] + k_val) / 2)
                                if not existing.get("age") and age_idx != -1:
                                    try:
                                        existing["age"] = float(parts[age_idx])
                                    except:
                                        pass
                            elif k_norm:
                                by_name[k_norm] = {
                                    "name": k_name,
                                    "norm_name": k_norm,
                                    "position": parts[headers.index("pos")] if "pos" in headers else "",
                                    "team": parts[headers.index("team")] if "team" in headers else "",
                                    "age": float(parts[age_idx]) if age_idx != -1 and parts[age_idx].replace('.','',1).isdigit() else None,
                                    "value": k_val,
                                    "consensus_value": k_val,
                                    "trend30Day": 0,
                                    "source": "KTC"
                                }
        except Exception as e:
            print(f"KTC load error: {e}")

    # Fallback to standard value if consensus not set
    for item in by_name.values():
        if "consensus_value" not in item:
            item["consensus_value"] = item.get("value", 0)

    payload = {
        "by_sleeper_id": by_sleeper_id,
        "by_name": by_name,
        "draft_picks": sorted(draft_picks, key=lambda x: x["value"], reverse=True),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    # Save to cache
    try:
        all_cache = {}
        if os.path.exists(TRADE_VALUES_CACHE):
            try:
                with open(TRADE_VALUES_CACHE, 'r', encoding='utf-8') as f:
                    all_cache = json.load(f)
            except:
                pass
        all_cache[cache_key] = {"timestamp": now, "payload": payload}
        with open(TRADE_VALUES_CACHE, 'w', encoding='utf-8') as f:
            json.dump(all_cache, f)
    except Exception as e:
        print(f"Error writing trade cache: {e}")

    return payload

def get_player_trade_value(player_id_or_name: str, market_data: Dict[str, Any], is_dynasty: bool = True) -> Dict[str, Any]:
    """Lookup market value for a given player ID or name."""
    by_id = market_data.get("by_sleeper_id", {})
    by_name = market_data.get("by_name", {})
    
    # 1. Try by sleeper ID
    pid = str(player_id_or_name)
    if pid in by_id:
        return by_id[pid]
        
    # 2. Try by normalized name
    norm = _normalize_name(player_id_or_name)
    if norm in by_name:
        return by_name[norm]
        
    # Fallback default
    return {
        "name": str(player_id_or_name),
        "norm_name": norm,
        "position": "—",
        "team": "—",
        "age": None,
        "value": 500 if is_dynasty else 200,
        "consensus_value": 500 if is_dynasty else 200,
        "trend30Day": 0,
        "source": "Estimated"
    }

POS_ORDER = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DEF": 6, "DST": 6}

def sort_roster_by_position_and_value(
    pids: List[str],
    players_meta: Dict[str, Any],
    market_data: Dict[str, Any],
    is_dynasty: bool = True
) -> List[Dict[str, Any]]:
    """
    Groups roster players by position hierarchy (QB -> RB -> WR -> TE -> K -> DEF)
    and sorts players within each position from highest market trade value to lowest.
    """
    parsed = []
    for pid in pids:
        p_str = str(pid)
        p_meta = players_meta.get(p_str, {}) if isinstance(players_meta, dict) else {}
        p_name = p_meta.get('name') or p_meta.get('full_name') or p_str
        pos = p_meta.get('pos') or p_meta.get('position', '—')
        team = p_meta.get('team') or '—'
        val_info = get_player_trade_value(p_str if p_str in market_data.get('by_sleeper_id', {}) else p_name, market_data, is_dynasty)
        val = val_info.get("consensus_value", val_info.get("value", 0))
        age = val_info.get("age")
        trend = val_info.get("trend30Day", 0)

        parsed.append({
            "id": p_str,
            "name": p_name,
            "pos": pos,
            "team": team,
            "val": val,
            "age": age,
            "trend": trend,
            "priority": POS_ORDER.get(pos, 99)
        })

    # Sort primarily by position priority, then by value descending, then by name
    parsed.sort(key=lambda x: (x["priority"], -x["val"], x["name"]))
    return parsed

def evaluate_trade(
    team_a_name: str,
    team_b_name: str,
    team_a_roster: List[str],
    team_b_roster: List[str],
    team_a_sends: List[str],
    team_b_sends: List[str],
    picks_a_sends: List[Dict[str, Any]],
    picks_b_sends: List[Dict[str, Any]],
    is_dynasty: bool,
    market_data: Dict[str, Any],
    players_meta: Dict[str, Any],
    projections: pd.DataFrame,
    comp_data: pd.DataFrame,
    roster_positions: List[str],
    build_optimal_lineup_func
) -> Dict[str, Any]:
    """
    Complete trade analysis combining Market Equity with Starting Lineup EV Delta.
    """
    # 1. Evaluate Market Values Sent / Received
    team_a_gives_assets = []
    for pid in team_a_sends:
        p_name = players_meta.get(pid, {}).get('name') or pid if isinstance(players_meta, dict) else pid
        val_info = get_player_trade_value(pid if pid in market_data.get('by_sleeper_id', {}) else p_name, market_data, is_dynasty)
        team_a_gives_assets.append({
            "id": pid,
            "name": val_info.get("name", p_name),
            "pos": val_info.get("position", ""),
            "age": val_info.get("age"),
            "value": val_info.get("consensus_value", val_info.get("value", 0)),
            "trend": val_info.get("trend30Day", 0)
        })
    for pick in picks_a_sends:
        team_a_gives_assets.append({
            "id": pick["name"],
            "name": pick["name"],
            "pos": "PICK",
            "age": None,
            "value": pick.get("value", 0),
            "trend": pick.get("trend30Day", 0)
        })

    team_b_gives_assets = []
    for pid in team_b_sends:
        p_name = players_meta.get(pid, {}).get('name') or pid if isinstance(players_meta, dict) else pid
        val_info = get_player_trade_value(pid if pid in market_data.get('by_sleeper_id', {}) else p_name, market_data, is_dynasty)
        team_b_gives_assets.append({
            "id": pid,
            "name": val_info.get("name", p_name),
            "pos": val_info.get("position", ""),
            "age": val_info.get("age"),
            "value": val_info.get("consensus_value", val_info.get("value", 0)),
            "trend": val_info.get("trend30Day", 0)
        })
    for pick in picks_b_sends:
        team_b_gives_assets.append({
            "id": pick["name"],
            "name": pick["name"],
            "pos": "PICK",
            "age": None,
            "value": pick.get("value", 0),
            "trend": pick.get("trend30Day", 0)
        })

    val_a_sends = sum(a["value"] for a in team_a_gives_assets)
    val_b_sends = sum(b["value"] for b in team_b_gives_assets)
    market_diff_a = val_b_sends - val_a_sends  # Positive means Team A gains value
    
    # Fairness Percentage
    max_val = max(val_a_sends, val_b_sends)
    min_val = min(val_a_sends, val_b_sends)
    fairness_pct = round((min_val / max_val * 100), 1) if max_val > 0 else 100.0

    # Age Shift
    ages_a_sends = [a["age"] for a in team_a_gives_assets if a["age"] is not None]
    ages_b_sends = [b["age"] for b in team_b_gives_assets if b["age"] is not None]
    avg_age_a_sends = round(sum(ages_a_sends) / len(ages_a_sends), 1) if ages_a_sends else None
    avg_age_b_sends = round(sum(ages_b_sends) / len(ages_b_sends), 1) if ages_b_sends else None

    # 2. Starting Lineup Impact Simulation (True Lineup Delta)
    # Team A:
    roster_a_before = list(team_a_roster)
    roster_a_after = [p for p in roster_a_before if p not in team_a_sends] + team_b_sends
    
    opt_a_before = build_optimal_lineup_func(roster_a_before, players_meta, projections, comp_data, roster_positions)
    opt_a_after = build_optimal_lineup_func(roster_a_after, players_meta, projections, comp_data, roster_positions)
    
    score_a_before = sum(slot['player']['points'] for slot in opt_a_before if slot['player'])
    score_a_after = sum(slot['player']['points'] for slot in opt_a_after if slot['player'])
    delta_score_a = round(score_a_after - score_a_before, 2)

    # Team B:
    roster_b_before = list(team_b_roster)
    roster_b_after = [p for p in roster_b_before if p not in team_b_sends] + team_a_sends
    
    opt_b_before = build_optimal_lineup_func(roster_b_before, players_meta, projections, comp_data, roster_positions)
    opt_b_after = build_optimal_lineup_func(roster_b_after, players_meta, projections, comp_data, roster_positions)
    
    score_b_before = sum(slot['player']['points'] for slot in opt_b_before if slot['player'])
    score_b_after = sum(slot['player']['points'] for slot in opt_b_after if slot['player'])
    delta_score_b = round(score_b_after - score_b_before, 2)

    # 3. Formulate Clear, Multi-Line Strategic Verdict
    diff_str = f"+{market_diff_a:,}" if market_diff_a >= 0 else f"{market_diff_a:,}"
    
    if fairness_pct >= 90 and abs(delta_score_a) <= 2.5 and abs(delta_score_b) <= 2.5:
        verdict_badge = "FAIR & BALANCED"
        verdict_headline = "Fair & Balanced Exchange"
        verdict_summary = f"Both {team_a_name} and {team_b_name} exchange near-identical market equity while preserving active starting lineup integrity."
        badge_color = "#5B705E"
    elif delta_score_a > 1.5 and delta_score_b > 1.5:
        verdict_badge = "MUTUAL WIN-WIN"
        verdict_headline = "Mutual Starting Lineup Upgrade"
        verdict_summary = f"Synergistic Win-Win: Both managers improve their weekly starting score (+{delta_score_a:.1f} pts for {team_a_name}, +{delta_score_b:.1f} pts for {team_b_name}) by addressing positional bottlenecks."
        badge_color = "#5B705E"
    elif delta_score_a > 2.0 and market_diff_a >= 0:
        verdict_badge = f"FAVORS {team_a_name.upper()}"
        verdict_headline = f"Strong High-Impact Win for {team_a_name}"
        verdict_summary = f"{team_a_name} captures surplus market equity (+{market_diff_a:,} pts) while improving immediate starting output (+{delta_score_a:.1f} pts/wk)."
        badge_color = "#2D6A4F"
    elif delta_score_b > 2.0 and market_diff_a < 0:
        verdict_badge = f"FAVORS {team_b_name.upper()}"
        verdict_headline = f"Strong High-Impact Win for {team_b_name}"
        verdict_summary = f"{team_b_name} captures surplus market equity (+{abs(market_diff_a):,} pts) while improving immediate starting output (+{delta_score_b:.1f} pts/wk)."
        badge_color = "#2D6A4F"
    elif delta_score_a > 2.5 and market_diff_a < -800:
        verdict_badge = "STAR CONSOLIDATION"
        verdict_headline = f"{team_a_name} Consolidates for Elite Starter"
        verdict_summary = f"{team_a_name} deliberately pays a market depth premium (-{abs(market_diff_a):,} pts) to acquire an elite weekly difference-maker (+{delta_score_a:.1f} pts/wk)."
        badge_color = "#5B705E"
    elif delta_score_b > 2.5 and market_diff_a > 800:
        verdict_badge = "STAR CONSOLIDATION"
        verdict_headline = f"{team_b_name} Consolidates for Elite Starter"
        verdict_summary = f"{team_b_name} deliberately pays a market depth premium to acquire an elite weekly difference-maker (+{delta_score_b:.1f} pts/wk)."
        badge_color = "#5B705E"
    elif is_dynasty and avg_age_a_sends and avg_age_b_sends and avg_age_b_sends < avg_age_a_sends - 2:
        verdict_badge = "YOUTH / REBUILD PIVOT"
        verdict_headline = f"{team_a_name} Executes Dynasty Youth Pivot"
        verdict_summary = f"{team_a_name} successfully resets their competitive timeline, getting younger by {avg_age_a_sends - avg_age_b_sends:.1f} years on average."
        badge_color = "#5B705E"
    elif is_dynasty and avg_age_a_sends and avg_age_b_sends and avg_age_a_sends < avg_age_b_sends - 2:
        verdict_badge = "WIN-NOW PUSH"
        verdict_headline = f"{team_a_name} Buys Veteran Production"
        verdict_summary = f"{team_a_name} trades future dynasty runway for experienced immediate veteran scoring."
        badge_color = "#8A6D3B"
    elif fairness_pct < 75:
        winning_team = team_a_name if market_diff_a > 0 else team_b_name
        losing_team = team_b_name if market_diff_a > 0 else team_a_name
        verdict_badge = "UNEVEN TRADE"
        verdict_headline = f"Lopsided in Favor of {winning_team}"
        verdict_summary = f"{winning_team} captures significant surplus market capital ({abs(market_diff_a):,} pts). {losing_team} requires additional assets to reach parity."
        badge_color = "#9C4221"
    else:
        winning_team = team_a_name if market_diff_a > 0 else team_b_name
        verdict_badge = "MODERATE SKEW"
        verdict_headline = f"Market Skew Toward {winning_team} ({fairness_pct}% Parity)"
        verdict_summary = f"Trade tilts moderately toward {winning_team} by {abs(market_diff_a):,} market points."
        badge_color = "#8A6D3B"

    # Multi-line Breakdown items
    breakdown_lines = [
        {
            "category": "Market Capital",
            "text": f"{team_a_name} receives {val_b_sends:,} pts and gives {val_a_sends:,} pts (Net: {diff_str} pts, {fairness_pct}% parity)."
        },
        {
            "category": "Starting Lineup Impact",
            "text": f"{team_a_name}: {delta_score_a:+.1f} pts/wk ({score_a_before:.1f} → {score_a_after:.1f}) | {team_b_name}: {delta_score_b:+.1f} pts/wk ({score_b_before:.1f} → {score_b_after:.1f})"
        }
    ]
    if is_dynasty and avg_age_a_sends and avg_age_b_sends:
        age_diff = round(avg_age_b_sends - avg_age_a_sends, 1)
        breakdown_lines.append({
            "category": "Dynasty Age Shift",
            "text": f"{team_a_name} sends avg age {avg_age_a_sends} yrs and receives avg age {avg_age_b_sends} yrs ({age_diff:+.1f} yrs shift)."
        })

    return {
        "team_a_gives": team_a_gives_assets,
        "team_b_gives": team_b_gives_assets,
        "val_a_sends": val_a_sends,
        "val_b_sends": val_b_sends,
        "market_diff_a": market_diff_a,
        "fairness_pct": fairness_pct,
        "score_a_before": round(score_a_before, 1),
        "score_a_after": round(score_a_after, 1),
        "delta_score_a": delta_score_a,
        "score_b_before": round(score_b_before, 1),
        "score_b_after": round(score_b_after, 1),
        "delta_score_b": delta_score_b,
        "avg_age_a_sends": avg_age_a_sends,
        "avg_age_b_sends": avg_age_b_sends,
        "verdict": verdict_summary,
        "verdict_headline": verdict_headline,
        "verdict_summary": verdict_summary,
        "verdict_badge": verdict_badge,
        "badge_color": badge_color,
        "breakdown_lines": breakdown_lines
    }

def generate_balancing_suggestions(
    team_a_name: str,
    team_b_name: str,
    team_a_roster: List[str],
    team_b_roster: List[str],
    team_a_sends: List[str],
    team_b_sends: List[str],
    trade_result: Dict[str, Any],
    market_data: Dict[str, Any],
    players_meta: Dict[str, Any],
    projections: pd.DataFrame,
    comp_data: pd.DataFrame,
    roster_positions: List[str],
    is_dynasty: bool,
    build_optimal_lineup_func,
    get_projection_func
) -> Dict[str, Any]:
    """
    Generates 3 distinct tailored counter-balance suggestions to bring an uneven trade to parity:
    1. 'Positional Need Balancer' - Targets the receiving team's weakest starting slot.
    2. 'EV Production Anchor' - Highest projected weekly output player within budget.
    3. 'The Leverage Sweetener' - Nudges trade slightly in the receiving team's favor (+5% to +15% over gap).
    """
    val_a = trade_result.get('val_a_sends', 0)
    val_b = trade_result.get('val_b_sends', 0)

    # Determine deficit team (who sends more value than they receive)
    if val_a > val_b:
        deficit_team = team_a_name
        surplus_team = team_b_name
        deficit_roster = list(team_a_roster)
        surplus_roster = list(team_b_roster)
        surplus_sends = list(team_b_sends)
        target_gap = val_a - val_b
        deficit_is_team_a = True
    else:
        deficit_team = team_b_name
        surplus_team = team_a_name
        deficit_roster = list(team_b_roster)
        surplus_roster = list(team_a_roster)
        surplus_sends = list(team_a_sends)
        target_gap = val_b - val_a
        deficit_is_team_a = False

    # Collect available candidates from surplus team (not already traded)
    available_pids = [pid for pid in surplus_roster if pid not in surplus_sends]
    candidates = []
    for pid in available_pids:
        p_str = str(pid)
        p_meta = players_meta.get(p_str, {}) if isinstance(players_meta, dict) else {}
        p_name = p_meta.get('name') or p_meta.get('full_name') or p_str
        pos = p_meta.get('pos') or p_meta.get('position', '—')
        team = p_meta.get('team') or '—'
        val_info = get_player_trade_value(p_str if p_str in market_data.get('by_sleeper_id', {}) else p_name, market_data, is_dynasty)
        val = val_info.get("consensus_value", val_info.get("value", 0))
        pts = get_projection_func(p_name, projections) if get_projection_func else 0.0
        
        candidates.append({
            "id": p_str,
            "name": p_name,
            "pos": pos,
            "team": team,
            "val": val,
            "pts": pts,
            "age": val_info.get("age"),
            "trend": val_info.get("trend30Day", 0)
        })

    def calc_recalculated_fairness(cand_val: int) -> Tuple[float, int]:
        if deficit_is_team_a:
            new_val_b = val_b + cand_val
            n_max = max(val_a, new_val_b)
            n_min = min(val_a, new_val_b)
            fairness = round((n_min / n_max * 100), 1) if n_max > 0 else 100.0
            shift = new_val_b - val_a
        else:
            new_val_a = val_a + cand_val
            n_max = max(new_val_a, val_b)
            n_min = min(new_val_a, val_b)
            fairness = round((n_min / n_max * 100), 1) if n_max > 0 else 100.0
            shift = val_b - new_val_a
        return fairness, shift

    # Fallback if no players on surplus team
    if not candidates:
        return {
            "deficit_team": deficit_team,
            "surplus_team": surplus_team,
            "target_gap": target_gap,
            "suggestions": []
        }

    # 1. Analyze deficit team's positional needs from starting lineup
    pos_pts = {}
    try:
        opt_lineup = build_optimal_lineup_func(deficit_roster, players_meta, projections, comp_data, roster_positions)
        for slot in opt_lineup:
            p = slot.get('player')
            slot_name = slot.get('slot', '')
            slot_base = slot_name.split()[0]
            if p and slot_base in ['QB', 'RB', 'WR', 'TE']:
                pos_pts.setdefault(slot_base, []).append(p.get('points', 0.0))
    except Exception as e:
        print(f"Error computing optimal lineup for suggestions: {e}")

    pos_avgs = {pos: (sum(pts) / len(pts)) for pos, pts in pos_pts.items() if pts}
    ranked_needs = sorted(pos_avgs.keys(), key=lambda k: pos_avgs[k])  # Lowest avg scoring starter first
    primary_need_pos = ranked_needs[0] if ranked_needs else "RB"
    need_starter_avg = pos_avgs.get(primary_need_pos, 0.0)

    # ─────────────────────────────────────────────────────────────────────────────
    # SUGGESTION 1: Positional Need Balancer
    # ─────────────────────────────────────────────────────────────────────────────
    need_pool = [c for c in candidates if c['pos'] == primary_need_pos]
    if not need_pool and len(ranked_needs) > 1:
        need_pool = [c for c in candidates if c['pos'] == ranked_needs[1]]
        primary_need_pos = ranked_needs[1]
    if not need_pool:
        need_pool = list(candidates)

    # Pick candidate closest in value to target_gap
    cand_need = min(need_pool, key=lambda c: abs(c['val'] - target_gap))
    fairness_1, shift_1 = calc_recalculated_fairness(cand_need['val'])
    
    sug_1 = {
        "name": "Positional Need Balancer",
        "badge": "ROSTER NEED",
        "player": cand_need,
        "headline": f"Fills {deficit_team}'s void at {cand_need['pos']}",
        "rationale": f"Targets {deficit_team}'s weakest starting slot ({primary_need_pos}, currently averaging {need_starter_avg:.1f} pts/starter). Adding {cand_need['name']} ({cand_need['val']:,} pts) brings trade parity to {fairness_1}%.",
        "new_fairness": fairness_1,
        "diff_shift": shift_1
    }

    # ─────────────────────────────────────────────────────────────────────────────
    # SUGGESTION 2: EV Production Anchor (Highest weekly points within budget)
    # ─────────────────────────────────────────────────────────────────────────────
    budget_cap = max(target_gap * 1.5, 2500)
    budget_pool = [c for c in candidates if c['val'] <= budget_cap]
    if not budget_pool:
        budget_pool = list(candidates)

    # Sort by projected weekly points descending
    budget_pool_sorted = sorted(budget_pool, key=lambda c: (c['pts'], c['val']), reverse=True)
    # Prefer a different player from Sug 1 if possible
    cand_proj = next((c for c in budget_pool_sorted if c['id'] != cand_need['id']), budget_pool_sorted[0])
    fairness_2, shift_2 = calc_recalculated_fairness(cand_proj['val'])

    sug_2 = {
        "name": "EV Production Anchor",
        "badge": "WEEKLY OUTPUT",
        "player": cand_proj,
        "headline": f"Maximizes weekly scoring (+{cand_proj['pts']:.1f} pts/wk)",
        "rationale": f"Infuses the highest available weekly projected output ({cand_proj['pts']:.1f} pts) within budget. Provides immediate starting scoring while adjusting fairness to {fairness_2}%.",
        "new_fairness": fairness_2,
        "diff_shift": shift_2
    }

    # ─────────────────────────────────────────────────────────────────────────────
    # SUGGESTION 3: The Leverage Sweetener (Nudges trade in receiving team's favor)
    # ─────────────────────────────────────────────────────────────────────────────
    sweet_min = target_gap * 1.02 if target_gap > 300 else target_gap + 150
    sweet_max = max(target_gap * 1.35, target_gap + 750)
    
    sweet_candidates = [c for c in candidates if sweet_min <= c['val'] <= sweet_max]
    if sweet_candidates:
        cand_sweet = min(sweet_candidates, key=lambda c: abs(c['val'] - (target_gap * 1.15)))
    else:
        over_gap = [c for c in candidates if c['val'] >= target_gap]
        if over_gap:
            cand_sweet = min(over_gap, key=lambda c: c['val'])
        else:
            cand_sweet = max(candidates, key=lambda c: c['val'])

    used_ids = {cand_need['id'], cand_proj['id']}
    if cand_sweet['id'] in used_ids and len(candidates) > 2:
        alternatives = [c for c in candidates if c['id'] not in used_ids]
        if alternatives:
            cand_sweet = min(alternatives, key=lambda c: abs(c['val'] - (target_gap * 1.15)))

    fairness_3, shift_3 = calc_recalculated_fairness(cand_sweet['val'])
    sweetener_bonus = max(0, cand_sweet['val'] - target_gap)
    
    sug_3 = {
        "name": "The Leverage Sweetener",
        "badge": "DEAL MAKER",
        "player": cand_sweet,
        "headline": f"Tips the scale in {deficit_team}'s favor",
        "rationale": f"Nudges market equity slightly into {deficit_team}'s favor (+{sweetener_bonus:,} bonus pts over exact balance). Creates a psychological sweetener that heavily incentivizes acceptance ({fairness_3}% parity).",
        "new_fairness": fairness_3,
        "diff_shift": shift_3
    }

    return {
        "deficit_team": deficit_team,
        "surplus_team": surplus_team,
        "target_gap": target_gap,
        "suggestions": [sug_1, sug_2, sug_3]
    }

