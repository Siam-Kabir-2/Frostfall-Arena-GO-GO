"""A continuous 3D skating arena with beveled ice and readable fracture effects."""

from math import atan2,cos,degrees,sin,tau
from random import Random

from panda3d.core import LineSegs,NodePath,Shader,TransparencyAttrib,Vec3,Vec4

from frostfall import materials3d
from frostfall.stage3d import Mesh,fish_model,flat_shape,floe_mesh,oval,penguin,sphere
from thin_rules import CENTERS,CRACK_TICKS,FISH_COUNT,SLABS,THIN,fish_position


TEAM = ((1.,.47,.29,1),(.30,.88,1.,1))
MINT = (.44,.96,.81,1)
GOLD = (1.,.80,.34,1)
WATER_Z = -.44


ICE_FRAGMENT = """
#version 150
uniform float weak;
uniform float fracture;
uniform float scene_time;
in vec3 world;
in vec3 normal;
in vec4 pigment;
out vec4 p3d_FragColor;
float noise(vec2 p) {
    return fract(sin(dot(floor(p),vec2(126.1,311.7)))*43758.5453);
}
void main() {
    vec2 p=world.xy;
    vec3 n=normalize(normal);
    float top=clamp(n.z,0.,1.);
    float vein=pow(max(0.,sin(p.x*4.2+p.y*3.6+sin(p.y*3.0-p.x)*1.2)),17.);
    float fine=noise(p*87.);
    float ripple=pow(max(0.,sin(p.x*3.5+sin(p.y*1.4)+scene_time*.7)*sin(p.y*4.4+scene_time*.41)),8.);
    vec3 rgb=pigment.rgb*(.86+fine*.034+top*.15);
    rgb += vec3(.14,.28,.31)*(vein*.45+ripple*.16)*top;
    rgb += vec3(.085,.15,.20)*pow(max(0.,sin(world.z*79.+p.x*1.26)),7.)*(1.-top);
    rgb=mix(rgb,vec3(.17,.48,.58),weak*.34);
    rgb=mix(rgb,vec3(.98,.31,.15),fracture*.43*(.73+.27*sin(scene_time*19.)));
    p3d_FragColor=vec4(rgb,pigment.a);
}
"""


def circle(radius,z,count=36):
    return tuple((radius*cos(tau*i/count),radius*sin(tau*i/count),z) for i in range(count))


def lines(parent,name,coordinates,color,thickness=1.4,closed=False):
    needle=LineSegs(name)
    needle.setThickness(thickness)
    needle.setColor(*color)
    needle.moveTo(*coordinates[0])
    for point in coordinates[1:]:
        needle.drawTo(*point)
    if closed:
        needle.drawTo(*coordinates[0])
    return parent.attachNewNode(needle.create())


def build_slab(parent,cell,polygon,ice_shader):
    mesh=Mesh("Blue ice floe")
    cx,cy=CENTERS[cell]
    perimeter=tuple((cx+(x-cx)*.983,cy+(y-cy)*.983,.021) for x,y in polygon)
    top=tuple((cx+(x-cx)*.969,cy+(y-cy)*.969,.087) for x,y in polygon)
    underside=tuple((cx+(x-cx)*.905,cy+(y-cy)*.905,-.405) for x,y in polygon)
    count=len(top)
    palette=((.54,.76,.80,1),(.51,.75,.79,1),(.57,.79,.82,1),(.60,.79,.84,1)) if cell not in THIN else (
        (.38,.65,.71,1),(.34,.63,.71,1),(.43,.69,.76,1))
    for i in range(count):
        j=(i+1)%count
        mesh.triangle(((cx,cy,.086),top[i],top[j]),palette[(i+cell)%len(palette)])
        mesh.triangle((top[i],perimeter[i],perimeter[j]),(.37,.70,.81,1))
        mesh.triangle((top[i],perimeter[j],top[j]),(.36,.74,.84,1))
        mesh.triangle((perimeter[i],underside[i],underside[j]),(.16,.42,.61,1))
        mesh.triangle((perimeter[i],underside[j],perimeter[j]),(.23,.55,.70,1))
    node=parent.attachNewNode(f"Floe {cell}")
    material=mesh.attach(node)
    material.setTwoSided(True)
    material.setShader(ice_shader)
    material.setShaderInput("weak",float(cell in THIN))
    material.setShaderInput("fracture",0.)
    edges=node.attachNewNode("Floe safety cues")
    edges.setShaderOff(1)
    edges.setTransparency(TransparencyAttrib.MAlpha)
    if cell in THIN:
        for i in range(count):
            x,y,_=top[i]
            u,v,_=top[(i+1)%count]
            lines(edges,"Thin ice seam",((x*.96+cx*.04,y*.96+cy*.04,.103),
                                         ((x+u)*.48+cx*.04,(y+v)*.48+cy*.04,.103)),(.64,.92,.97,.67),1.9)
        for x,y in ((cx-.08,cy-.02),(cx+.08,cy+.03)):
            lines(edges,"Thin ice crossing",((x-.045,y-.095,.116),(x+.025,y+.01,.116),(x+.01,y+.10,.116)),
                  (.14,.41,.46,.76),1.9)
    crack=edges.attachNewNode("Active fractures")
    rng=Random(541+cell)
    for x,y in polygon:
        dx,dy=x-cx,y-cy
        coords=[(cx,cy,.121)]
        for fraction in (.26,.49,.72,.88):
            jitter=rng.uniform(-.09,.09)
            coords.append((cx+dx*fraction+dy*jitter,cy+dy*fraction-dx*jitter,.121))
        lines(crack,"Burning crack",tuple(coords),(1.,.31,.16,1),2.6)
    lines(crack,"Fracture perimeter",tuple((x,y,.124) for x,y,_ in top),(1.,.38,.18,.92),2.2,True)
    crack.hide()
    return node,material,crack


class Stage:
    def __init__(self,render,camera):
        self.root=render.attachNewNode("Thin Ice arena")
        self.root.setShader(Shader.make(Shader.SL_GLSL,materials3d.VERTEX,materials3d.SURFACE))
        self.root.setShaderInput("eye",camera.getPos())
        self.root.setShaderInput("material_kind",0)
        self.root.setShaderInput("cap_tint",Vec4(0))
        self.root.setShaderInput("frost_tint",Vec4(0))
        self.root.setShaderInput("scene_time",0.)
        self.bank=NodePath("Model library")
        self.unit=sphere(self.bank,18,12)
        self.fish_model=fish_model(self.bank)
        self.ice_shader=Shader.make(Shader.SL_GLSL,materials3d.VERTEX,ICE_FRAGMENT)
        self.water=flat_shape("Aurora reflected in the fjord",self.root,((-70,-70),(70,-70),(70,70),(-70,70)),
                              (1,1,1,1),WATER_Z)
        self.water.setShader(Shader.make(Shader.SL_GLSL,materials3d.VERTEX,materials3d.WATER))
        self.water.setShaderInput("tide_time",0.)
        self.water.setShaderInput("pressure",Vec4(0))
        self.ripples=[]
        for i in range(4):
            self.water.setShaderInput(f"ripple{i}",Vec4(0,0,-20,0))
        self.elapsed=0.
        self.slabs=[build_slab(self.root,cell,profile,self.ice_shader) for cell,profile in enumerate(SLABS)]
        self.broken_since={}
        self.glints=[]
        self.build_context()
        self.swimmers=tuple(penguin(self.root,self.unit,color,0) for color in TEAM)
        for rig in self.swimmers:
            rig.root.setScale(1.13)
        self.overlay=self.root.attachNewNode("Markers and particles")
        self.overlay.setShaderOff(1)
        self.overlay.setTransparency(TransparencyAttrib.MAlpha)
        self.rings=[]
        self.shadows=[]
        self.trails=[]
        for team,color in enumerate(TEAM):
            self.rings.append(lines(self.overlay,"Skater's team ring",circle(.40,.130),color,2.8,True))
            shadow=flat_shape("Ice contact shadow",self.overlay,
                              tuple((x,y) for x,y,_ in circle(.46,.099)),(.014,.070,.11,.27),.103)
            shadow.setDepthWrite(False)
            self.shadows.append(shadow)
            dots=[]
            for index in range(8):
                dot=oval(self.overlay,self.unit,"Dash trail",(0,0,0),(.05,.05,.037),color)
                dot.hide()
                dots.append(dot)
            self.trails.append(dots)
        self.fish=[self.fish_model.copyTo(self.root) for _ in range(FISH_COUNT)]
        self.fish_glow=[]
        for index in range(FISH_COUNT):
            self.fish[index].setScale(1.97)
            glow=lines(self.overlay,"Fish pickup halo",circle(.20,.151),(1.,.84,.42,.85),1.55,True)
            self.fish_glow.append(glow)
        self.bits=[]
        self.sparks=NodePath("Particles")
        for color in (*TEAM,GOLD,(.70,.95,1.,1)):
            self.bits.append(oval(self.sparks,self.unit,"Ice spark",(0,0,0),(1,1,1),color))
        self.particles=[]

    def build_context(self):
        rng=Random(174)
        for i in range(41):
            angle=tau*i/41+rng.uniform(-.055,.055)
            back=sin(angle)>0
            radial=rng.uniform(1.,1.09)
            x,y=cos(angle)*(11.1 if back else 12.9)*radial,sin(angle)*(7.6 if back else 8.1)*radial
            figure=floe_mesh(self.root,rng,(.39,.63,.77,1) if back else (.34,.57,.72,1),(.12,.34,.54,1),
                             glacier=i%3==0)
            figure.setShaderInput("material_kind",1)
            figure.setPos(x,y,-.42)
            size=rng.uniform(.47,1.23)
            figure.setScale(size*1.46,size,size*(1.5 if back else .58))
            figure.setH(rng.uniform(0,360))
        for index in range(16):
            x=-18.2+2.4*index
            y=9.85+rng.uniform(-.8,1.4)
            glacier=floe_mesh(self.root,rng,(.44,.65,.80,1),(.13,.29,.48,1),glacier=True)
            glacier.setShaderInput("material_kind",1)
            glacier.setPos(x,y,-.51)
            glacier.setScale(rng.uniform(1.23,2.65),rng.uniform(1.4,2.85),rng.uniform(2.05,4.1))
            glacier.setH(rng.uniform(0,360))
        for x,y in ((-12.5,2.9),(12.4,3.8),(-11.7,-4.1),(11.8,-4.2)):
            bank=floe_mesh(self.root,rng,(.62,.78,.87,1),(.24,.43,.64,1),glacier=True)
            bank.setShaderInput("material_kind",1)
            bank.setPos(x,y,-.42)
            bank.setScale(1.86,1.65,2.35)
            bank.setH(rng.uniform(0,360))
        for i in range(30):
            x,y=rng.uniform(-13,13),rng.uniform(-8,10)
            beam=oval(self.root,self.unit,"Loose snow crystals",(x,y,.45),(.021,.021,.026),(.73,.92,.99,1))
            self.glints.append((beam,x,y,rng.random()*tau))
        for team,(x,y) in enumerate(CENTERS[:2]):
            post=oval(self.root,self.unit,"Starting beacon",(x+(-.8 if team==0 else .8),y+.67,.26),(.092,.092,.24),TEAM[team])
            post.setColorScale(.90,1.,1.,1.)

    def clear(self):
        for node,_,_,_,_ in self.particles:
            node.removeNode()
        self.particles.clear()
        self.broken_since.clear()
        self.ripples.clear()
        for node,_,crack in self.slabs:
            node.show()
            node.setZ(0)
            crack.hide()

    def add_events(self,events):
        for kind,team,x,y in events:
            if kind not in ("fish","fall","sink","dash"):
                continue
            if kind in ("fall","sink"):
                self.ripples=(self.ripples+[(x,y,self.elapsed,1.35)])[-4:]
            color=2 if kind=="fish" else team if kind=="dash" else 3
            amount=7 if kind in ("fish","dash") else 13
            rng=Random(round(self.elapsed*1000)+team*541)
            for index in range(amount):
                bit=self.bits[color].copyTo(self.overlay)
                theta=index*tau/amount+rng.uniform(-.15,.15)
                speed=rng.uniform(.56,2.15)
                start=Vec3(x,y,.18 if kind in ("fish","dash") else WATER_Z)
                delta=Vec3(cos(theta)*speed,sin(theta)*speed,rng.uniform(.78,2.0))
                self.particles.append((bit,start,delta,self.elapsed,rng.uniform(.028,.062)))

    def update(self,state,dt):
        self.elapsed+=dt
        self.root.setShaderInput("scene_time",self.elapsed)
        self.water.setShaderInput("tide_time",self.elapsed)
        for i in range(4):
            ripple=self.ripples[i] if i<len(self.ripples) else (0,0,-20,0)
            self.water.setShaderInput(f"ripple{i}",Vec4(*ripple))
        for cell,(node,material,crack) in enumerate(self.slabs):
            mark=state.ice[cell]
            if mark==-1:
                started=self.broken_since.setdefault(cell,self.elapsed)
                age=(self.elapsed-started)/.58
                if age>=1:
                    node.hide()
                else:
                    node.setZ(-1.25*age)
                crack.hide()
            else:
                node.show()
                node.setZ(0)
                crack.show() if mark>0 else crack.hide()
            material.setShaderInput("fracture",max(0.,min(1.,1-(mark-state.tick)/CRACK_TICKS)) if mark>0 else 0.)
            material.setShaderInput("scene_time",self.elapsed)
        for side,pawn in enumerate(state.skaters):
            rig=self.swimmers[side]
            ring=self.rings[side]
            shadow=self.shadows[side]
            shadow.setPos(pawn.x,pawn.y,0)
            ring.setPos(pawn.x,pawn.y,0)
            if pawn.splash:
                rig.root.hide(); ring.hide(); shadow.hide()
            else:
                rig.root.show(); ring.show(); shadow.show()
                speed=(pawn.vx*pawn.vx+pawn.vy*pawn.vy)**.5
                rig.root.setPos(pawn.x,pawn.y,.08+.025*sin(self.elapsed*9+side)*min(speed/4,1))
                rig.root.setHpr(degrees(atan2(pawn.face_x,-pawn.face_y)),min(19.,speed*2.),5*sin(self.elapsed*8)*min(speed/4,1))
                rig.pose(min(.38,speed*.041))
            for i,dot in enumerate(self.trails[side]):
                if pawn.boost and not pawn.splash:
                    dot.show()
                    ahead=.016*(i+1)
                    dot.setPos(pawn.x-pawn.vx*ahead,pawn.y-pawn.vy*ahead,.14+.07*sin(i))
                    dot.setScale(.054*(1-i*.079))
                else:
                    dot.hide()
        for index,frog in enumerate(self.fish):
            glow=self.fish_glow[index]
            if state.school_mask & (1<<index):
                x,y=fish_position(state,index)
                frog.show(); glow.show()
                frog.setPos(x,y,.225+.07*sin(self.elapsed*4+index))
                frog.setH(26*sin(self.elapsed*2.1+index)+(0 if index%2 else 155))
                glow.setPos(x,y,0)
            else:
                frog.hide(); glow.hide()
        for beam,x,y,phase in self.glints:
            beam.setPos(x+.25*sin(self.elapsed*.53+phase),y+.21*cos(self.elapsed*.65+phase),.95+.56*sin(self.elapsed*.67+phase))
        alive=[]
        for node,start,velocity,created,size in self.particles:
            age=self.elapsed-created
            if age>=.57:
                node.removeNode()
            else:
                node.setPos(start+velocity*age-Vec3(0,0,3.12*age*age))
                node.setScale(size*(1-age/.65))
                alive.append((node,start,velocity,created,size))
        self.particles=alive
