# Frostfall · Thin Ice

Double-click **Play Thin Ice.cmd**. Choose Play vs Minimax, Play vs MCTS, Local Duel, or Watch Minimax vs MCTS. A standalone install can use `python -m pip install -r requirements.txt` followed by `python thin_ice.py`.

Two penguins skate simultaneously on one shared 3D lake. Catch the moving golden fish by skating over them. Dash off a marked thin floe and it will crack and sink after about one second. If the central route breaks, the shoal moves north where a path stays open around the water. Falling costs one point, then returns you to solid ice. The higher score at the end of 45 seconds wins.

| | Coral | Azure in Local Duel |
| --- | --- | --- |
| Steer | WASD | Arrow keys |
| Dash | Q | Enter |
| Brake | Space | Slash |

Arrow keys also steer Coral in a match against AI. **P** pauses, **H** shows AI decisions, **R** restarts, **M** mutes, and **Esc** opens pause or returns from results to the menu.

Minimax uses alpha-beta pruning over simultaneous skating actions. MCTS uses decoupled UCT on the same state and physics. Both plan short actions from public game state while the 60 Hz game continues. The AI display names the chosen action and shows the number of nodes or rollouts explored.
