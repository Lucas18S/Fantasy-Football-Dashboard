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

    # 3. Formulate Strategic Verdict
    verdict = ""
    verdict_badge = ""
    
    if fairness_pct >= 90 and abs(delta_score_a) <= 3 and abs(delta_score_b) <= 3:
        verdict = "Balanced Win-Win: Both rosters maintain market parity and optimize their respective lineups."
        verdict_badge = "FAIR & BALANCED"
    elif delta_score_a > 1.5 and delta_score_b > 1.5:
        verdict = f"Mutual Starting Lineup Upgrade: Both managers improve their weekly starting score (+{delta_score_a:.1f} pts for {team_a_name}, +{delta_score_b:.1f} pts for {team_b_name}) by addressing positional bottlenecks."
        verdict_badge = "MUTUAL WIN-WIN"
    elif delta_score_a > 2.0 and market_diff_a >= 0:
        verdict = f"High-Impact Win for {team_a_name}: Enhances starting projection (+{delta_score_a:.1f} pts/wk) while netting +{market_diff_a:,} in market equity."
        verdict_badge = f"FAVORS {team_a_name.upper()}"
    elif delta_score_b > 2.0 and market_diff_a < 0:
        verdict = f"High-Impact Win for {team_b_name}: Enhances starting projection (+{delta_score_b:.1f} pts/wk) while netting +{abs(market_diff_a):,} in market equity."
        verdict_badge = f"FAVORS {team_b_name.upper()}"
    elif is_dynasty and avg_age_a_sends and avg_age_b_sends and avg_age_b_sends < avg_age_a_sends - 2:
        verdict = f"Dynasty Youth Pivot: {team_a_name} gets significantly younger (Avg Age: {avg_age_b_sends} vs {avg_age_a_sends}), acquiring productive multi-year runway."
        verdict_badge = "REBUILD / YOUTH PIVOT"
    elif delta_score_a > 3.0 and market_diff_a < -1000:
        verdict = f"Contender Consolidation Overpay: {team_a_name} gives up surplus market depth to acquire an elite weekly difference-maker (+{delta_score_a:.1f} pts/wk)."
        verdict_badge = "CONTENDER CONSOLIDATION"
    else:
        diff_str = f"+{market_diff_a:,}" if market_diff_a >= 0 else f"{market_diff_a:,}"
        verdict = f"Market Value Differential: {diff_str} equity shift. Lineup effect: {delta_score_a:+.1f} pts/wk for {team_a_name}, {delta_score_b:+.1f} pts/wk for {team_b_name}."
        verdict_badge = "SLIGHT SKEW" if fairness_pct >= 75 else "UNEVEN TRADE"

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
        "verdict": verdict,
        "verdict_badge": verdict_badge
    }
