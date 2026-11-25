# Frostfall: Whiteout

A desktop 3D downhill penguin race on a 1.28 km mountain course. Run `Play Whiteout.cmd` on Windows. The launcher checks this version's local virtual environment first. For a standalone install with Python 3.10 or later, install `requirements.txt` and run `python whiteout.py`.

| Mode | What you play |
| --- | --- |
| **1 · Quick Race** | You and seven bots race down the same mountain. |
| **2 · AI Showdown** | Watch Minimax with alpha-beta pruning race MCTS. |
| **3 · Rival Duel** | Race MCTS head to head. |

Use **A/D** or **←/→** to steer, **Space** to boost, **S** or **↓** to brake, and hold **C** to look back. **P** pauses. **H** toggles AI telemetry and **Tab** changes the camera while spectating. After the race, **R** starts a rematch and **V** opens the replay.

Gain speed and recharge boost by following another racer's fresh tracks. Steer around darker blue rough ice. At shortcut signs, move toward the marked side before the routes split. The Blue Tunnel shutter closes after 34.5 seconds. A fall sends you to the last checkpoint if the avalanche has yet to reach it. The first racer to cross the finish wins.

All three modes use a shared deterministic physics simulation. Minimax scores both racers' possible controls using alpha-beta pruning, and MCTS samples outcomes with decoupled UCT. The searches compare short sequences of steering and throttle decisions using progress, speed, remaining boost, safe clearance and the state of the tunnel. The bots in Quick Race use preset racing strategies. Race replays use the recorded inputs and search decisions from that run. All modes run locally.
