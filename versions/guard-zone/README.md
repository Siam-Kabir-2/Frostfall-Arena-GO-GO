# Frostfall Arena · Guard Zone

Double-click **Play Guard Zone.cmd**. Choose a local duel, Minimax with alpha-beta pruning, MCTS, or an AI matchup. The launcher checks this version's local virtual environment first. For a standalone setup, install `requirements-3d.txt` and run `python guard_zone.py`.

- Each team first steps its Defender one tile, or holds it in place with **H**, then slides its Attacker. Clicking the Attacker destination commits the turn. Use **Undo** or right-click to reconsider the Defender's step first.
- The Defender guards the eight neighboring tiles, clipped to existing ice. Opponents can slide across a guard but need an unguarded or contested landing. Opposing guards cancel their restrictions where they overlap. Both teams can land on those tiles. The two guard colors and gold ring mark the overlap.
- The Defender leaves fish and ice in place. The Attacker collects fish on landing and cracks that floe. A cracked floe sinks when the Attacker pushes off it. An intact floe stays in play.
- Reach 30 fish or trap both opposing penguins with physical obstructions. Guard markings alone can block a landing for a turn. The fish score decides when the fish run out, both teams are physically trapped, or 24 rounds finish.

The prototype uses the original seeded 8×8 board, with guard and fishing rules running independently of the Adventure hazards. Use **V** to change the view and **P** to pause.
