"""Simultaneous-move Minimax and decoupled UCT over short skating actions."""

from dataclasses import dataclass
from math import cos,hypot,log,sin,sqrt
from random import Random
from time import perf_counter

from thin_rules import CENTERS, Control, IDLE, fish_locations, ice_at, live_ice, school_destination, steer, step


MACRO_TICKS = 13
THINK_TIME = .075


@dataclass(frozen=True, slots=True)
class Decision:
    control: Control
    effort: int
    action: str


class SearchStopped(Exception):
    pass


def target(state,team):
    player=state.skaters[team]
    lead_x,lead_y=school_destination(state)
    dx,dy=lead_x-state.school_x,lead_y-state.school_y
    length=max(.01,hypot(dx,dy))
    drift_x,drift_y=.5*dx/length,.5*dy/length
    fish = tuple((x+drift_x,y+drift_y) for _,x,y in fish_locations(state)
                 if live_ice(state,x+drift_x,y+drift_y))
    if fish:
        return min(fish,key=lambda point:hypot(point[0]-player.x,point[1]-player.y))
    if live_ice(state,lead_x,lead_y):
        return lead_x,lead_y
    return CENTERS[team]


def simple(state,team):
    player=state.skaters[team]
    x,y=target(state,team)
    return steer(x-player.x-player.vx*.16,y-player.y-player.vy*.16)


def forecast(state,team,action):
    pawn=state.skaters[team]
    wanted=target(state,team)
    if action.brake:
        vx,vy=pawn.vx*.11,pawn.vy*.11
    elif action.dash:
        vx,vy=10.9*action.x,10.9*action.y
    else:
        vx,vy=.51*pawn.vx+3.05*action.x,.51*pawn.vy+3.05*action.y
    x,y=pawn.x+vx*.26,pawn.y+vy*.26
    cell=ice_at(x,y)
    danger=7 if cell<0 or state.ice[cell]<0 else (3 if 0<state.ice[cell]-state.tick<25 else 0)
    return hypot(wanted[0]-x,wanted[1]-y)+danger + (.26 if action.dash else 0.)


def candidates(state,team):
    pawn=state.skaters[team]
    if pawn.splash:
        return (IDLE,)
    pursuit=simple(state,team)
    options=[pursuit,Control(brake=True)]
    for angle in (-1.60,-.84,.84,1.60):
        options.append(Control(pursuit.x*cos(angle)-pursuit.y*sin(angle),pursuit.x*sin(angle)+pursuit.y*cos(angle)))
    if not pawn.cooldown and hypot(pursuit.x,pursuit.y)>.6:
        options.extend((pursuit._replace(dash=True),options[3]._replace(dash=True)))
    options.sort(key=lambda action:forecast(state,team,action))
    return tuple(dict.fromkeys(options[:4]))


def simulate(state,controls):
    child=state.clone()
    for _ in range(MACRO_TICKS):
        step(child,controls)
    return child


def value(state,team):
    skaters=state.skaters
    score=[]
    for side,pawn in enumerate(skaters):
        wanted=target(state,side)
        distance=hypot(pawn.x-wanted[0],pawn.y-wanted[1])
        safe=live_ice(state,pawn.x+pawn.vx*.14,pawn.y+pawn.vy*.14)
        score.append(pawn.score*12.+5/(.8+distance)-pawn.splash*.09-(0 if safe else 2.3))
    return score[team]-score[1-team]


def paired(first,second,team):
    return (first,second) if team==0 else (second,first)


def move_name(action):
    if action.dash:
        return "Dash toward the shoal"
    if action.brake:
        return "Brake and change direction"
    return "Skate to intercept"


def minimax(state,team,cancelled):
    deadline=perf_counter()+THINK_TIME
    root=candidates(state,team)
    picked=root[0]
    count=0

    def visit(position,depth,alpha,beta):
        nonlocal count
        count += 1
        if cancelled() or perf_counter()>=deadline:
            raise SearchStopped
        if not depth or position.over:
            return value(position,team)
        best=-float("inf")
        opponents=candidates(position,1-team)
        for action in candidates(position,team):
            worst=float("inf")
            for reply in opponents:
                output=simulate(position,paired(action,reply,team))
                worst=min(worst,visit(output,depth-1,alpha,min(beta,worst)))
                if worst<=alpha:
                    break
            best=max(best,worst)
            alpha=max(alpha,best)
            if alpha>=beta:
                break
        return best

    for depth in (1,2):
        try:
            rating=-float("inf")
            opponents=candidates(state,1-team)
            for action in root:
                worst=float("inf")
                for reply in opponents:
                    out=simulate(state,paired(action,reply,team))
                    worst=min(worst,visit(out,depth-1,rating,worst))
                    if worst<=rating:
                        break
                if worst>rating:
                    rating,best=worst,action
            picked=best
        except SearchStopped:
            break
    return Decision(picked,count,move_name(picked))


class Node:
    def __init__(self,state):
        self.state=state
        self.actions=tuple(candidates(state,team) for team in range(2))
        self.visits=[[0]*len(actions) for actions in self.actions]
        self.rewards=[[0.]*len(actions) for actions in self.actions]
        self.children={}
        self.count=0

    def choose(self,team,rng):
        untried=[index for index,count in enumerate(self.visits[team]) if not count]
        if untried:
            return rng.choice(untried)
        explore=1.29*sqrt(log(max(1,self.count)))
        return max(range(len(self.actions[team])),key=lambda i:self.rewards[team][i]/self.visits[team][i]
                   +explore/sqrt(self.visits[team][i]))


def mcts(state,team,cancelled):
    deadline=perf_counter()+THINK_TIME
    root=Node(state)
    rng=Random(state.seed*277+state.tick*13+team)
    attempts=0
    while attempts<70 and perf_counter()<deadline and not cancelled():
        node=root
        path=[]
        for _ in range(3):
            if node.state.over:
                break
            joint=node.choose(0,rng),node.choose(1,rng)
            path.append((node,joint))
            child=node.children.get(joint)
            if child is None:
                control=tuple(node.actions[side][joint[side]] for side in range(2))
                child=Node(simulate(node.state,control))
                node.children[joint]=child
                node=child
                break
            node=child
        sample=node.state
        for _ in range(2):
            if sample.over:
                break
            sample=simulate(sample,tuple(simple(sample,side) for side in range(2)))
        outcome=value(sample,0)
        for visited,joint in path:
            visited.count+=1
            for side,choice in enumerate(joint):
                visited.visits[side][choice]+=1
                visited.rewards[side][choice]+=outcome if side==0 else -outcome
        attempts+=1
    picked=root.actions[team][max(range(len(root.actions[team])),key=lambda i:root.visits[team][i])]
    return Decision(picked,attempts,move_name(picked))


def search(state,team,algorithm,cancelled=lambda:False):
    return (minimax if algorithm=="Minimax" else mcts)(state,team,cancelled)
