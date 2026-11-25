"""The fixed-step ice, skating, and fish simulation shared by players and AI."""

from dataclasses import dataclass, field, replace
from math import cos, hypot, sin, tau
from typing import NamedTuple


FPS = 60
ROUND_TICKS = 45*FPS
CRACK_TICKS = 54
DASH_COOLDOWN = 102
FISH_COUNT = 5
SWIM_PATH = ((0.,-1.7),(-4.4,-1.7),(-3.5,2.1),(.9,2.45),(4.4,1.4),(3.3,-2.1),(0.,-.5))
NORTH_SHOAL = ((-5.9,.12),(-4.4,2.),(-2.25,2.62),(.15,2.72),(2.6,2.65),(4.6,2.1),(6.05,.14),
               (4.6,2.1),(2.6,2.65),(.15,2.72),(-2.25,2.62),(-4.4,2.))
CENTERS = ((-6.1,-.25),(6.1,.25),(-3.45,2.65),(3.45,-2.65),(-3.55,-2.65),(3.55,2.65),
           (0.,0.),(0.,3.35),(0.,-3.35),(-6.45,2.9),(6.45,-2.9),(-6.4,-2.7),(6.4,2.7))
THIN = frozenset({3,4,6,8})
RX, RY = 8.45,5.03
BOUNDARY = tuple((RX*cos(tau*i/20),RY*sin(tau*i/20)) for i in range(20))
BOUNDARY_PLANES = tuple((b[1]-a[1],a[0]-b[0],(b[1]-a[1])*a[0]+(a[0]-b[0])*a[1])
                        for a,b in zip(BOUNDARY,(*BOUNDARY[1:],BOUNDARY[0])))
PHASES = tuple(tau*i/4 for i in range(4))


def clip(points, nx, ny, maximum):
    result = []
    for a,b in zip(points,(*points[1:],points[0])):
        left = nx*a[0]+ny*a[1]-maximum
        right = nx*b[0]+ny*b[1]-maximum
        if left <= 0:
            result.append(a)
        if (left <= 0) != (right <= 0):
            t = left/(left-right)
            result.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
    return result


def slab_profiles():
    slabs = []
    for x,y in CENTERS:
        outline = list(BOUNDARY)
        for u,v in CENTERS:
            if (x,y)!=(u,v):
                outline = clip(outline, u-x, v-y, (u*u+v*v-x*x-y*y)*.5)
        slabs.append(tuple(outline))
    return tuple(slabs)


SLABS = slab_profiles()


def ice_at(x,y):
    rim = (x/RX)**2+(y/RY)**2
    if rim>1 or (rim>.95 and any(nx*x+ny*y>edge for nx,ny,edge in BOUNDARY_PLANES)):
        return -1
    best, nearest = 0,float("inf")
    for cell,(cx,cy) in enumerate(CENTERS):
        dx,dy = x-cx,y-cy
        length = dx*dx+dy*dy
        if length < nearest:
            best,nearest=cell,length
    return best


class Control(NamedTuple):
    x: float = 0.
    y: float = 0.
    dash: bool = False
    brake: bool = False


IDLE = Control()


def steer(x,y,dash=False,brake=False):
    size = max(1.,hypot(x,y))
    return Control(x/size,y/size,dash,brake)


@dataclass(slots=True)
class Skater:
    x: float
    y: float
    vx: float = 0.
    vy: float = 0.
    face_x: float = 1.
    face_y: float = 0.
    cooldown: int = 0
    boost: int = 0
    splash: int = 0
    score: int = 0


@dataclass(slots=True)
class State:
    seed: int = 0
    tick: int = 0
    skaters: list[Skater] = field(default_factory=lambda: [Skater(-5.8,-.14),Skater(5.8,.14,face_x=-1)])
    ice: list[int] = field(default_factory=lambda: [0]*len(CENTERS))
    school_x: float = 0.
    school_y: float = -.85
    school_target: int = 0
    school_mask: int = (1<<FISH_COUNT)-1
    respawn_at: int = 0
    wave_start: int = 0
    north_route: bool = False

    def clone(self):
        return replace(self,skaters=[replace(player) for player in self.skaters],ice=self.ice.copy())

    @property
    def over(self):
        return self.tick >= ROUND_TICKS


def fish_position(state,index):
    if index == 0:
        return state.school_x,state.school_y
    t = state.tick*.024+PHASES[index-1]
    return state.school_x+.70*cos(t),state.school_y+.57*sin(t)


def fish_locations(state):
    return tuple((index,*fish_position(state,index)) for index in range(FISH_COUNT) if state.school_mask & (1<<index))


def school_path(state):
    return NORTH_SHOAL if state.north_route else SWIM_PATH


def school_destination(state):
    return school_path(state)[state.school_target]


def live_ice(state,x,y):
    cell = ice_at(x,y)
    return cell >= 0 and state.ice[cell] >= 0


def advance_player(state,team,control,events):
    player = state.skaters[team]
    if player.splash:
        player.splash -= 1
        if not player.splash:
            player.x,player.y=CENTERS[team]
            player.cooldown=0
            player.face_x,player.face_y=(1. if team == 0 else -1.),0.
        return
    player.cooldown = max(0,player.cooldown-1)
    if control.x or control.y:
        player.face_x,player.face_y=control.x,control.y
    if control.dash and not player.cooldown:
        cell = ice_at(player.x,player.y)
        if cell in THIN and state.ice[cell] == 0:
            state.ice[cell]=state.tick+CRACK_TICKS
            if events is not None:
                events.append(("crack",team,player.x,player.y))
        player.vx,player.vy=player.face_x*12.3,player.face_y*12.3
        player.cooldown=DASH_COOLDOWN
        player.boost=16
        if events is not None:
            events.append(("dash",team,player.x,player.y))
    elif control.brake:
        player.vx *= .76
        player.vy *= .76
        player.boost=0
    elif player.boost:
        player.vx *= .978
        player.vy *= .978
        player.boost -= 1
    else:
        player.vx = player.vx*.947+control.x*.35
        player.vy = player.vy*.947+control.y*.35
    player.x += player.vx/FPS
    player.y += player.vy/FPS


def bump_players(skaters):
    a,b = skaters
    if a.splash or b.splash:
        return
    dx,dy = b.x-a.x,b.y-a.y
    separation = hypot(dx,dy)
    if separation >= .72:
        return
    if separation < .00001:
        nx,ny = 1.,0.
    else:
        nx,ny = dx/separation,dy/separation
    overlap = (.72-separation)*.5
    a.x -= nx*overlap
    a.y -= ny*overlap
    b.x += nx*overlap
    b.y += ny*overlap
    closing = max(0.,(a.vx-b.vx)*nx+(a.vy-b.vy)*ny)*.63
    a.vx -= nx*closing
    a.vy -= ny*closing
    b.vx += nx*closing
    b.vy += ny*closing


def advance_school(state):
    route=school_path(state)
    if not state.school_mask or state.tick-state.wave_start >= 620:
        if not state.respawn_at:
            state.respawn_at = state.tick+65
            state.school_mask = 0
        elif state.tick >= state.respawn_at:
            state.respawn_at=0
            state.school_target=(state.school_target+2+state.seed%2)%len(route)
            x,y = route[state.school_target]
            if not live_ice(state,x,y):
                x,y = CENTERS[state.school_target%2]
                x *= .91
            state.school_x,state.school_y=x,y
            state.wave_start=state.tick
            state.school_mask=(1<<FISH_COUNT)-1
        return
    x,y = route[state.school_target]
    dx,dy = x-state.school_x,y-state.school_y
    distance = hypot(dx,dy)
    if distance < .22 or not live_ice(state,x,y):
        state.school_target=(state.school_target+1)%len(route)
    else:
        speed = .039/max(.039,distance)
        state.school_x += dx*speed
        state.school_y += dy*speed


def step(state,controls,events=None):
    if state.over:
        return
    state.tick += 1
    for cell in THIN:
        if state.ice[cell] == state.tick:
            state.ice[cell] = -1
            if not state.north_route and (cell==6 or all(state.ice[edge]<0 for edge in (3,4,8))):
                state.north_route=True
                state.school_target=min(range(len(NORTH_SHOAL)),key=lambda i:
                    hypot(state.school_x-NORTH_SHOAL[i][0],state.school_y-NORTH_SHOAL[i][1]))
            if events is not None:
                events.append(("sink",cell,*CENTERS[cell]))
    for team,control in enumerate(controls):
        advance_player(state,team,control,events)
    bump_players(state.skaters)
    for team,player in enumerate(state.skaters):
        if not player.splash and not live_ice(state,player.x,player.y):
            player.splash=57
            player.score=max(0,player.score-1)
            player.vx=player.vy=player.boost=0
            if events is not None:
                events.append(("fall",team,player.x,player.y))
    advance_school(state)
    a,b = state.skaters
    if all(player.splash or (player.x-state.school_x)**2+(player.y-state.school_y)**2>1.8**2 for player in (a,b)):
        return
    for index,x,y in fish_locations(state):
        left = float("inf") if a.splash else (a.x-x)**2+(a.y-y)**2
        right = float("inf") if b.splash else (b.x-x)**2+(b.y-y)**2
        if min(left,right) < .71**2 and abs(left-right)>1e-7:
            team = int(right<left)
            state.school_mask ^= 1<<index
            state.skaters[team].score += 1
            if events is not None:
                events.append(("fish",team,x,y))
