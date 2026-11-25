# Frostfall Go Go

Run `Play Go Go.cmd` on Windows. The launcher checks this version's local virtual environment first. For a standalone install, run `python -m pip install -r requirements.txt` and then `python gogo.py`.

The game starts inside the desktop work area. Drag a window corner or use **−/+** to change the size. Press **F10** or click **Fit Window** to fit the entire board and card hand on screen.

Choose **Play vs MCTS**, **Local Two Player**, or **Minimax vs MCTS**. Both players get 15 shells and can deploy up to five penguins on the shared battlefield. Drag a card from the bottom of the screen onto a tile on your side, or click the card and then the tile. Deploying costs shells and brings the displayed **Next** card into that slot. Each opening hand contains the Tank and three other distinct classes. Right-click a recruit to sell it.

Before rounds one, two, and three, both sides get one, two, and three free upgrades respectively. Pick **Upgrade**, then a highlighted penguin. An upgrade raises its rank by one, up to rank four. A penguin can be upgraded once per round. Unspent upgrades expire between rounds. The lineup, ranks, cards, and shells carry over, and penguins begin each battle at full health.

Lock both teams to start early, or battle automatically at the end of the 32-second countdown. In CPU mode, press **Space** to ready your team. Cards stay visible during battle, and the penguins move and attack automatically.

Both squads use the same combat rules. Greedy targeting chooses the nearest enemy for normal attacks, with a back-line priority for the Assassin's ability. A* guides each advancing penguin toward a tile in attack range on a half-tile movement grid, with a cost for crossing allies. It runs for movement across open ice as well.

In **Play vs MCTS**, the CPU samples possible opponent hands and future draws and plays out real battles to choose placements and upgrades. **Minimax vs MCTS** alternates those decisions using identical public card sequences. The opening side switches between rounds and new showdowns. Minimax uses alpha-beta pruning and a formation score, with the battle engine for fully locked lineups. The search counters show the work done for each planner's latest decision.

| Penguin | Class | Suggested position | Combat style |
| --- | --- | --- | --- |
| Rime | Marksman | Back center | Repeated long-range shots and a slowing volley. |
| Wisp | Assassin | Outer edge | Blinks into the opposing back line, prioritizing Marksmen and Mages. |
| Glacier | Tank | Front center | Absorbs hits and shields nearby allies. |
| Tide | Fighter | Front flank | Rushes into melee, pushes an enemy, and recovers some health. |
| Cinder | Mage | Back offset | Hits groups with a ranged burst. |

A match lasts up to three rounds. The last squad standing wins the round, or a timeout compares each team's remaining percentage of its starting health. Simultaneous knockouts and ties are draws and give neither player a round win. The first to two round wins takes the match. If three rounds are played, the higher win count takes the match, and equal scores draw. **Rematch** starts a new series.

Formation references include the [official Magic Chess: Go Go positioning tutorial](https://www.youtube.com/watch?v=6jYmQJMwbVQ) and the [official Mobile Legends hero class list](https://www.mobilelegends.com/hero/list). The abilities and suggested tiles above are Frostfall's own rules.
