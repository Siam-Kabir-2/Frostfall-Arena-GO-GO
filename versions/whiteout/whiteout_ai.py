"""Race-line drivers and two adversarial searches over the real race rules."""

from dataclasses import dataclass, field
from math import log, sqrt
from random import Random
from time import perf_counter

from whiteout_rules import FORKS, HZ, Control, clamp, road_x, rough_ahead, width

MACRO = 42


@dataclass(frozen=True)
class Plan:
    line: str
    throttle: str

    @property
    def label(self):
        return f"{self.line} / {self.throttle}"


@dataclass(frozen=True)
class Decision:
    plan: Plan
    work: int
    depth: int
    seconds: float


def fork_ahead(racer):
    if racer.route < 0 and racer.next_fork < len(FORKS):
        return FORKS[racer.next_fork]


def gate_margin(race, racer, fork):
    return fork.deadline - race.time - max(0., fork.shutter - racer.s) / max(17., racer.speed)


def trail_line(race, index):
    racer = race.racers[index]
    samples = (sample for cell in range(int(racer.s // 4), int(racer.s // 4) + 4)
               for sample in race.trails.get(cell, ()) if sample.owner != index
               and sample.route == racer.route and 0. <= sample.s - racer.s <= 14.
               and race.tick - sample.tick <= 135 and abs(sample.x - racer.x) < 5.6)
    sample = min(samples, key=lambda point: abs(point.x - racer.x) + .07 * (point.s - racer.s), default=None)
    if sample:
        return clamp(sample.x - road_x(sample.s, racer.route), -4., 4.)
    return None


def control(race, index, plan, bias=0.):
    racer = race.racers[index]
    fork = fork_ahead(racer)
    target = bias
    if plan.line == "Take shortcut" and fork and fork.start - 54 <= racer.s < fork.start:
        target = fork.side * (width(fork.start) * .31 + 1.55) + bias*.48
    elif plan.line == "Follow trail":
        draft = trail_line(race, index)
        if draft is not None:
            target = draft
    elif (patch := rough_ahead(racer.s, racer.route, 28)):
        if abs(target-patch.lane) < patch.half_width+1.10:
            side = 1 if racer.lane > patch.lane else -1
            target = patch.lane + side*(patch.half_width+1.12)
    if plan.line != "Take shortcut" and fork and fork.start - racer.s < 28 and target * fork.side > 1.9:
        target = fork.side * 1.9
    if racer.route >= 0:
        target *= .72
    slip = racer.lateral * .20
    steer = clamp((target - racer.lane - slip) * .63, -1., 1.)
    return Control(steer, plan.throttle == "Boost", plan.throttle == "Brake")


def tactical_plan(race, index, profile=0):
    racer = race.racers[index]
    fork = fork_ahead(racer)
    wants_cut = fork and 0 < fork.start - racer.s < 51 and (racer.next_fork + profile) % 6 != 4
    if wants_cut and fork.shutter and gate_margin(race, racer, fork) < (1.0 if profile % 3 else .55):
        wants_cut = False
    if wants_cut:
        line = "Take shortcut"
    elif (racer.route == -1 and not rough_ahead(racer.s, racer.route, 24) and (racer.s > 118 or profile % 3 == 0)
          and (not fork or fork.start - racer.s > 52) and trail_line(race, index) is not None):
        line = "Follow trail"
    else:
        line = "Safe line"
    near_edge = abs(racer.lane) > width(racer.s, racer.route) * .79 or abs(racer.lateral) > 5.3
    reserves = (.38, .61, .42, .73, .49, .57, .65, .43)[profile % 8]
    emergency = racer.s - race.danger < 38 or racer.s > 1150
    use_boost = racer.energy > (.085 if emergency else reserves) and not racer.draft
    if wants_cut or (fork and 0 < fork.start - racer.s < 27):
        use_boost = False
    throttle = "Brake" if near_edge else "Boost" if use_boost else "Glide"
    return Plan(line, throttle)


def quick_control(race, index):
    racer = race.racers[index]
    bias = (index % 4 - 1.5) * (2.52 if racer.s < 140 else 1.14)
    return control(race, index, tactical_plan(race, index, index), bias)


def candidates(race, index):
    racer = race.racers[index]
    if not racer.active:
        return [Plan("Safe line", "Glide")]
    first = tactical_plan(race, index)
    fork = fork_ahead(racer)
    plans = [first]
    if fork and 0 < fork.start - racer.s < 55:
        plans.extend((Plan("Take shortcut", "Glide"), Plan("Safe line", "Glide")))
    else:
        plans.append(Plan("Safe line", "Glide"))
        if racer.route == -1 and trail_line(race, index) is not None:
            plans.append(Plan("Follow trail", "Glide"))
    if racer.energy > .10:
        plans.append(Plan(first.line, "Boost"))
    if abs(racer.lane) > width(racer.s, racer.route) * .58:
        plans.append(Plan("Safe line", "Brake"))
    return list(dict.fromkeys(plans))


def transition(race, plans, steps=MACRO):
    child = race.copy()
    for _ in range(steps):
        if child.done:
            break
        child.step(tuple(control(child, index, plan) for index, plan in enumerate(plans)))
    return child


def value(race, index):
    racer = race.racers[index]
    if racer.finished:
        return 2800 - racer.finished / HZ
    if racer.eliminated:
        return -850 + racer.s * .20
    road_room = abs(racer.lane) / width(racer.s, racer.route)
    score = (racer.s + racer.speed * .57 + 12 * racer.energy + 2.8 * racer.draft
             - 12 * racer.crashes - 7 * max(0., road_room - .65)
             - max(0., 48 - (racer.s - race.danger)) * .46)
    if racer.route >= 0:
        fork = FORKS[racer.route]
        score += fork.speed * min(2., (fork.end - racer.s) / 52)
        if fork.shutter and racer.s < fork.shutter:
            score -= max(0., .65 - gate_margin(race, racer, fork)) * 24
    return score


def utility(race, index):
    return value(race, index) - value(race, 1 - index)


class SearchTime(Exception):
    pass


def minimax(race, index, budget=.090, max_depth=3):
    started = perf_counter()
    deadline = started + budget
    nodes = 0

    def visit(state, depth, alpha, beta):
        nonlocal nodes
        nodes += 1
        if perf_counter() >= deadline:
            raise SearchTime
        moves = candidates(state, index)
        if not depth or state.done:
            return utility(state, index), moves[0]
        best, chosen = -float("inf"), moves[0]
        replies = candidates(state, 1 - index)
        for plan in moves:
            worst = float("inf")
            for reply in replies:
                pair = (plan, reply) if index == 0 else (reply, plan)
                child = transition(state, pair)
                score, _ = visit(child, depth - 1, alpha, min(beta, worst))
                worst = min(worst, score)
                if worst <= alpha:
                    break
            if worst > best:
                best, chosen = worst, plan
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best, chosen

    plan, completed = tactical_plan(race, index), 0
    for depth in range(1, max_depth + 1):
        try:
            _, plan = visit(race, depth, -float("inf"), float("inf"))
        except SearchTime:
            break
        completed = depth
    return Decision(plan, nodes, completed, perf_counter() - started)


@dataclass
class Node:
    state: object
    pairs: list
    children: dict = field(default_factory=dict)
    visits: int = 0
    scores: tuple = field(default_factory=lambda: ({}, {}))

    def choose(self, rng):
        return tuple(max(plans, key=lambda plan: self.ucb(index, plan, rng))
                     for index, plans in enumerate(self.pairs))

    def ucb(self, index, plan, rng):
        count, total = self.scores[index].get(plan, (0, 0.))
        if count == 0:
            return 100. + rng.random()
        return total / count + .72 * sqrt(log(self.visits + 1) / count)

    def record(self, pair, result):
        self.visits += 1
        for index, plan in enumerate(pair):
            count, total = self.scores[index].get(plan, (0, 0.))
            self.scores[index][plan] = count + 1, total + (result if index == 0 else -result)


def mcts(race, index, budget=.090, max_rollouts=128):
    started = perf_counter()
    rng = Random(race.tick * 113 + 19)
    root = Node(race, [candidates(race, player) for player in range(2)])
    rollouts, deepest = 0, 0
    while rollouts < max_rollouts and perf_counter() - started < budget and not race.done:
        node = root
        path = []
        while len(path) < 4 and not node.state.done:
            pair = node.choose(rng)
            path.append((node, pair))
            if pair in node.children:
                node = node.children[pair]
            else:
                child = transition(node.state, pair)
                new = Node(child, [candidates(child, player) for player in range(2)])
                node.children[pair] = new
                node = new
                break
        outcome = node.state
        for _ in range(3):
            if outcome.done:
                break
            pair = tuple(rng.choice(candidates(outcome, player)) if rng.random() < .23
                         else tactical_plan(outcome, player) for player in range(2))
            outcome = transition(outcome, pair)
        score = clamp(utility(outcome, 0) / 80, -1., 1.)
        for parent, pair in path:
            parent.record(pair, score)
        rollouts += 1
        deepest = max(deepest, len(path))
    statistics = root.scores[index]
    plan = (max(statistics, key=lambda move: (statistics[move][0], statistics[move][1] / statistics[move][0]))
            if statistics else tactical_plan(race, index))
    return Decision(plan, rollouts, deepest, perf_counter() - started)
