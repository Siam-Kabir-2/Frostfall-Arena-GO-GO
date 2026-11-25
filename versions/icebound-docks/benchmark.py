"""Measure Minimax and MCTS on the same boards with balanced seats and initiative."""

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from statistics import mean

from frostfall.ai import PRESETS, search
from frostfall.rules import choices, decide_team, new_match, transition


def play(case):
    seed, adventure, swap, difficulty = case
    lineup = ("MCTS", "Minimax") if swap else ("Minimax", "MCTS")
    # Coral opens in both games, so swapping seats also swaps first algorithm.
    state = new_match(seed, adventure, first=0)
    depth, simulations = PRESETS[difficulty]
    stats = {algorithm: [0, 0, 0.0] for algorithm in lineup}
    actions = 0
    while not state.over:
        legal = choices(state)
        if len(legal) == 1:
            action = legal[0]
        else:
            algorithm = lineup[decide_team(state)]
            decision = search(state, algorithm, difficulty)
            action = decision.action
            bucket = stats[algorithm]
            bucket[0] += 1
            bucket[1] += decision.effort
            bucket[2] += decision.seconds
        state, _ = transition(state, action)
        actions += 1
        if actions > 160:
            raise RuntimeError(f"Match failed to finish for seed {seed}")
    mini, mcts = stats["Minimax"], stats["MCTS"]
    return {"mode": "Adventure" if adventure else "Classic", "seed": seed,
            "coral": lineup[0], "azure": lineup[1], "first_team": "Coral",
            "winner": "Draw" if state.winner < 0 else lineup[state.winner], "reason": state.reason,
            "minimax_fish": state.scores[lineup.index("Minimax")], "mcts_fish": state.scores[lineup.index("MCTS")],
            "minimax_depth": depth, "mcts_budget": simulations,
            "minimax_decisions": mini[0], "mcts_decisions": mcts[0],
            "minimax_nodes": mini[1], "mcts_simulations": mcts[1],
            "minimax_ms": round(1000 * mini[2] / max(1, mini[0]), 3),
            "mcts_ms": round(1000 * mcts[2] / max(1, mcts[0]), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=610830)
    parser.add_argument("--difficulty", choices=PRESETS, default="Standard")
    parser.add_argument("--mode", choices=("classic", "adventure", "both"), default="both")
    parser.add_argument("--output", default="benchmark-results.csv")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.seeds < 1 or args.workers < 1:
        parser.error("--seeds and --workers must be positive")
    modes = {"classic": (False,), "adventure": (True,), "both": (False, True)}[args.mode]
    cases = [(seed, adventure, swap, args.difficulty) for adventure in modes
             for seed in range(args.seed_start, args.seed_start + args.seeds) for swap in (False, True)]
    if args.workers == 1:
        results = list(map(play, cases))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(play, cases))
    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=results[0])
        writer.writeheader()
        writer.writerows(results)
    for mode in dict.fromkeys(row["mode"] for row in results):
        rows = [row for row in results if row["mode"] == mode]
        wins = [sum(row["winner"] == name for row in rows) for name in ("Minimax", "MCTS", "Draw")]
        line = f"{mode} ({len(rows)} matches)  Minimax {wins[0]} | MCTS {wins[1]} | Draws {wins[2]}"
        for name in ("minimax", "mcts"):
            fish = mean(row[f"{name}_fish"] for row in rows)
            decisions = sum(row[f"{name}_decisions"] for row in rows)
            milliseconds = sum(row[f"{name}_ms"] * row[f"{name}_decisions"] for row in rows) / max(1, decisions)
            line += f"  |  {name} {fish:.1f} fish, {milliseconds:.1f} ms/decision"
        print(line)


if __name__ == "__main__":
    main()
