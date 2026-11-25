# Frostfall · Under the Ice

Double-click **Play Under the Ice.cmd** for the 3D duel. Choose **Local Duel**, **Play vs Minimax**, **Play vs MCTS**, or **Watch Minimax vs MCTS**. Two penguins share one cave, one fish supply, and the same air vents. Each team moves one penguin per turn.

Click a glowing landmark to swim, or use its number. **Tab** cycles destinations and **Enter** plays the selected move. Air vents bank your fish and refill air. The red ring shows where Deepfin strikes after both teams move. Reach eight banked fish or outlast the other diver. **P** pauses and **R** restarts. The 3D opponent uses alpha-beta Minimax or UCT MCTS across the same legal moves used by human players. Install `requirements-3d.txt` for a standalone 3D setup.

## 2D prototype

Double-click **Play Under the Ice 2D.cmd** to open the earlier 2D mode menu. You can also install `requirements.txt` and run `python under_the_ice.py`.

- **1 · Solo Dive.** Control the penguin yourself.
- **2 · Watch AI Dive.** Spectate an autonomous diver against Deepfin. **Tab** switches the diver and lookout between A* and Greedy Best-First.
- **3 · AI vs AI.** Watch two autonomous divers race to 11 fish in identical copies of a cave with extra ice formations. They share the same movement, air, and decision rules. One uses A*, and the other uses Greedy Best-First. Each lane displays its elapsed time and the nodes its diver searched. At 60 seconds, or when both divers run out of lives, banked fish decide the race.

Press **Esc** in a game to return to the mode menu. Use `--mode solo`, `--mode watch`, or `--mode race` to open a mode directly.

Use **WASD** or the **arrow keys** to move. Press **Down** at either opening to dive, swim through fish to collect them, and press **Up** under an opening to surface. Bring **11 fish** to the surface before losing three dives. Running out of air or getting caught by Deepfin loses your current haul. The fish from that dive return to the cave.

The upper current flows east and the lower current flows west. The Lookout runs along the surface to mark an opening. Use **G** to show its route and **Tab** to switch the search between A* and Greedy Best-First. Press **P** to pause, **R** to restart the same cave, **N** for a new cave, and **M** to mute.

## AI in play

- **Backtracking with forward checking** assigns formations and fish schools from compatible domains. Press **N** to generate another arrangement.
- **A*** and **Greedy Best-First Search** use the same hidden waypoint graph, with edges limited to unobstructed swims. The route overlay shows how many nodes each search explored from the current position to the suggested opening.
- **Rule-based inference** checks reachability, proximity to Deepfin, and whether the estimated route fits the remaining air. It selects a route and explains its choice in the HUD.
- **Fuzzy pursuit** blends Deepfin’s patrol and chasing speeds using distance, visibility, and the diver’s remaining air.
